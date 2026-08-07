const API = "/api";
let trafficMap = null;
let trafficMapLayer = null;
const state = {
  metadata: null,
  role: localStorage.getItem("flowcast-role") || "traffic_analyst",
  activeView: "overview",
  charts: {},
  latestForecast: [],
};

const pageTitles = {
  overview: "Operations Overview",
  live: "Live Traffic Forecast",
  historical: "Historical Analytics",
  map: "Interactive Traffic Map",
  weather: "Weather Impact Analysis",
  model: "Model Transparency",
  upload: "Batch Prediction Studio",
  alerts: "Operational Alert Centre",
  reports: "Reports & Exports",
};

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];
const safeNumber = (value, digits = 1) => Number(value ?? 0).toFixed(digits);
const formatPercent = (value) => `${Math.round(Number(value ?? 0) * 100)}%`;
const formatTime = (value) => new Date(value).toLocaleString([], { dateStyle: "short", timeStyle: "short" });
const escapeHtml = (value) => String(value ?? "")
  .replaceAll("&", "&amp;")
  .replaceAll("<", "&lt;")
  .replaceAll(">", "&gt;")
  .replaceAll('"', "&quot;")
  .replaceAll("'", "&#039;");

async function apiFetch(path, options = {}) {
  const response = await fetch(`${API}${path}`, options);
  if (!response.ok) {
    let detail = `Request failed (${response.status})`;
    try {
      const payload = await response.json();
      detail = payload.detail || detail;
    } catch (_) { /* no JSON body */ }
    throw new Error(detail);
  }
  const contentType = response.headers.get("content-type") || "";
  return contentType.includes("application/json") ? response.json() : response;
}

function toast(message, type = "success") {
  const element = document.createElement("div");
  element.className = `toast ${type}`;
  element.textContent = message;
  $("#toastContainer").appendChild(element);
  setTimeout(() => element.remove(), 4200);
}

function setLoadingTable(selector, columns, text = "Loading…") {
  $(selector).innerHTML = `<tr><td colspan="${columns}" class="loading-cell">${escapeHtml(text)}</td></tr>`;
}

function congestionChip(level) {
  const normalized = String(level || "Low").toLowerCase();
  return `<span class="status-chip status-${normalized}">${escapeHtml(level)}</span>`;
}

function riskClass(value) {
  if (Number(value) >= 0.65) return "high";
  if (Number(value) >= 0.4) return "medium";
  return "";
}

function chartColors() {
  return {
    blue: "#4aa9ff",
    teal: "#53e0c2",
    yellow: "#f6b84a",
    red: "#ff667d",
    purple: "#9b8cff",
    grid: "rgba(149,179,211,.11)",
    text: "#8fa8c2",
  };
}

function destroyChart(name) {
  if (state.charts[name]) {
    state.charts[name].destroy();
    delete state.charts[name];
  }
}

function commonChartOptions(extra = {}) {
  const colors = chartColors();
  return {
    responsive: true,
    maintainAspectRatio: false,
    interaction: { intersect: false, mode: "index" },
    plugins: {
      legend: { labels: { color: colors.text, boxWidth: 12, usePointStyle: true } },
      tooltip: { backgroundColor: "#071525", borderColor: "rgba(149,179,211,.25)", borderWidth: 1 },
    },
    scales: {
      x: { ticks: { color: colors.text, maxRotation: 0, autoSkip: true }, grid: { color: colors.grid } },
      y: { ticks: { color: colors.text }, grid: { color: colors.grid } },
    },
    ...extra,
  };
}

function showView(view) {
  const allowedNav = $(`.nav-item[data-view="${view}"]:not([style*="display: none"])`);
  if (!allowedNav) {
    const roleInfo = state.metadata?.roles?.[state.role];
    view = roleInfo?.default_view || "overview";
  }
  state.activeView = view;
  $$(".view").forEach((item) => item.classList.toggle("active", item.id === `view-${view}`));
  $$(".nav-item").forEach((item) => item.classList.toggle("active", item.dataset.view === view));
  $("#pageTitle").textContent = pageTitles[view] || "FlowCast";
  $("#sidebar").classList.remove("open");
  loadView(view);
}

async function loadView(view) {
  try {
    if (view === "overview") await loadOverview();
    if (view === "live") await loadLiveForecast();
    if (view === "historical") await loadHistorical();
    if (view === "map") await loadTrafficMap();
    if (view === "weather") await loadWeatherImpact();
    if (view === "model") await loadModelDiagnostics();
    if (view === "reports") {
  await Promise.all([
    loadReportSummary(),
    loadRuns(),
  ]);
}
    if (view === "reports") await loadRuns();
  } catch (error) {
    toast(error.message, "error");
  }
}

