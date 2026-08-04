# Requirement Mapping

## Functional analytics requirements

| ID | Requirement | Implementation |
|---|---|---|
| FR-13 | Present live/near-term predictions per segment | Live Forecast page + `/api/predictions/near-term` |
| FR-14 | Historical trends, congestion heatmaps and road comparison | Historical page + three analytics endpoints |
| FR-15 | Metrics, feature importance and forecast visualizations | Model Insights page + registry-backed diagnostics |
| FR-16 | Weather-vs-traffic analysis | Weather Impact page + Open-Meteo integration |
| FR-17 | Upload data and trigger prediction | Upload & Predict page + chunked CSV API |
| FR-18 | Export report for a selected range | Reports page + CSV/HTML export |

## Non-functional requirements

| Category | Target | Implementation / verification |
|---|---|---|
| Performance | Full-corridor horizon ≤ 30 seconds | Vectorized pandas inference, 25k row chunks, `scripts/benchmark_batch.py` |
| Scalability | ≥150k rows on 16 GB | Chunked reading and 200k default upload safety limit |
| Reproducibility | Deterministic | Fixed seed 42 and versioned model registry |
| Maintainability | Modular and documented | `api`, `services`, `schemas`, docs, type hints and docstrings |
| Usability | ≤3 clicks to any view | Persistent sidebar and role-specific navigation |
| Reliability | No silent drops | Invalid records are written to downloadable quarantine CSVs; failures logged |
| Portability | One setup command | `setup.bat`, `setup.sh`, Dockerfile and pinned dependencies |
| Transparency | Full lineage | Prediction ID, run ID, SHA-256 input hash, model version, source and timestamp |

## User roles

- **Traffic Operations Analyst:** overview, live forecast, historical analytics, weather, alerts and reports.
- **Incident Response Coordinator:** live conditions and ranked risk alerts.
- **Transport Planner:** historical trends, weather impact, road comparison and reports.
- **System Owner / Reviewer:** all views, model diagnostics, batch upload and audit trail.

The role switcher is a portfolio/demo role-oriented interface, not a security boundary. Add SSO/JWT authentication before a real agency deployment.
