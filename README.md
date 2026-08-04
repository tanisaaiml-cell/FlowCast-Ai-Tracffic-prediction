# FlowCast — Full-Stack Traffic Prediction Dashboard

FlowCast is a traffic operations web application with a Python/FastAPI backend and a responsive HTML/CSS/JavaScript dashboard. It includes near-term forecasts, historical charts, congestion heatmaps, weather integration, model transparency, CSV batch inference, invalid-row quarantine, alerts, report export and prediction lineage.

## 1. What is included

```text
flowcast_web_fullstack/
├── app/
│   ├── api/routes.py                 # REST API endpoints
│   ├── services/                     # models, analytics, weather, upload, reports
│   ├── static/                       # frontend dashboard
│   ├── config.py                     # environment configuration
│   ├── db.py                         # SQLite + demo data
│   ├── schemas.py                    # API validation
│   └── main.py                       # FastAPI app
├── model_artifacts/registry.json     # model names, features, metrics and version
├── scripts/                          # training, benchmark and setup validation
├── tests/                            # API tests
├── data/                             # SQLite, exports and quarantine files
├── Dockerfile
├── render.yaml
├── setup.bat / setup.sh
├── run.bat / run.sh
└── requirements.txt
```

## 2. Run locally on Windows — beginner steps

1. Extract the ZIP.
2. Open the extracted `flowcast_web_fullstack` folder in VS Code.
3. Open **Terminal → New Terminal**.
4. Run one setup command:

```powershell
.\setup.bat
```

5. Start the project:

```powershell
.\run.bat
```

6. Open:

```text
http://127.0.0.1:8000
```

API documentation:

```text
http://127.0.0.1:8000/docs
```

Do not create another `venv` manually after running `setup.bat`; it already creates `.venv` and installs the pinned packages.

### Manual Windows commands when a BAT file is blocked

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
python -m uvicorn main:app --reload
```

## 3. First run behaviour

The app creates a deterministic 30-day, eight-segment demo dataset in SQLite. This makes every dashboard page immediately testable. Until you add your own model files, the backend uses a deterministic prediction adapter and clearly displays **Demo model adapter**.

## 4. Connect your trained FlowCast models

Your Colab work already produced the actual regression and classification models. Copy the final **preprocessing + model pipelines** into `model_artifacts/` using these names, or use your own names and edit the registry:

```text
model_artifacts/
├── volume_model.joblib
├── travel_time_model.joblib
├── congestion_model.joblib
├── accident_risk_model.joblib
└── registry.json
```

Important rules:

- Save the complete preprocessing pipeline whenever possible, not only the estimator.
- `feature_order` must exactly match training.
- Congestion predictions should be `Low`, `Moderate`, `High`, or `Severe`.
- Accident-risk classifiers should support `predict_proba`; otherwise `predict` is used.
- Restart `run.bat` after replacing model files.
- Open **Model Insights** as System Owner and verify the mode says `loaded_artifacts`.

A demonstration training script is included:

```powershell
python scripts\train_demo_models.py
```

It is for testing the integration pattern, not a replacement for your final Colab models.

## 5. CSV upload format

Required columns:

```text
datetime, segment_id, speed_kmh, volume, occupancy, temp_c,
rain_mm, visibility_km, event_flag
```

Optional columns:

```text
segment_name, distance_km
```

Use **Upload & Predict → Download sample CSV**. Invalid rows are never silently discarded. They are returned in a quarantine CSV with an `_validation_error` column.

## 6. Dashboard pages

- **Overview:** network KPIs, live weather, forecast trend and segment table.
- **Live Forecast:** 30–180 minute segment forecast, risk chart and prediction lineage.
- **Historical Trends:** time-series chart, congestion heatmap and road comparison.
- **Weather Impact:** rain buckets and weather/traffic correlations.
- **Model Insights:** metrics, feature importance, artifact mode and reproducibility.
- **Upload & Predict:** chunked batch inference with exports and quarantine.
- **Alerts:** ranked high-congestion and accident-risk alerts with acknowledgement.
- **Reports:** date-range CSV/HTML export and recent batch audit trail.

Use the **Working as** selector to see the interface designed for each user role.

## 7. Test and benchmark

Run tests:

```powershell
pip install -r requirements-dev.txt
pytest -q
```

Benchmark the 150,000-row non-functional target:

```powershell
python scripts\benchmark_batch.py
```

The exact time depends on your laptop and whether your real models are heavier than the demo adapter.

## 8. Deploy live on Render

This project intentionally serves frontend and backend from one FastAPI service, so you only deploy once and avoid frontend/backend URL and CORS mistakes.

1. Create a new GitHub repository named `flowcast-dashboard`.
2. From the project terminal:

```powershell
git init
git add .
git commit -m "Build FlowCast full-stack dashboard"
git branch -M main
git remote add origin YOUR_GITHUB_REPOSITORY_URL
git push -u origin main
```

3. In Render, create a **Web Service** from the repository.
4. Use:

```text
Build command: pip install -r requirements.txt
Start command: uvicorn main:app --host 0.0.0.0 --port $PORT
Health check: /api/health
Python: 3.11.11
```

5. Deploy and open the Render URL.
6. In Render environment variables, set `ALLOWED_ORIGINS` to your final Render URL.

`render.yaml` is already included for Blueprint deployment.

### Important persistence note

Render's local disk can be replaced during redeploys. For a class/portfolio demo, SQLite is acceptable. For a production deployment, move observations, run history and alert acknowledgement to PostgreSQL, and store exports in object storage.

## 9. Weather API

The backend calls Open-Meteo, so no API key is required for the included integration. The browser never receives a secret. When the weather service is temporarily unavailable, the backend returns a safe fallback so the dashboard remains usable.

Set the corridor location in `.env`:

```env
FLOWCAST_LATITUDE=22.5726
FLOWCAST_LONGITUDE=88.3639
```