async function initialize() {
  bindEvents();
  setDateDefaults();
  try {
    const [health, metadata] = await Promise.all([apiFetch("/health"), apiFetch("/metadata")]);
    state.metadata = metadata;
    $("#apiStatus").textContent = `${health.model_version} · healthy`;
    populateSegments(metadata.segments);
    applyRole(state.role);
    $("#modelModePill").textContent = health.model_mode === "loaded_artifacts" ? "Production artifacts loaded" : "Demo model adapter";
    await Promise.all([loadOverview(), loadAlerts(false)]);
  } catch (error) {
    $("#apiStatus").textContent = "Connection failed";
    toast(`API connection failed: ${error.message}`, "error");
  }
}

function bindEvents() {
  $$(".nav-item").forEach((button) => button.addEventListener("click", () => showView(button.dataset.view)));
  $("#menuButton").addEventListener("click", () => $("#sidebar").classList.toggle("open"));
  $("#refreshButton").addEventListener("click", () => loadView(state.activeView));
  $("#roleSelect").addEventListener(
  "change",
  (event) => {
    const selectedRole =
      event.target.value;

    applyRole(selectedRole);
  }
);
  $("#overviewWindow").addEventListener("change", loadOverview);
  $("#runForecastButton").addEventListener("click", loadLiveForecast);
  $("#applyHistoryButton").addEventListener("click", loadHistorical);
  $("#refreshMapButton").addEventListener(
  "click",
  () => loadTrafficMap(true)
);
  $("#refreshWeatherImpact").addEventListener("click", loadWeatherImpact);
  $("#refreshAlertsButton").addEventListener("click", () => loadAlerts(true));
  $("#uploadForm").addEventListener("submit", uploadCsv);
  $("#csvFile").addEventListener("change", (event) => {
    $("#selectedFileName").textContent = event.target.files[0]?.name || "No file selected";
  });
  ["dragenter", "dragover"].forEach((name) => $("#dropZone").addEventListener(name, (event) => {
    event.preventDefault(); $("#dropZone").classList.add("dragging");
  }));
  ["dragleave", "drop"].forEach((name) => $("#dropZone").addEventListener(name, (event) => {
    event.preventDefault(); $("#dropZone").classList.remove("dragging");
  }));
  $("#dropZone").addEventListener("drop", (event) => {
    const file = event.dataTransfer.files[0];
    if (file) {
      const transfer = new DataTransfer(); transfer.items.add(file); $("#csvFile").files = transfer.files;
      $("#selectedFileName").textContent = file.name;
    }
  });
  $("#loadReportButton").addEventListener(
  "click",
  () => loadReportSummary(true)
);
  $("#downloadCsvReport").addEventListener("click", () => downloadReport("csv"));
  $("#downloadHtmlReport").addEventListener("click", () => downloadReport("html"));
  $("#closeModal").addEventListener("click", () => $("#lineageModal").classList.add("hidden"));
  $("#lineageModal").addEventListener("click", (event) => {
    if (event.target === $("#lineageModal")) $("#lineageModal").classList.add("hidden");
  });
}
function applyRole(role) {
  console.log("applyRole received:", role);
  const roleInfo =
    state.metadata?.roles?.[role];

  if (!roleInfo) {
    console.error(
      "Unknown FlowCast role:",
      role
    );
    return;
  }

  // Update application state
  state.role = role;

  // Remember selected role
  localStorage.setItem(
    "flowcast-role",
    role
  );

  // Keep dropdown synchronized
  $("#roleSelect").value = role;

  // Update role workspace text
  $("#roleGoal").textContent =
    roleInfo.goal;

  // Show only views permitted for this role
  $$(".nav-item").forEach((button) => {
    const view = button.dataset.view;

    const isAllowed =
      roleInfo.views.includes(view);

    button.style.display =
      isAllowed ? "flex" : "none";
  });

  // If current page isn't allowed,
  // move to role's default page.
  if (
    !roleInfo.views.includes(
      state.activeView
    )
  ) {
    showView(
      roleInfo.default_view
    );
  }
}


function populateSegments(segments) {
  ["#liveSegment", "#historySegment"].forEach((selector) => {
    const select = $(selector);
    segments.forEach((segment) => {
      const option = document.createElement("option");
      option.value = segment.segment_id;
      option.textContent = `${segment.segment_id} · ${segment.segment_name}`;
      select.appendChild(option);
    });
  });
}

function setDateDefaults() {
  const end = new Date();
  const start = new Date(); start.setDate(start.getDate() - 7);
  const endString = end.toISOString().slice(0, 10);
  const startString = start.toISOString().slice(0, 10);
  ["#historyEnd", "#reportEnd"].forEach((selector) => $(selector).value = endString);
  ["#historyStart", "#reportStart"].forEach((selector) => $(selector).value = startString);
}

