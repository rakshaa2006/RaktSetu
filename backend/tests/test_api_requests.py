import pytest
from fastapi.testclient import TestClient

from app.factory import create_app
from tests.conftest import DATA_DIR


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok" and body["database"] == "ok" and body["demo_data"] is True


def test_swagger_docs_available(client):
    assert client.get("/docs").status_code == 200
    assert client.get("/openapi.json").status_code == 200


def test_create_request_returns_id_status_and_patient_blood_group(client, payload):
    r = client.post("/api/requests", json=payload)
    assert r.status_code == 201
    body = r.json()
    assert body["id"].startswith("REQ-") and body["status"] == "open"
    assert body["patient_blood_group"] == "O+"
    assert body["created_at"]


def test_patient_details_are_persisted_and_retrievable(client, payload):
    rid = client.post("/api/requests", json=payload).json()["id"]
    got = client.get(f"/api/requests/{rid}").json()
    assert got["patient_name"] == payload["patient_name"]
    assert got["patient_age"] == 42
    assert got["patient_gender"] == "Female"
    assert got["patient_blood_group"] == "O+"
    assert any(r["id"] == rid for r in client.get("/api/requests").json())


@pytest.mark.parametrize("field,value", [
    ("patient_name", ""), ("patient_name", "A"), ("patient_name", "R2D2 9000"),
    ("patient_age", -1), ("patient_age", 121), ("patient_age", 25.5), ("patient_age", "abc"),
    ("patient_gender", "Robot"), ("patient_blood_group", "Z+"), ("component", "Water"),
    ("units_required", 0), ("units_required", -3), ("units_required", 2.5), ("units_required", 99),
    ("urgency", "Whenever"), ("hospital_name", ""), ("hospital_location", ""),
])
def test_invalid_request_fields_are_rejected(client, payload, field, value):
    payload[field] = value
    r = client.post("/api/requests", json=payload)
    assert r.status_code == 422


def test_missing_required_field_and_unknown_field_rejected(client, payload):
    del payload["patient_blood_group"]
    assert client.post("/api/requests", json=payload).status_code == 422
    payload2 = dict(payload, patient_blood_group="O+", surprise="x")
    assert client.post("/api/requests", json=payload2).status_code == 422


def test_half_supplied_coordinates_rejected(client, payload):
    del payload["hospital_longitude"]
    assert client.post("/api/requests", json=payload).status_code == 422


def test_request_without_coordinates_is_allowed_and_distance_unknown(client, payload):
    payload.update(hospital_latitude=None, hospital_longitude=None)
    rid = client.post("/api/requests", json=payload).json()["id"]
    top = client.get(f"/api/requests/{rid}/recommendations").json()["current"]["ranked"][0]
    assert top["distance_km"] is None and "unknown" in top["distance_note"].lower()


def test_missing_ids_return_404(client):
    for path in ("", "/recommendations", "/timeline"):
        assert client.get(f"/api/requests/REQ-NOPE{path}").status_code == 404
    assert client.post("/api/requests/REQ-NOPE/events", json={"event_type": "DATA_STALE", "candidate_type": "donor", "candidate_id": "DN-001"}).status_code == 404
    assert client.patch("/api/requests/REQ-NOPE/status", json={"status": "under_review"}).status_code == 404


def test_unknown_candidate_id_returns_404(client, created):
    r = client.post(f"/api/requests/{created['id']}/events", json={"event_type": "DATA_STALE", "candidate_type": "donor", "candidate_id": "DN-999"})
    assert r.status_code == 404


def test_request_survives_backend_restart(db_url, payload):
    first = TestClient(create_app(database_url=db_url, seed=True, data_dir=DATA_DIR))
    rid = first.post("/api/requests", json=payload).json()["id"]
    first.post(f"/api/requests/{rid}/events", json={"event_type": "DATA_STALE", "candidate_type": "donor", "candidate_id": "DN-001"})
    first.close()
    second = TestClient(create_app(database_url=db_url, seed=True, data_dir=DATA_DIR))  # "restart"
    got = second.get(f"/api/requests/{rid}").json()
    assert got["patient_name"] == payload["patient_name"] and got["patient_blood_group"] == "O+"
    assert len(second.get(f"/api/requests/{rid}/timeline").json()) >= 4
    assert second.get(f"/api/requests/{rid}/recommendations").json()["current"]["version"] == 2


def test_cors_only_for_configured_origin(client):
    ok = client.get("/api/health", headers={"Origin": "http://localhost:5173"})
    assert ok.headers.get("access-control-allow-origin") == "http://localhost:5173"
    bad = client.get("/api/health", headers={"Origin": "http://evil.example"})
    assert "access-control-allow-origin" not in bad.headers
