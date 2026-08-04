# FlowCast API

Interactive Swagger documentation is available at `http://127.0.0.1:8000/docs` after the server starts.

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/api/health` | Service and model health |
| GET | `/api/metadata` | Segments, role capabilities and model version |
| GET | `/api/dashboard/overview` | KPI cards and latest segment status |
| GET | `/api/predictions/near-term` | 30–180 minute forecast by segment |
| POST | `/api/predict/single` | One JSON prediction |
| POST | `/api/predict/upload` | Chunked CSV validation and batch inference |
| GET | `/api/analytics/historical` | Historical trend series |
| GET | `/api/analytics/heatmap` | Congestion heatmap values |
| GET | `/api/analytics/road-comparison` | Road comparison metrics |
| GET | `/api/analytics/weather-impact` | Rain-bucket traffic analytics |
| GET | `/api/model/diagnostics` | Metrics, features and artifact status |
| GET | `/api/alerts` | Ranked operational alerts |
| POST | `/api/alerts/{id}/acknowledge` | Acknowledge an alert |
| GET | `/api/weather/current` | Current Open-Meteo weather |
| GET | `/api/reports/export` | CSV or HTML report |
| GET | `/api/prediction-runs` | Recent batch run audit trail |

## Single prediction example

```json
{
  "segment_id": "SEG-01",
  "datetime": "2026-07-31T09:00:00Z",
  "speed_kmh": 28.5,
  "volume": 940,
  "occupancy": 0.71,
  "temp_c": 30.2,
  "rain_mm": 0,
  "visibility_km": 9.5,
  "event_flag": 0,
  "distance_km": 1.9
}
```