async function loadOverview() {
  setLoadingTable("#overviewSegmentTable", 7);
  const hours = $("#overviewWindow").value;
  const [payload, weather] = await Promise.all([
    apiFetch(`/dashboard/overview?hours=${hours}`),
    apiFetch("/weather/current"),
  ]);
  const kpi = payload.kpis || {};
  $("#kpiSpeed").textContent = safeNumber(kpi.average_speed_kmh);
  $("#kpiVolume").textContent = Math.round(kpi.average_volume || 0).toLocaleString();
  $("#kpiTravel").textContent = safeNumber(kpi.average_travel_time_min);
  $("#kpiRisk").textContent = kpi.high_risk_segments ?? 0;
  $("#kpiSevere").textContent = `${safeNumber(kpi.severe_congestion_share)}%`;
  $("#kpiSegments").textContent = kpi.active_segments ?? 0;

  $("#weatherTemperature").textContent = safeNumber(weather.temperature_c, 0);
  $("#weatherRain").textContent = `${safeNumber(weather.precipitation_mm)} mm`;
  $("#weatherVisibility").textContent = `${safeNumber(weather.visibility_km)} km`;
  $("#weatherWind").textContent = `${safeNumber(weather.wind_speed_kmh)} km/h`;
  $("#weatherSource").textContent = weather.source;

  renderOverviewTrend(payload.trend || []);
  $("#overviewSegmentTable").innerHTML = (payload.latest_segments || []).map((row) => `
    <tr>
      <td><strong>${escapeHtml(row.segment_id)}</strong><br><span class="muted">${escapeHtml(row.segment_name)}</span></td>
      <td>${safeNumber(row.speed_kmh)} km/h</td>
      <td>${Math.round(row.predicted_volume).toLocaleString()}</td>
      <td>${safeNumber(row.predicted_travel_time)} min</td>
      <td>${congestionChip(row.predicted_congestion)}</td>
      <td class="risk-value ${riskClass(row.predicted_accident_risk)}">${formatPercent(row.predicted_accident_risk)}</td>
      <td>${escapeHtml(row.model_version)}</td>
    </tr>`).join("") || `<tr><td colspan="7" class="loading-cell">No data found.</td></tr>`;
}

function renderOverviewTrend(rows) {
  destroyChart("overviewTrend");
  const colors = chartColors();
  state.charts.overviewTrend = new Chart($("#overviewTrendChart"), {
    type: "line",
    data: {
      labels: rows.map((row) => new Date(row.bucket).toLocaleString([], { weekday: "short", hour: "2-digit" })),
      datasets: [
        { label: "Forecast volume", data: rows.map((row) => row.predicted_volume), borderColor: colors.blue, backgroundColor: "rgba(74,169,255,.12)", fill: true, tension: .35, yAxisID: "y" },
        { label: "Travel time (min)", data: rows.map((row) => row.predicted_travel_time), borderColor: colors.teal, tension: .35, yAxisID: "y1" },
      ],
    },
    options: commonChartOptions({
      scales: {
        x: { ticks: { color: colors.text, maxRotation: 0 }, grid: { color: colors.grid } },
        y: { position: "left", ticks: { color: colors.text }, grid: { color: colors.grid } },
        y1: { position: "right", ticks: { color: colors.text }, grid: { drawOnChartArea: false } },
      },
    }),
  });
}

async function loadLiveForecast() {
  setLoadingTable("#liveForecastTable", 8, "Running forecast…");
  const horizon = $("#forecastHorizon").value;
  const segment = $("#liveSegment").value;
  const payload = await apiFetch(`/predictions/near-term?horizon_minutes=${horizon}&segment_id=${encodeURIComponent(segment)}`);
  state.latestForecast = payload.predictions || [];
  renderLiveForecastChart(state.latestForecast);
  renderRiskChart(state.latestForecast);
  $("#liveForecastTable").innerHTML = state.latestForecast.map((row, index) => `
    <tr>
      <td>${formatTime(row.datetime)}</td><td><strong>${escapeHtml(row.segment_id)}</strong><br>${escapeHtml(row.segment_name)}</td>
      <td>${Math.round(row.predicted_volume).toLocaleString()}</td><td>${safeNumber(row.predicted_travel_time)} min</td>
      <td>${congestionChip(row.predicted_congestion)}</td><td class="risk-value ${riskClass(row.predicted_accident_risk)}">${formatPercent(row.predicted_accident_risk)}</td>
      <td>${formatPercent(row.confidence)}</td><td><button class="lineage-button" data-lineage-index="${index}">Inspect</button></td>
    </tr>`).join("") || `<tr><td colspan="8" class="loading-cell">No forecast records.</td></tr>`;
  $$('[data-lineage-index]').forEach((button) => button.addEventListener("click", () => showLineage(state.latestForecast[Number(button.dataset.lineageIndex)])));
}

