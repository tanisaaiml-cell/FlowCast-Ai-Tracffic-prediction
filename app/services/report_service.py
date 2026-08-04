"""Generate downloadable analytics reports."""

from __future__ import annotations

from datetime import datetime, timezone
from html import escape
from io import BytesIO

import pandas as pd

from app.services.analytics_service import road_comparison, weather_impact


def build_csv_report(start: str | None, end: str | None) -> bytes:
    frame = pd.DataFrame(road_comparison(start, end))
    if frame.empty:
        frame = pd.DataFrame([{"message": "No data in selected range"}])
    return frame.to_csv(index=False).encode("utf-8")


def build_html_report(start: str | None, end: str | None) -> bytes:
    comparison = road_comparison(start, end)
    weather = weather_impact(start, end)
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    rows = "".join(
        "<tr>"
        f"<td>{escape(str(item['segment_id']))}</td>"
        f"<td>{escape(str(item['segment_name']))}</td>"
        f"<td>{item['average_speed_kmh']:.1f}</td>"
        f"<td>{item['average_volume']:.0f}</td>"
        f"<td>{item['average_travel_time_min']:.1f}</td>"
        f"<td>{item['average_accident_risk']:.1%}</td>"
        "</tr>"
        for item in comparison
    )
    highest = max(comparison, key=lambda x: x["average_accident_risk"], default=None)
    insight = (
        f"Highest average risk: {highest['segment_name']} ({highest['average_accident_risk']:.1%})."
        if highest else "No observations were available for the selected range."
    )
    html = f"""<!doctype html>
<html><head><meta charset="utf-8"><title>FlowCast Report</title>
<style>
body{{font-family:Arial,sans-serif;margin:36px;color:#17213a}}h1{{color:#153d70}}
.meta{{color:#5b6578;margin-bottom:24px}}table{{border-collapse:collapse;width:100%}}
th,td{{border:1px solid #ccd5e3;padding:9px;text-align:left}}th{{background:#173d6b;color:white}}
.insight{{padding:14px;background:#edf5ff;border-left:5px solid #1e78d6;margin:18px 0}}
</style></head><body>
<h1>FlowCast Analytics Report</h1>
<div class="meta">Range: {escape(str(start or 'default'))} to {escape(str(end or 'now'))}<br>Generated: {generated}</div>
<div class="insight"><strong>Key insight:</strong> {escape(insight)}</div>
<h2>Road comparison</h2>
<table><thead><tr><th>ID</th><th>Segment</th><th>Speed km/h</th><th>Volume</th><th>Travel min</th><th>Risk</th></tr></thead>
<tbody>{rows}</tbody></table>
<h2>Weather correlation</h2><pre>{escape(str(weather.get('correlations', {})))}</pre>
<p>Model outputs are decision-support estimates and should be reviewed with operational context.</p>
</body></html>"""
    return html.encode("utf-8")
