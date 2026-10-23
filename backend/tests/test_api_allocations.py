"""Comprehensive validation, fulfillment, shared inventory, and transaction integrity tests for allocations."""
import pytest
from sqlalchemy import select

from app.models.models import Allocation, BloodBank, BloodRequest
from tests.conftest import post_event, recs


def confirm_candidate(client, request_id, candidate_type, candidate_id):
    """Workflow: candidate must be selected for review, then confirmed available."""
    r_sel = post_event(client, request_id, "SELECT_FOR_REVIEW", candidate_type, candidate_id)
    assert r_sel.status_code == 201, r_sel.text
    r_conf = post_event(client, request_id, "CONFIRM_AVAILABILITY", candidate_type, candidate_id)
    assert r_conf.status_code == 201, r_conf.text


def test_allocation_validation_errors(client, created):
    rid = created["id"]
    top = recs(client, rid)["current"]["ranked"][0]
    confirm_candidate(client, rid, top["candidate_type"], top["candidate_id"])

    # Zero units
    r = client.post(f"/api/requests/{rid}/allocations", json={
        "candidate_type": top["candidate_type"], "candidate_id": top["candidate_id"], "units": 0
    })
    assert r.status_code == 422

    # Negative units
    r = client.post(f"/api/requests/{rid}/allocations", json={
        "candidate_type": top["candidate_type"], "candidate_id": top["candidate_id"], "units": -2
    })
    assert r.status_code == 422

    # Non-integer units
    r = client.post(f"/api/requests/{rid}/allocations", json={
        "candidate_type": top["candidate_type"], "candidate_id": top["candidate_id"], "units": "two"
    })
    assert r.status_code == 422

    # Missing request
    r = client.post("/api/requests/REQ-NONEXISTENT/allocations", json={
        "candidate_type": top["candidate_type"], "candidate_id": top["candidate_id"], "units": 1
    })
    assert r.status_code == 404

    # Missing candidate
    r = client.post(f"/api/requests/{rid}/allocations", json={
        "candidate_type": "blood_bank", "candidate_id": "BB-NONEXISTENT", "units": 1
    })
    assert r.status_code == 404

    # Unknown candidate type
    r = client.post(f"/api/requests/{rid}/allocations", json={
        "candidate_type": "alien", "candidate_id": top["candidate_id"], "units": 1
    })
    assert r.status_code == 422

    # Extra fields (extra='forbid')
    r = client.post(f"/api/requests/{rid}/allocations", json={
        "candidate_type": top["candidate_type"], "candidate_id": top["candidate_id"], "units": 1, "extra": "field"
    })
    assert r.status_code == 422


def test_unconfirmed_candidate_allocation_rejected(client, created):
    rid = created["id"]
    top = recs(client, rid)["current"]["ranked"][0]
    # Candidate not yet confirmed
    r = client.post(f"/api/requests/{rid}/allocations", json={
        "candidate_type": top["candidate_type"], "candidate_id": top["candidate_id"], "units": 1
    })
    assert r.status_code == 422
    assert "must be confirmed" in r.json()["detail"].lower()


def test_incompatible_blood_group_rejected(client, app, payload):
    # Create request for O- packed red cells (only O- is compatible)
    p = dict(payload, patient_blood_group="O-", component="Packed Red Cells", units_required=1)
    r = client.post("/api/requests", json=p)
    assert r.status_code == 201
    rid = r.json()["id"]

    # Pick an A+ blood bank
    with app.state.session_factory() as db:
        ab_bank = db.scalar(select(BloodBank).where(BloodBank.blood_group == "A+"))
        assert ab_bank is not None
        bank_id = ab_bank.id

    # Confirm and try to allocate A+ bank
    confirm_candidate(client, rid, "blood_bank", bank_id)
    alloc = client.post(f"/api/requests/{rid}/allocations", json={
        "candidate_type": "blood_bank", "candidate_id": bank_id, "units": 1
    })
    assert alloc.status_code == 422
    assert "not compatible" in alloc.json()["detail"].lower()


def test_donor_capacity_and_duplicate_prevention(client, app, payload):
    # Create request needing 2 units
    p = dict(payload, units_required=2)
    rid = client.post("/api/requests", json=p).json()["id"]

    donors = client.get("/api/donors").json()
    eligible_donor = next(
        d for d in donors
        if d["consent_status"] == "consented_demo"
        and d["blood_group"] in ("O+", "O-")
        and d["availability_status"] in ("reported_available", "confirmed_available")
    )
    did = eligible_donor["id"]

    confirm_candidate(client, rid, "donor", did)

    # Attempt to allocate 2 units to a single donor -> rejected
    r = client.post(f"/api/requests/{rid}/allocations", json={
        "candidate_type": "donor", "candidate_id": did, "units": 2
    })
    assert r.status_code == 422
    assert "at most one unit" in r.json()["detail"].lower()

    # Allocate 1 unit -> succeeds
    r1 = client.post(f"/api/requests/{rid}/allocations", json={
        "candidate_type": "donor", "candidate_id": did, "units": 1
    })
    assert r1.status_code == 201
    assert r1.json()["allocated_units"] == 1
    assert r1.json()["request_status"] == "partially_fulfilled"

    # Attempt second allocation to same donor on same request -> rejected
    r2 = client.post(f"/api/requests/{rid}/allocations", json={
        "candidate_type": "donor", "candidate_id": did, "units": 1
    })
    assert r2.status_code == 422
    assert "already has an active allocation" in r2.json()["detail"].lower()