function renderLiveForecastChart(rows) {
  destroyChart("liveForecast");
  const colors = chartColors();
  const segments = [...new Set(rows.map((row) => row.segment_id))];
  const labels = [...new Set(rows.map((row) => row.datetime))].sort();
  const palette = [colors.blue, colors.teal, colors.yellow, colors.red, colors.purple, "#79d16f", "#ff9f5b", "#7ec8e3"];
  state.charts.liveForecast = new Chart($("#liveForecastChart"), {
    type: "line",
    data: {
      labels: labels.map((value) => new Date(value).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })),
      datasets: segments.map((segment, index) => ({
        label: segment,
        data: labels.map((label) => rows.find((row) => row.segment_id === segment && row.datetime === label)?.predicted_volume ?? null),
        borderColor: palette[index % palette.length], tension: .32, pointRadius: 3,
      })),
    },
    options: commonChartOptions(),
  });
}

function renderRiskChart(rows) {
  destroyChart("risk");
  const counts = { Low: 0, Medium: 0, High: 0 };
  rows.forEach((row) => {
    const risk = Number(row.predicted_accident_risk);
    counts[risk >= .65 ? "High" : risk >= .4 ? "Medium" : "Low"] += 1;
  });
  const colors = chartColors();
  state.charts.risk = new Chart($("#riskChart"), {
    type: "doughnut",
    data: { labels: Object.keys(counts), datasets: [{ data: Object.values(counts), backgroundColor: [colors.teal, colors.yellow, colors.red], borderWidth: 0 }] },
    options: { responsive: true, maintainAspectRatio: false, cutout: "68%", plugins: { legend: { position: "bottom", labels: { color: colors.text, usePointStyle: true } } } },
  });
}

function showLineage(row) {
  const fields = {
    "Prediction ID": row.prediction_id,
    "Run ID": row.run_id,
    "Segment": `${row.segment_id} · ${row.segment_name}`,
    "Forecast time": row.datetime,
    "Model version": row.model_version,
    "Input SHA-256": row.input_hash,
    "Created at": row.created_at,
    "Confidence": formatPercent(row.confidence),
  };
  $("#lineageContent").innerHTML = Object.entries(fields).map(([label, value]) => `<div class="lineage-row"><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong></div>`).join("");
  $("#lineageModal").classList.remove("hidden");
}

function dateQuery(prefix = "history") {
  const start = $(`#${prefix}Start`).value;
  const end = $(`#${prefix}End`).value;
  return `start=${encodeURIComponent(start)}&end=${encodeURIComponent(`${end}T23:59:59Z`)}`;
}

async function loadHistorical() {
  const query = dateQuery("history");
  const segment = $("#historySegment").value;
  const [historyPayload, heatPayload, roadPayload] = await Promise.all([
    apiFetch(`/analytics/historical?${query}&segment_id=${encodeURIComponent(segment)}`),
    apiFetch(`/analytics/heatmap?${query}`),
    apiFetch(`/analytics/road-comparison?${query}`),
  ]);
  renderHistoricalChart(historyPayload.series || []);
  renderHeatmap(heatPayload);
  renderRoadComparison(roadPayload.roads || []);
}

function renderHistoricalChart(rows) {
  destroyChart("historical");
  const colors = chartColors();
  const labels = [...new Set(rows.map((row) => row.bucket))].sort();
  const aggregate = labels.map((bucket) => {
    const values = rows.filter((row) => row.bucket === bucket);
    const average = (key) => values.reduce((sum, item) => sum + Number(item[key] || 0), 0) / Math.max(values.length, 1);
    return { bucket, speed: average("speed_kmh"), travel: average("predicted_travel_time") };
  });
  state.charts.historical = new Chart($("#historicalChart"), {
    type: "line",
    data: {
      labels: aggregate.map((row) => new Date(row.bucket).toLocaleString([], { month: "short", day: "numeric", hour: "2-digit" })),
      datasets: [
        { label: "Average speed km/h", data: aggregate.map((row) => row.speed), borderColor: colors.blue, tension: .3 },
        { label: "Predicted travel min", data: aggregate.map((row) => row.travel), borderColor: colors.yellow, tension: .3 },
      ],
    }, options: commonChartOptions(),
  });
}

function renderHeatmap(payload) {
  const cells = payload.cells || [];
  const hours = payload.hours || [];
  const segments = payload.segments || [];
  const grid = $("#heatmapGrid");
  grid.style.gridTemplateColumns = `minmax(110px, 1.7fr) repeat(${hours.length}, minmax(20px, 1fr))`;
  let html = `<div></div>${hours.map((hour) => `<div class="heat-hour">${hour}</div>`).join("")}`;
  segments.forEach((segment) => {
    html += `<div class="heat-label" title="${escapeHtml(segment.segment_name)}">${escapeHtml(segment.segment_id)}</div>`;
    hours.forEach((hour) => {
      const cell = cells.find((item) => item.segment_id === segment.segment_id && Number(item.hour) === Number(hour));
      const score = Math.max(1, Math.min(4, Math.round(Number(cell?.congestion_score || 1))));
      const title = cell ? `${segment.segment_name} · ${hour}:00 · score ${safeNumber(cell.congestion_score)} · risk ${formatPercent(cell.accident_risk)}` : "No data";
      html += `<div class="heat-cell heat-${score}" title="${escapeHtml(title)}"></div>`;
    });
  });
  grid.innerHTML = html;
}

