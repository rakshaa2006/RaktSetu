from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.factory import create_app

DATA_DIR = Path(__file__).resolve().parents[2] / "data"

VALID_REQUEST = {
    "patient_name": "Test Patient Alpha",
    "patient_age": 42,
    "patient_gender": "Female",
    "patient_blood_group": "O+",
    "component": "Packed Red Cells",
    "units_required": 2,
    "hospital_name": "Demo City Hospital",
    "hospital_location": "Shivajinagar",
    "hospital_latitude": 18.5308,
    "hospital_longitude": 73.8475,
    "urgency": "Critical",
}


@pytest.fixture()
def db_url(tmp_path):
    return f"sqlite:///{(tmp_path / 'test.db').as_posix()}"


@pytest.fixture()
def app(db_url):
    return create_app(database_url=db_url, seed=True, data_dir=DATA_DIR)


@pytest.fixture()
def client(app):
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def payload():
    return dict(VALID_REQUEST)


@pytest.fixture()
def created(client, payload):
    r = client.post("/api/requests", json=payload)
    assert r.status_code == 201, r.text
    return r.json()


def recs(client, request_id):
    r = client.get(f"/api/requests/{request_id}/recommendations")
    assert r.status_code == 200, r.text
    return r.json()


def post_event(client, request_id, event_type, candidate_type=None, candidate_id=None, reason=None):
    body = {"event_type": event_type}
    if candidate_type:
        body["candidate_type"] = candidate_type
        body["candidate_id"] = candidate_id
    if reason:
        body["reason"] = reason
    return client.post(f"/api/requests/{request_id}/events", json=body)
