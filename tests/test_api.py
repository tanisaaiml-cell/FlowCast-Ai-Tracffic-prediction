from io import BytesIO

from fastapi.testclient import TestClient

from main import app


def test_health_and_metadata():
    with TestClient(app) as client:
        health = client.get("/api/health")
        assert health.status_code == 200
        assert health.json()["status"] == "ok"
        metadata = client.get("/api/metadata")
        assert metadata.status_code == 200
        assert len(metadata.json()["segments"]) == 8


def test_near_term_predictions_have_lineage():
    with TestClient(app) as client:
        response = client.get("/api/predictions/near-term?horizon_minutes=60&segment_id=SEG-01")
        assert response.status_code == 200
        rows = response.json()["predictions"]
        assert rows
        assert rows[0]["input_hash"]
        assert rows[0]["model_version"]


def test_upload_quarantines_invalid_row():
    csv_data = (
        "datetime,segment_id,speed_kmh,volume,occupancy,temp_c,rain_mm,visibility_km,event_flag,distance_km\n"
        "2026-07-31T09:00:00Z,SEG-01,30,900,0.7,30,0,10,0,2\n"
        "bad-date,SEG-02,-1,1000,1.4,30,0,10,0,2\n"
    )
    with TestClient(app) as client:
        response = client.post(
            "/api/predict/upload",
            files={"file": ("test.csv", BytesIO(csv_data.encode()), "text/csv")},
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["valid_rows"] == 1
        assert payload["invalid_rows"] == 1
        assert payload["quarantine_filename"]