function renderRoadComparison(rows) {
  destroyChart("roadComparison");
  const colors = chartColors();
  state.charts.roadComparison = new Chart($("#roadComparisonChart"), {
    type: "bar",
    data: { labels: rows.map((row) => row.segment_id), datasets: [{ label: "Travel time (min)", data: rows.map((row) => row.average_travel_time_min), backgroundColor: colors.blue, borderRadius: 7 }] },
    options: commonChartOptions({ indexAxis: "y" }),
  });
}

function mapCongestionColor(level) {
  const congestion = String(level || "Low").toLowerCase();

  if (congestion === "severe") {
    return "#ff667d";
  }

  if (
    congestion === "heavy" ||
    congestion === "high"
  ) {
    return "#f6b84a";
  }

  if (congestion === "moderate") {
    return "#4aa9ff";
  }

  return "#53e0c2";
}


function initializeTrafficMap() {
  if (trafficMap) {
    return;
  }

  const Leaflet = window.L;

  if (!Leaflet) {
    throw new Error(
      "Map library could not be loaded. Check your internet connection."
    );
  }

  trafficMap = Leaflet.map("trafficMap", {
    zoomControl: true,
  }).setView(
    [22.5726, 88.3639],
    12
  );

  Leaflet.tileLayer(
    "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
    {
      maxZoom: 19,
      attribution:
        '&copy; <a href="https://www.openstreetmap.org/copyright">' +
        "OpenStreetMap contributors</a>",
    }
  ).addTo(trafficMap);

  trafficMapLayer = Leaflet
    .layerGroup()
    .addTo(trafficMap);
}


async function loadTrafficMap(showToast = false) {
  initializeTrafficMap();

  const payload = await apiFetch("/map/traffic");
  const segments = payload.segments || [];

  trafficMapLayer.clearLayers();

  if (!segments.length) {
    $("#selectedMapSegment").innerHTML = `
      <strong>No map data available</strong>
      <p>
        Upload traffic data or check the traffic-observations
        database.
      </p>
    `;

    trafficMap.invalidateSize();
    return;
  }

  const Leaflet = window.L;
  const markerBounds = [];

  segments.forEach((segment) => {
    const latitude = Number(segment.latitude);
    const longitude = Number(segment.longitude);

    if (
      !Number.isFinite(latitude) ||
      !Number.isFinite(longitude)
    ) {
      return;
    }

    const congestion =
      segment.predicted_congestion || "Low";

    const markerColor =
      mapCongestionColor(congestion);

    const marker = Leaflet.circleMarker(
      [latitude, longitude],
      {
        radius: 10,
        color: markerColor,
        fillColor: markerColor,
        fillOpacity: 0.82,
        weight: 3,
      }
    );

    marker.bindTooltip(
      `${escapeHtml(segment.segment_id)} · ` +
      `${escapeHtml(congestion)}`,
      {
        direction: "top",
        offset: [0, -8],
      }
    );

    marker.bindPopup(`
      <div>
        <strong>
          ${escapeHtml(segment.segment_name)}
        </strong>

        <br>
        Segment:
        ${escapeHtml(segment.segment_id)}

        <br>
        Speed:
        ${safeNumber(segment.speed_kmh)} km/h

        <br>
        Current volume:
        ${Math.round(
          Number(segment.volume || 0)
        ).toLocaleString()}

        <br>
        Predicted volume:
        ${Math.round(
          Number(segment.predicted_volume || 0)
        ).toLocaleString()}

        <br>
        Travel time:
        ${safeNumber(
          segment.predicted_travel_time
        )} min

        <br>
        Congestion:
        ${escapeHtml(congestion)}

        <br>
        Accident risk:
        ${formatPercent(
          segment.predicted_accident_risk
        )}
      </div>
    `);

    marker.on("click", () => {
      renderSelectedMapSegment(segment);
    });

    marker.addTo(trafficMapLayer);

    markerBounds.push([
      latitude,
      longitude,
    ]);
  });

  if (markerBounds.length === 1) {
    trafficMap.setView(
      markerBounds[0],
      14
    );
  } else if (markerBounds.length > 1) {
    trafficMap.fitBounds(
      markerBounds,
      {
        padding: [35, 35],
        maxZoom: 14,
      }
    );
  }

  setTimeout(() => {
    trafficMap.invalidateSize();
  }, 150);

  if (showToast) {
    toast(
      `Traffic map refreshed: ${markerBounds.length} segments.`
    );
  }
}