def test_multiple_donors_fulfillment(client, app, payload):
    p = dict(payload, units_required=2)
    rid = client.post("/api/requests", json=p).json()["id"]

    donors = client.get("/api/donors").json()
    consented = [
        d for d in donors
        if d["consent_status"] == "consented_demo"
        and d["blood_group"] in ("O+", "O-")
        and d["availability_status"] in ("reported_available", "confirmed_available")
    ]
    assert len(consented) >= 2
    d1, d2 = consented[0]["id"], consented[1]["id"]

    confirm_candidate(client, rid, "donor", d1)
    confirm_candidate(client, rid, "donor", d2)

    # Allocate first donor -> partially fulfilled
    a1 = client.post(f"/api/requests/{rid}/allocations", json={"candidate_type": "donor", "candidate_id": d1, "units": 1})
    assert a1.status_code == 201
    assert a1.json()["request_status"] == "partially_fulfilled"
    assert a1.json()["remaining_units"] == 1

    # Allocate second donor -> fulfilled
    a2 = client.post(f"/api/requests/{rid}/allocations", json={"candidate_type": "donor", "candidate_id": d2, "units": 1})
    assert a2.status_code == 201
    assert a2.json()["request_status"] == "fulfilled"
    assert a2.json()["remaining_units"] == 0

    req_data = client.get(f"/api/requests/{rid}").json()
    assert req_data["status"] == "fulfilled"
    assert req_data["allocated_units"] == 2
    assert req_data["remaining_units"] == 0


def test_over_allocation_rejected(client, created):
    rid = created["id"]  # requires 2 units
    top = recs(client, rid)["current"]["ranked"][0]
    confirm_candidate(client, rid, top["candidate_type"], top["candidate_id"])

    # Attempt to allocate 3 units for a request needing 2 -> rejected
    r = client.post(f"/api/requests/{rid}/allocations", json={
        "candidate_type": top["candidate_type"], "candidate_id": top["candidate_id"], "units": 3
    })
    assert r.status_code == 422
    assert "only requires" in r.json()["detail"].lower()


def test_allocation_to_closed_or_cancelled_request_rejected(client, created):
    rid = created["id"]
    top = recs(client, rid)["current"]["ranked"][0]
    confirm_candidate(client, rid, top["candidate_type"], top["candidate_id"])

    # Cancel request
    cancel_resp = client.patch(f"/api/requests/{rid}/status", json={"status": "cancelled", "reason": "Patient transferred"})
    assert cancel_resp.status_code == 200

    # Try to allocate -> rejected
    r = client.post(f"/api/requests/{rid}/allocations", json={
        "candidate_type": top["candidate_type"], "candidate_id": top["candidate_id"], "units": 1
    })
    assert r.status_code == 422
    assert "cannot allocate" in r.json()["detail"].lower()


