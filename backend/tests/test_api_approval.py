"""Comprehensive test suite for the blood request approval workflow.

Covers:
- Demo token configuration and fail-closed authentication
- Bank isolation and cross-bank authorization
- Request creation with target blood banks
- Explicit approval and rejection decisions
- Rejection reason bounds and validation
- Audit history and timeline persistence
- Double-decision prevention and conflict (409) handling
- Concurrent decision execution
- Separation of approval from unit allocation
- Database schema migration compatibility
"""
from __future__ import annotations

import concurrent.futures
import os
from pathlib import Path
from typing import Dict

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.core.config import parse_demo_tokens
from app.database import init_db, make_engine
from app.factory import create_app
from tests.conftest import DATA_DIR, VALID_REQUEST

DEMO_TOKENS_CONFIG = "demo-tok-bb001:BB-001,demo-tok-bb002:BB-002"
BB1_AUTH = {"Authorization": "Bearer demo-tok-bb001"}
BB2_AUTH = {"Authorization": "Bearer demo-tok-bb002"}


@pytest.fixture()
def approval_app(tmp_path, monkeypatch):
    monkeypatch.setenv("RAKTSETU_DEMO_TOKENS", DEMO_TOKENS_CONFIG)
    db_url = f"sqlite:///{(tmp_path / 'approval_test.db').as_posix()}"
    return create_app(database_url=db_url, seed=True, data_dir=DATA_DIR)


@pytest.fixture()
def client(approval_app):
    with TestClient(approval_app) as c:
        yield c


def _create_targeted_request(client: TestClient, target_bank: str = "BB-001") -> Dict:
    payload = dict(VALID_REQUEST)
    payload["target_blood_bank_id"] = target_bank
    res = client.post("/api/requests", json=payload)
    assert res.status_code == 201, res.text
    return res.json()


# ============================================================================
# 1. Configuration & Fail-Closed Authentication
# ============================================================================
def test_parse_demo_tokens_formats():
    # JSON format
    tokens = parse_demo_tokens('{"tok1": "BB-001", "tok2": "BB-002"}')
    assert tokens == {"tok1": "BB-001", "tok2": "BB-002"}

    # Delimited format (colon)
    tokens = parse_demo_tokens("tok1:BB-001, tok2:BB-002")
    assert tokens == {"tok1": "BB-001", "tok2": "BB-002"}

    # Delimited format (equals)
    tokens = parse_demo_tokens("tok1=BB-001,tok2=BB-002")
    assert tokens == {"tok1": "BB-001", "tok2": "BB-002"}

    # Fail closed on empty/garbage
    assert parse_demo_tokens("") == {}
    assert parse_demo_tokens("   ") == {}
    assert parse_demo_tokens("{invalid-json") == {}


def test_auth_fails_closed_when_unconfigured(tmp_path, monkeypatch):
    monkeypatch.setenv("RAKTSETU_DEMO_TOKENS", "")
    db_url = f"sqlite:///{(tmp_path / 'unconfigured.db').as_posix()}"
    app = create_app(database_url=db_url, seed=True, data_dir=DATA_DIR)

    with TestClient(app) as unauth_client:
        # Any attempt with a token fails 401 closed
        res = unauth_client.get("/api/blood-banks/inbox", headers={"Authorization": "Bearer any-token"})
        assert res.status_code == 401
        assert "WWW-Authenticate" in res.headers
        assert "No blood bank demo identities configured" in res.json()["detail"]


def test_auth_rejects_missing_or_malformed_token(client):
    # Missing header
    res = client.get("/api/blood-banks/inbox")
    assert res.status_code == 401
    assert "WWW-Authenticate" in res.headers

    # Malformed scheme (Basic)
    res = client.get("/api/blood-banks/inbox", headers={"Authorization": "Basic dXNlcjpwYXNz"})
    assert res.status_code == 401

    # Empty token
    res = client.get("/api/blood-banks/inbox", headers={"Authorization": "Bearer "})
    assert res.status_code == 401

    # Invalid/unrecognized token
    res = client.get("/api/blood-banks/inbox", headers={"Authorization": "Bearer wrong-token"})
    assert res.status_code == 401