function renderSelectedMapSegment(segment) {
  $("#selectedMapSegment").innerHTML = `
    <strong>
      ${escapeHtml(segment.segment_name)}
    </strong>

    <p>
      Segment:
      ${escapeHtml(segment.segment_id)}
      <br>

      Latest observation:
      ${formatTime(segment.datetime)}
      <br>

      Speed:
      ${safeNumber(segment.speed_kmh)} km/h
      <br>

      Occupancy:
      ${formatPercent(segment.occupancy)}
      <br>

      Predicted volume:
      ${Math.round(
        Number(segment.predicted_volume || 0)
      ).toLocaleString()}
      <br>

      Travel time:
      ${safeNumber(
        segment.predicted_travel_time
      )} min
      <br>

      Congestion:
      ${escapeHtml(
        segment.predicted_congestion || "Unknown"
      )}
      <br>

      Accident risk:
      ${formatPercent(
        segment.predicted_accident_risk
      )}
      <br>

      Model version:
      ${escapeHtml(
        segment.model_version || "Unknown"
      )}
    </p>
  `;
}

async function loadWeatherImpact() {
  const query = dateQuery("history");
  const payload = await apiFetch(`/analytics/weather-impact?${query}`);
  renderWeatherImpact(payload.buckets || []);
  $("#correlationCards").innerHTML = Object.entries(payload.correlations || {}).map(([key, value]) => `
    <div class="correlation-item"><span>${escapeHtml(key.replaceAll("_", " "))}</span><strong>${Number(value) > 0 ? "+" : ""}${safeNumber(value, 3)}</strong></div>`).join("") || `<div class="empty-state">No correlation data.</div>`;
}

function renderWeatherImpact(rows) {
  destroyChart("weatherImpact");
  const colors = chartColors();
  state.charts.weatherImpact = new Chart($("#weatherImpactChart"), {
    type: "bar",
    data: {
      labels: rows.map((row) => row.rain_bucket),
      datasets: [
        { label: "Travel time (min)", data: rows.map((row) => row.average_travel_time_min), backgroundColor: colors.blue, yAxisID: "y" },
        { label: "Accident risk %", data: rows.map((row) => row.average_accident_risk * 100), backgroundColor: colors.red, yAxisID: "y1" },
      ],
    },
    options: commonChartOptions({
      scales: {
        x: { ticks: { color: colors.text }, grid: { color: colors.grid } },
        y: { position: "left", ticks: { color: colors.text }, grid: { color: colors.grid } },
        y1: { position: "right", ticks: { color: colors.text, callback: (value) => `${value}%` }, grid: { drawOnChartArea: false } },
      },
    }),
  });
}

async function loadModelDiagnostics() {
  const payload = await apiFetch("/model/diagnostics");

  // Model version
  $("#modelVersionLabel").textContent =
    payload.model_version || "Unknown";

  // Model mode
  $("#modelModeLabel").textContent =
    payload.mode_label ||
    payload.mode ||
    "Unknown mode";

  // Performance metrics
  const metrics = payload.metrics || {};
  const metricEntries = [];

  Object.entries(metrics).forEach(
    ([model, values]) => {
      Object.entries(values || {}).forEach(
        ([metric, value]) => {
          metricEntries.push({
            model,
            metric,
            value,
          });
        }
      );
    }
  );

  $("#metricCards").innerHTML =
    metricEntries.length
      ? metricEntries
          .slice(0, 8)
          .map(
            (item) => `
              <article class="kpi-card">
                <span>
                  ${escapeHtml(
                    item.model.replaceAll("_", " ")
                  )}
                </span>

                <strong>
                  ${
                    typeof item.value === "number"
                      ? safeNumber(item.value, 3)
                      : escapeHtml(item.value)
                  }
                </strong>

                <small>
                  ${escapeHtml(
                    item.metric.toUpperCase()
                  )}
                </small>
              </article>
            `
          )
          .join("")
      : `
          <article class="kpi-card">
            <span>Execution mode</span>
            <strong>
              ${escapeHtml(
                payload.mode_label ||
                payload.mode ||
                "Unknown"
              )}
            </strong>
            <small>Model runtime information</small>
          </article>
        `;

  // Feature importance
  renderFeatureImportance(
    payload.feature_importance || []
  );

  // Diagnostics
  const diagnostics = {
    "Execution mode":
      payload.mode_label ||
      payload.mode ||
      "Unknown",

    "Loaded models":
      (payload.loaded_models || []).join(", ") ||
      "No trained artifacts loaded",

    "Expected models":
      (payload.expected_models || []).join(", ") ||
      "Not specified",

    "Forecast horizons":
      (payload.forecast_horizons_minutes || [])
        .map((value) => `${value} min`)
        .join(", ") ||
      "Not specified",

    "Random seed":
      payload.seed ?? "Not specified",
  };

  $("#modelDiagnostics").innerHTML =
    Object.entries(diagnostics)
      .map(
        ([key, value]) => `
          <div class="diagnostic-item">
            <span>${escapeHtml(key)}</span>
            <strong>${escapeHtml(value)}</strong>
          </div>
        `
      )
      .join("");

  // Input features
  const features =
    payload.feature_order || [];

  $("#modelFeatureList").innerHTML =
    features.length
      ? features
          .map(
            (feature) => `
              <span class="model-info-tag">
                ${escapeHtml(feature)}
              </span>
            `
          )
          .join("")
      : `
          <span class="model-info-placeholder">
            Feature information is not available.
          </span>
        `;

  // Prediction targets
  const targets =
    payload.prediction_targets || [];

  $("#modelTargetList").innerHTML =
    targets.length
      ? targets
          .map(
            (target) => `
              <span class="model-info-tag">
                ${escapeHtml(target)}
              </span>
            `
          )
          .join("")
      : `
          <span class="model-info-placeholder">
            Prediction targets are not available.
          </span>
        `;

  // Prediction lineage
  const lineage =
    payload.lineage_fields || [];

  $("#modelLineageList").innerHTML =
    lineage.length
      ? lineage
          .map(
            (field) => `
              <span class="model-info-tag">
                ${escapeHtml(field)}
              </span>
            `
          )
          .join("")
      : `
          <span class="model-info-placeholder">
            Lineage information is not available.
          </span>
        `;

  // Notes
  $("#modelNotes").textContent =
    payload.notes ||
    "No additional model notes are available.";

  // Limitations
  const limitations =
    payload.limitations || [];

  $("#modelLimitationsList").innerHTML =
    limitations.length
      ? limitations
          .map(
            (item) => `
              <li>${escapeHtml(item)}</li>
            `
          )
          .join("")
      : `
          <li>
            No model limitations are currently listed.
          </li>
        `;
}