def test_shared_inventory_reservation_and_release(client, app, payload):
    # Find a blood bank with a known stock amount
    with app.state.session_factory() as db:
        bank = db.scalar(select(BloodBank).where(
            BloodBank.blood_group == "O+",
            BloodBank.component == "Packed Red Cells",
            BloodBank.units_available >= 5,
        ))
        assert bank is not None
        bank_id = bank.id
        initial_stock = bank.units_available

    # Request A: requires 3 units
    req_a = client.post("/api/requests", json=dict(payload, units_required=3)).json()["id"]
    # Request B: requires 3 units
    req_b = client.post("/api/requests", json=dict(payload, units_required=3)).json()["id"]

    confirm_candidate(client, req_a, "blood_bank", bank_id)
    confirm_candidate(client, req_b, "blood_bank", bank_id)

    # Allocate 3 units to Request A -> leaves initial_stock - 3
    resp_a = client.post(f"/api/requests/{req_a}/allocations", json={
        "candidate_type": "blood_bank", "candidate_id": bank_id, "units": 3
    })
    assert resp_a.status_code == 201
    alloc_a_id = resp_a.json()["allocation"]["id"]

    # Now Request B attempts to allocate 3 units
    with app.state.session_factory() as db:
        from app.services.allocations import get_bank_stock_info
        info = get_bank_stock_info(db, bank_id)
        assert info["active_reserved_units"] == 3
        assert info["available_to_allocate"] == initial_stock - 3

    # If we request more than available:
    too_much = info["available_to_allocate"] + 1
    req_c = client.post("/api/requests", json=dict(payload, units_required=too_much)).json()["id"]
    confirm_candidate(client, req_c, "blood_bank", bank_id)
    fail_resp = client.post(f"/api/requests/{req_c}/allocations", json={
        "candidate_type": "blood_bank", "candidate_id": bank_id, "units": too_much
    })
    assert fail_resp.status_code == 422
    assert "insufficient stock" in fail_resp.json()["detail"].lower()

    # Releasing Request A's allocation frees stock
    rel_resp = client.post(f"/api/requests/{req_a}/allocations/{alloc_a_id}/release", json={"reason": "Transfer cancelled"})
    assert rel_resp.status_code == 200
    assert rel_resp.json()["request_status"] == "awaiting_confirmation"
    assert rel_resp.json()["allocated_units"] == 0

    with app.state.session_factory() as db:
        from app.services.allocations import get_bank_stock_info
        info_after = get_bank_stock_info(db, bank_id)
        assert info_after["active_reserved_units"] == 0
        assert info_after["available_to_allocate"] == initial_stock


def test_candidate_event_releases_active_allocation(client, created):
    rid = created["id"]
    top = recs(client, rid)["current"]["ranked"][0]
    confirm_candidate(client, rid, top["candidate_type"], top["candidate_id"])

    # Allocate 1 unit (request needs 2)
    alloc = client.post(f"/api/requests/{rid}/allocations", json={
        "candidate_type": top["candidate_type"], "candidate_id": top["candidate_id"], "units": 1
    })
    assert alloc.status_code == 201
    assert alloc.json()["request_status"] == "partially_fulfilled"

    # Candidate reports stock unavailable or declines
    event_type = "STOCK_UNAVAILABLE" if top["candidate_type"] == "blood_bank" else "DONOR_DECLINED"
    ev = post_event(client, rid, event_type, top["candidate_type"], top["candidate_id"])
    assert ev.status_code == 201

    # Allocation should have been automatically released
    req_after = client.get(f"/api/requests/{rid}").json()
    assert req_after["allocated_units"] == 0
    assert req_after["status"] == "awaiting_confirmation"

    timeline = client.get(f"/api/requests/{rid}/timeline").json()
    assert any(e["event_type"] == "ALLOCATION_RELEASED" for e in timeline)


def test_idempotency_key_behavior(client, created):
    rid = created["id"]
    top = recs(client, rid)["current"]["ranked"][0]
    confirm_candidate(client, rid, top["candidate_type"], top["candidate_id"])

    # First call with idempotency key
    r1 = client.post(f"/api/requests/{rid}/allocations", json={
        "candidate_type": top["candidate_type"],
        "candidate_id": top["candidate_id"],
        "units": 1,
        "idempotency_key": "IDEM-KEY-001"
    })
    assert r1.status_code == 201
    alloc_id = r1.json()["allocation"]["id"]

    # Replay with same idempotency key and same payload
    r2 = client.post(f"/api/requests/{rid}/allocations", json={
        "candidate_type": top["candidate_type"],
        "candidate_id": top["candidate_id"],
        "units": 1,
        "idempotency_key": "IDEM-KEY-001"
    })
    assert r2.status_code == 201
    assert r2.json()["allocation"]["id"] == alloc_id
    assert r2.json()["allocated_units"] == 1  # Not double-allocated!

    # Replay with same key but different payload -> rejected
    r3 = client.post(f"/api/requests/{rid}/allocations", json={
        "candidate_type": top["candidate_type"],
        "candidate_id": top["candidate_id"],
        "units": 2,
        "idempotency_key": "IDEM-KEY-001"
    })
    assert r3.status_code == 422
    assert "different allocation parameters" in r3.json()["detail"].lower()


def test_request_cancellation_releases_all_reservations(client, created):
    rid = created["id"]
    top = recs(client, rid)["current"]["ranked"][0]
    confirm_candidate(client, rid, top["candidate_type"], top["candidate_id"])

    # Allocate 1 unit
    alloc = client.post(f"/api/requests/{rid}/allocations", json={
        "candidate_type": top["candidate_type"], "candidate_id": top["candidate_id"], "units": 1
    })
    assert alloc.status_code == 201

    # Cancel request
    cancel = client.patch(f"/api/requests/{rid}/status", json={
        "status": "cancelled", "reason": "Patient condition resolved"
    })
    assert cancel.status_code == 200

    # Verify allocation is released
    allocs = client.get(f"/api/requests/{rid}/allocations").json()
    assert len(allocs) == 1
    assert allocs[0]["status"] == "released"