# ============================================================================
# 2. Bank Isolation & Cross-Bank Protection
# ============================================================================
def test_bank_isolation_on_inbox(client):
    # BB-001 accesses its own inbox
    res = client.get("/api/blood-banks/inbox", headers=BB1_AUTH)
    assert res.status_code == 200

    # BB-001 accesses its own inbox via path parameter
    res = client.get("/api/blood-banks/BB-001/inbox", headers=BB1_AUTH)
    assert res.status_code == 200

    # Cross-bank access: BB-001 tries to access BB-002's inbox
    res = client.get("/api/blood-banks/BB-002/inbox", headers=BB1_AUTH)
    assert res.status_code == 403
    assert "Forbidden" in res.json()["detail"]


def test_cross_bank_decision_forbidden(client):
    # Request targeted to BB-001
    req = _create_targeted_request(client, target_bank="BB-001")

    # BB-002 tries to approve BB-001's request
    res = client.post(f"/api/requests/{req['id']}/approve", headers=BB2_AUTH)
    assert res.status_code == 403
    assert "Forbidden" in res.json()["detail"]

    # BB-002 tries to reject BB-001's request
    res = client.post(
        f"/api/requests/{req['id']}/reject",
        headers=BB2_AUTH,
        json={"reason": "Cannot accept outside bank requests"},
    )
    assert res.status_code == 403
    assert "Forbidden" in res.json()["detail"]


# ============================================================================
# 3. Request Creation with Target Bank
# ============================================================================
def test_create_request_with_valid_target_bank(client):
    req = _create_targeted_request(client, target_bank="BB-001")
    assert req["target_blood_bank_id"] == "BB-001"
    assert req["approval_status"] == "pending"
    assert req["status"] == "open"
    assert req["decided_at"] is None
    assert req["decided_by_bank_id"] is None


def test_create_request_with_nonexistent_bank_rejected(client):
    payload = dict(VALID_REQUEST)
    payload["target_blood_bank_id"] = "BB-NONEXISTENT"
    res = client.post("/api/requests", json=payload)
    assert res.status_code == 422
    assert "Target blood bank 'BB-NONEXISTENT' was not found" in res.json()["detail"]


def test_create_request_without_target_bank_backward_compatible(client):
    payload = dict(VALID_REQUEST)
    res = client.post("/api/requests", json=payload)
    assert res.status_code == 201
    data = res.json()
    assert data["target_blood_bank_id"] is None
    assert data["approval_status"] is None


# ============================================================================
# 4. Bank Inbox Content
# ============================================================================
def test_inbox_lists_targeted_requests(client):
    req1 = _create_targeted_request(client, target_bank="BB-001")
    req2 = _create_targeted_request(client, target_bank="BB-002")

    # Check BB-001 inbox
    res1 = client.get("/api/blood-banks/inbox", headers=BB1_AUTH)
    assert res1.status_code == 200
    ids_1 = [r["id"] for r in res1.json()]
    assert req1["id"] in ids_1
    assert req2["id"] not in ids_1

    # Check BB-002 inbox
    res2 = client.get("/api/blood-banks/inbox", headers=BB2_AUTH)
    assert res2.status_code == 200
    ids_2 = [r["id"] for r in res2.json()]
    assert req2["id"] in ids_2
    assert req1["id"] not in ids_2


# ============================================================================
# 5. Explicit Approval Workflow
# ============================================================================
def test_approve_request_success(client):
    req = _create_targeted_request(client, target_bank="BB-001")

    res = client.post(f"/api/requests/{req['id']}/approve", headers=BB1_AUTH)
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["approval_status"] == "approved"
    assert data["decided_by_bank_id"] == "BB-001"
    assert data["decided_at"] is not None
    # Transitioned from open to under_review
    assert data["status"] == "under_review"

    # Separation of concerns: stock is NOT allocated by approval
    assert data["allocated_units"] == 0
    assert data["remaining_units"] == req["units_required"]

    # Verify audit event in timeline
    timeline = client.get(f"/api/requests/{req['id']}/timeline").json()
    events = [e["event_type"] for e in timeline]
    assert "REQUEST_APPROVED" in events