function renderFeatureImportance(rows) {
  destroyChart("featureImportance");
  const fallback = [
    { feature: "volume", importance: .24 }, { feature: "occupancy", importance: .19 },
    { feature: "hour", importance: .15 }, { feature: "speed_kmh", importance: .14 },
    { feature: "rain_mm", importance: .10 }, { feature: "visibility_km", importance: .07 },
    { feature: "event_flag", importance: .06 }, { feature: "day_of_week", importance: .05 },
  ];
  const values = (rows.length ? rows : fallback).slice(0, 12).sort((a, b) => a.importance - b.importance);
  state.charts.featureImportance = new Chart($("#featureImportanceChart"), {
    type: "bar",
    data: { labels: values.map((row) => row.feature), datasets: [{ label: "Importance", data: values.map((row) => row.importance), backgroundColor: chartColors().teal, borderRadius: 7 }] },
    options: commonChartOptions({ indexAxis: "y" }),
  });
}

async function uploadCsv(event) {
  event.preventDefault();
  const file = $("#csvFile").files[0];
  if (!file) return toast("Select a CSV file first.", "error");
  const formData = new FormData(); formData.append("file", file);
  $("#uploadProgress").classList.remove("hidden");
  $("#uploadPredictButton").disabled = true;
  try {
    const result = await apiFetch("/predict/upload", { method: "POST", body: formData });
    renderUploadResult(result);
    toast(`Prediction completed: ${result.valid_rows.toLocaleString()} valid rows.`, "success");
  } catch (error) {
    toast(error.message, "error");
  } finally {
    $("#uploadProgress").classList.add("hidden");
    $("#uploadPredictButton").disabled = false;
  }
}

function renderUploadResult(result) {
  $("#uploadResult").classList.remove("hidden");
  const stats = [
    ["Total rows", result.total_rows], ["Valid predictions", result.valid_rows], ["Quarantined", result.invalid_rows],
    ["Inference time", `${result.elapsed_seconds}s`], ["Performance target", result.under_30_second_target ? "Passed" : "Review"], ["Model", result.model_version],
  ];
  $("#uploadStats").innerHTML = stats.map(([label, value]) => `<article class="kpi-card"><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong></article>`).join("");
  let downloads = `<a class="primary-button" href="${API}/exports/${encodeURIComponent(result.export_filename)}">Download predictions</a>`;
  if (result.quarantine_filename) downloads += `<a class="secondary-button" href="${API}/quarantine/${encodeURIComponent(result.quarantine_filename)}">Download quarantine</a>`;
  $("#uploadDownloads").innerHTML = downloads;
  $("#uploadPreviewTable").innerHTML = (result.preview || []).map((row) => `<tr><td>${escapeHtml(row.datetime)}</td><td>${escapeHtml(row.segment_id)}</td><td>${Math.round(row.predicted_volume).toLocaleString()}</td><td>${safeNumber(row.predicted_travel_time)}</td><td>${congestionChip(row.predicted_congestion)}</td><td>${formatPercent(row.predicted_accident_risk)}</td><td>${formatPercent(row.confidence)}</td></tr>`).join("") || `<tr><td colspan="7" class="loading-cell">No valid rows. Download the quarantine file to see errors.</td></tr>`;
}

async function loadAlerts(showToast = false) {
  const payload = await apiFetch("/alerts");
  const alerts = payload.alerts || [];
  $("#alertCount").textContent = alerts.length;
  $("#alertsList").innerHTML = alerts.map((alert) => `
    <article class="alert-card ${escapeHtml(alert.severity)}">
      <div class="alert-symbol">!</div>
      <div><h4>${escapeHtml(alert.segment_id)} · ${escapeHtml(alert.message)}</h4><p>${escapeHtml(alert.segment_name)}</p><div class="alert-meta"><span>${formatTime(alert.forecast_time)}</span><span>Confidence ${formatPercent(alert.confidence)}</span><span>${escapeHtml(alert.recommended_action)}</span></div></div>
      <button class="secondary-button acknowledge-alert" data-alert-id="${escapeHtml(alert.alert_id)}">Acknowledge</button>
    </article>`).join("") || `<div class="empty-state">No active high-risk alerts. The corridor is within configured thresholds.</div>`;
  $$(".acknowledge-alert").forEach((button) => button.addEventListener("click", async () => {
    try { await apiFetch(`/alerts/${button.dataset.alertId}/acknowledge`, { method: "POST" }); await loadAlerts(false); toast("Alert acknowledged."); }
    catch (error) { toast(error.message, "error"); }
  }));
  if (showToast) toast(`Alert centre refreshed: ${alerts.length} active.`);
}

async function loadReportSummary(showToast = false) {
  const query = dateQuery("report");

  try {
    const payload = await apiFetch(
      `/reports/summary?${query}`
    );

    const summary = payload.summary || {};

    $("#reportTotalRecords").textContent =
      Number(
        summary.total_records || 0
      ).toLocaleString();

    $("#reportTotalSegments").textContent =
      Number(
        summary.total_segments || 0
      ).toLocaleString();

    $("#reportAverageVolume").textContent =
      Number(
        summary.average_volume || 0
      ).toLocaleString(undefined, {
        maximumFractionDigits: 1,
      });

    $("#reportAverageTravelTime").textContent =
      safeNumber(
        summary.average_travel_time,
        1
      );

    $("#reportAverageRisk").textContent =
      `${safeNumber(
        summary.average_accident_risk,
        1
      )}%`;

    renderReportCongestionChart(
      payload.congestion_distribution || []
    );

    if (showToast) {
      toast("Report summary loaded successfully.");
    }
  } catch (error) {
    console.error(
      "Report summary error:",
      error
    );

    toast(
      `Unable to load report: ${error.message}`,
      "error"
    );
  }
}


function renderReportCongestionChart(rows) {
  destroyChart("reportCongestion");

  const colors = chartColors();

  const congestionColors = {
    low: colors.teal,
    moderate: colors.yellow,
    heavy: "#ff965b",
    high: colors.red,
    severe: colors.red,
    unknown: colors.purple,
  };

  const labels = rows.map(
    (row) => row.congestion || "Unknown"
  );

  const values = rows.map(
    (row) => Number(row.count || 0)
  );

  const backgroundColors = labels.map(
    (label) =>
      congestionColors[
        String(label).toLowerCase()
      ] || colors.purple
  );

  state.charts.reportCongestion = new Chart(
    $("#reportCongestionChart"),
    {
      type: "doughnut",

      data: {
        labels,
        datasets: [
          {
            data: values,
            backgroundColor: backgroundColors,
            borderWidth: 0,
          },
        ],
      },

      options: {
        responsive: true,
        maintainAspectRatio: false,
        cutout: "68%",

        plugins: {
          legend: {
            position: "bottom",

            labels: {
              color: colors.text,
              usePointStyle: true,
              boxWidth: 12,
            },
          },

          tooltip: {
            backgroundColor: "#071525",
            borderColor:
              "rgba(149,179,211,.25)",
            borderWidth: 1,
          },
        },
      },
    }
  );
}

function downloadReport(format) {
  const query = dateQuery("report");
  window.location.href = `${API}/reports/export?format=${format}&${query}`;
}

async function loadRuns() {
  setLoadingTable("#runsTable", 8);
  const payload = await apiFetch("/prediction-runs");
  $("#runsTable").innerHTML = (payload.runs || []).map((row) => `<tr><td>${formatTime(row.created_at)}</td><td>${escapeHtml(row.source_file)}</td><td>${Number(row.total_rows).toLocaleString()}</td><td>${Number(row.valid_rows).toLocaleString()}</td><td>${Number(row.invalid_rows).toLocaleString()}</td><td>${safeNumber(row.elapsed_seconds, 3)}s</td><td>${escapeHtml(row.model_version)}</td><td><a class="lineage-button" href="${API}/exports/${encodeURIComponent(row.export_filename)}">Download</a></td></tr>`).join("") || `<tr><td colspan="8" class="loading-cell">No upload runs yet.</td></tr>`;
}

document.addEventListener("DOMContentLoaded", initialize);