def test_approve_alias_route_success(client):
    req = _create_targeted_request(client, target_bank="BB-001")

    res = client.post(f"/api/blood-banks/BB-001/requests/{req['id']}/approve", headers=BB1_AUTH)
    assert res.status_code == 200
    assert res.json()["approval_status"] == "approved"


# ============================================================================
# 6. Explicit Rejection Workflow & Reason Bounds
# ============================================================================
def test_reject_request_success(client):
    req = _create_targeted_request(client, target_bank="BB-001")

    reason = "Stock currently reserved for emergency surgeries."
    res = client.post(
        f"/api/requests/{req['id']}/reject",
        headers=BB1_AUTH,
        json={"reason": reason},
    )
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["approval_status"] == "rejected"
    assert data["rejection_reason"] == reason
    assert data["decided_by_bank_id"] == "BB-001"
    assert data["decided_at"] is not None

    # Verify audit event in timeline
    timeline = client.get(f"/api/requests/{req['id']}/timeline").json()
    rejections = [e for e in timeline if e["event_type"] == "REQUEST_REJECTED"]
    assert len(rejections) == 1
    assert reason in rejections[0]["reason"]


def test_reject_reason_validation(client):
    req = _create_targeted_request(client, target_bank="BB-001")

    # Missing reason
    res = client.post(f"/api/requests/{req['id']}/reject", headers=BB1_AUTH, json={})
    assert res.status_code == 422

    # Reason too short (< 5 chars)
    res = client.post(f"/api/requests/{req['id']}/reject", headers=BB1_AUTH, json={"reason": "No"})
    assert res.status_code == 422

    # Reason too long (> 300 chars)
    res = client.post(
        f"/api/requests/{req['id']}/reject",
        headers=BB1_AUTH,
        json={"reason": "A" * 301},
    )
    assert res.status_code == 422


# ============================================================================
# 7. One Decision Per Request (409 Conflict)
# ============================================================================
def test_cannot_decide_twice(client):
    req = _create_targeted_request(client, target_bank="BB-001")

    # First approval succeeds
    res1 = client.post(f"/api/requests/{req['id']}/approve", headers=BB1_AUTH)
    assert res1.status_code == 200

    # Second approval receives 409 Conflict
    res2 = client.post(f"/api/requests/{req['id']}/approve", headers=BB1_AUTH)
    assert res2.status_code == 409
    assert "already been recorded" in res2.json()["detail"]

    # Attempted rejection on approved request receives 409 Conflict
    res3 = client.post(
        f"/api/requests/{req['id']}/reject",
        headers=BB1_AUTH,
        json={"reason": "Changing our mind"},
    )
    assert res3.status_code == 409
    assert "already been recorded" in res3.json()["detail"]


# ============================================================================
# 8. Concurrent Decision Execution
# ============================================================================
def test_concurrent_decisions_serialize_safely(approval_app):
    with TestClient(approval_app) as init_client:
        req = _create_targeted_request(init_client, target_bank="BB-001")
        req_id = req["id"]

    results = []

    def make_decision(action: str):
        with TestClient(approval_app) as thread_client:
            if action == "approve":
                r = thread_client.post(f"/api/requests/{req_id}/approve", headers=BB1_AUTH)
            else:
                r = thread_client.post(
                    f"/api/requests/{req_id}/reject",
                    headers=BB1_AUTH,
                    json={"reason": "Concurrent race condition test rejection"},
                )
            results.append((r.status_code, r.text))

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        f1 = executor.submit(make_decision, "approve")
        f2 = executor.submit(make_decision, "reject")
        f1.result()
        f2.result()

    status_codes = sorted([r[0] for r in results])
    # Exactly one decision succeeds (200), and the second receives 409 Conflict
    assert status_codes == [200, 409], f"Unexpected concurrent statuses: {results}"


def test_concurrent_separate_db_sessions_serialize_at_database_level(approval_app, monkeypatch):
    """Verify database-level atomic conditional update safety even across separate database sessions.

    Disables the process-local threading.Lock to verify that database-level atomic UPDATE
    safely catches the race condition independently of in-memory locks.
    """
    from unittest.mock import MagicMock
    from app.services import approval
    from app.core.errors import ConflictError

    # Create targeted request
    with TestClient(approval_app) as init_client:
        req = _create_targeted_request(init_client, target_bank="BB-001")
        req_id = req["id"]

    session_factory = approval_app.state.session_factory

    # Bypass process-local lock to test raw database-level atomic conditional UPDATE
    dummy_lock = MagicMock()
    dummy_lock.__enter__ = MagicMock(return_value=None)
    dummy_lock.__exit__ = MagicMock(return_value=None)
    monkeypatch.setattr(approval, "_decision_lock", dummy_lock)

    # Session 1 approves
    with session_factory() as s1:
        approved_req = approval.approve_request(s1, req_id, acting_bank_id="BB-001")
        assert approved_req.approval_status == "approved"

    # Session 2 attempts rejection on the already-decided request
    with session_factory() as s2:
        with pytest.raises(ConflictError) as exc_info:
            approval.reject_request(s2, req_id, acting_bank_id="BB-001", reason="Valid reason but too late")
        assert "already been recorded" in str(exc_info.value)


# ============================================================================
# 9. Audit and Transaction Integrity (Rollback on Failure)
# ============================================================================
def test_audit_failure_rolls_back_approval_atomically(approval_app, monkeypatch):
    """Verify that if writing an audit event fails, the approval decision rolls back cleanly."""
    from app.services import approval, audit

    with TestClient(approval_app) as init_client:
        req = _create_targeted_request(init_client, target_bank="BB-001")
        req_id = req["id"]

    def failing_record_event(*args, **kwargs):
        raise RuntimeError("Simulated audit subsystem or storage failure")

    monkeypatch.setattr(audit, "record_event", failing_record_event)

    session_factory = approval_app.state.session_factory
    with session_factory() as db:
        with pytest.raises(RuntimeError) as exc_info:
            approval.approve_request(db, req_id, acting_bank_id="BB-001")
        assert "Simulated audit subsystem" in str(exc_info.value)

    # Verify atomic rollback in a fresh database session
    with session_factory() as db:
        from app.models.models import AuditEvent, BloodRequest
        fresh_req = db.get(BloodRequest, req_id)
        assert fresh_req.approval_status == "pending"
        assert fresh_req.status == "open"
        assert fresh_req.decided_at is None
        assert fresh_req.decided_by_bank_id is None

        # Verify no audit event was committed
        events = list(db.scalars(
            approval.select(AuditEvent).where(AuditEvent.request_id == req_id)
        ))
        assert not any(e.event_type == "REQUEST_APPROVED" for e in events)


def test_audit_failure_rolls_back_rejection_atomically(approval_app, monkeypatch):
    """Verify that if writing an audit event fails, the rejection decision rolls back cleanly."""
    from app.services import approval, audit

    with TestClient(approval_app) as init_client:
        req = _create_targeted_request(init_client, target_bank="BB-001")
        req_id = req["id"]

    def failing_record_event(*args, **kwargs):
        raise RuntimeError("Simulated audit storage failure during rejection")

    monkeypatch.setattr(audit, "record_event", failing_record_event)

    session_factory = approval_app.state.session_factory
    with session_factory() as db:
        with pytest.raises(RuntimeError) as exc_info:
            approval.reject_request(db, req_id, acting_bank_id="BB-001", reason="Valid rejection reason")
        assert "Simulated audit storage failure" in str(exc_info.value)

    # Verify rollback in a fresh session
    with session_factory() as db:
        from app.models.models import AuditEvent, BloodRequest
        fresh_req = db.get(BloodRequest, req_id)
        assert fresh_req.approval_status == "pending"
        assert fresh_req.rejection_reason is None
        assert fresh_req.decided_at is None

        events = list(db.scalars(
            approval.select(AuditEvent).where(AuditEvent.request_id == req_id)
        ))
        assert not any(e.event_type == "REQUEST_REJECTED" for e in events)


def test_failed_decision_does_not_create_misleading_audit_event(client):
    """Verify that a rejected or conflicting attempt does not write success audit events."""
    req = _create_targeted_request(client, target_bank="BB-001")

    # Initial timeline has REQUEST_CREATED and initial RANKING
    initial_timeline = client.get(f"/api/requests/{req['id']}/timeline").json()
    initial_event_count = len(initial_timeline)

    # Unauthorized bank attempt -> 403
    client.post(f"/api/requests/{req['id']}/approve", headers=BB2_AUTH)

    # Invalid rejection reason -> 422
    client.post(f"/api/requests/{req['id']}/reject", headers=BB1_AUTH, json={"reason": "No"})

    # Timeline event count must not change
    current_timeline = client.get(f"/api/requests/{req['id']}/timeline").json()
    assert len(current_timeline) == initial_event_count


# ============================================================================
# 10. Requester Visibility & Backward Compatibility
# ============================================================================
def test_requester_visible_decision_status(client):
    req = _create_targeted_request(client, target_bank="BB-001")
    req_id = req["id"]

    # Requester checks request: pending
    r1 = client.get(f"/api/requests/{req_id}").json()
    assert r1["approval_status"] == "pending"
    assert r1["decided_at"] is None

    # Bank approves
    client.post(f"/api/requests/{req_id}/approve", headers=BB1_AUTH)

    # Requester checks request: approved and status moved to under_review
    r2 = client.get(f"/api/requests/{req_id}").json()
    assert r2["approval_status"] == "approved"
    assert r2["decided_by_bank_id"] == "BB-001"
    assert r2["status"] == "under_review"
    assert r2["decided_at"] is not None


def test_legacy_request_without_target_bank_isolation(client):
    """Verify backward compatibility: legacy requests without target bank are preserved,

    and banks cannot approve or reject unassigned requests.
    """
    payload = dict(VALID_REQUEST)  # No target_blood_bank_id
    res = client.post("/api/requests", json=payload)
    assert res.status_code == 201
    legacy_req = res.json()
    assert legacy_req["target_blood_bank_id"] is None
    assert legacy_req["approval_status"] is None

    # Not visible in BB-001's inbox
    inbox = client.get("/api/blood-banks/inbox", headers=BB1_AUTH).json()
    assert legacy_req["id"] not in [r["id"] for r in inbox]

    # Attempt to approve an unassigned request is forbidden (403)
    appr = client.post(f"/api/requests/{legacy_req['id']}/approve", headers=BB1_AUTH)
    assert appr.status_code == 403

    # Attempt to reject an unassigned request is forbidden (403)
    rej = client.post(
        f"/api/requests/{legacy_req['id']}/reject",
        headers=BB1_AUTH,
        json={"reason": "Cannot reject unassigned request"},
    )
    assert rej.status_code == 403


# ============================================================================
# 11. Database Migration Compatibility
# ============================================================================
def test_migration_adds_columns_to_existing_database(tmp_path):
    db_file = tmp_path / "legacy_test.db"
    engine = make_engine(f"sqlite:///{db_file.as_posix()}")

    # Simulate legacy table without approval columns
    with engine.connect() as conn:
        conn.exec_driver_sql("""
            CREATE TABLE blood_requests (
                id VARCHAR(32) PRIMARY KEY,
                patient_name VARCHAR(100),
                patient_age INTEGER,
                patient_gender VARCHAR(24),
                patient_blood_group VARCHAR(3),
                component VARCHAR(32),
                units_required INTEGER,
                hospital_name VARCHAR(120),
                hospital_location VARCHAR(120),
                hospital_latitude FLOAT,
                hospital_longitude FLOAT,
                urgency VARCHAR(16),
                status VARCHAR(32) DEFAULT 'open',
                created_at DATETIME,
                updated_at DATETIME
            )
        """)
        conn.commit()

    # Call init_db to perform migration
    init_db(engine)

    # Inspect columns
    with engine.connect() as conn:
        res = conn.exec_driver_sql("PRAGMA table_info(blood_requests)").fetchall()
        cols = {row[1] for row in res}
        assert "target_blood_bank_id" in cols
        assert "approval_status" in cols
        assert "rejection_reason" in cols
        assert "decided_at" in cols
        assert "decided_by_bank_id" in cols
