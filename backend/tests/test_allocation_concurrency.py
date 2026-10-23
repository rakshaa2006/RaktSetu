"""Deterministic inventory concurrency stress tests."""
from concurrent.futures import ThreadPoolExecutor, as_completed
import pytest
from sqlalchemy import select

from app.models.models import BloodBank
from app.services.allocations import get_bank_stock_info
from tests.conftest import post_event


def confirm_candidate(client, request_id, candidate_type, candidate_id):
    r_sel = post_event(client, request_id, "SELECT_FOR_REVIEW", candidate_type, candidate_id)
    assert r_sel.status_code == 201, r_sel.text
    r_conf = post_event(client, request_id, "CONFIRM_AVAILABILITY", candidate_type, candidate_id)
    assert r_conf.status_code == 201, r_conf.text


def test_concurrent_oversubscription_prevented(client, app, payload):
    """Required scenario:
    - Available inventory: 5 units.
    - Concurrent request A: allocate 4 units.
    - Concurrent request B: allocate 4 units.
    - Expected: both must NOT succeed (total 8 units). Exactly one succeeds.
    - Expected active reservation: <= 5 units.
    """
    # Setup blood bank with exactly 5 usable units
    with app.state.session_factory() as db:
        bank = db.scalar(select(BloodBank).where(
            BloodBank.blood_group == "O+",
            BloodBank.component == "Packed Red Cells",
        ))
        assert bank is not None
        bank_id = bank.id
        bank.units_available = 5
        db.commit()

    # Create Request A and Request B (each needing 4 units)
    req_a = client.post("/api/requests", json=dict(payload, units_required=4)).json()["id"]
    req_b = client.post("/api/requests", json=dict(payload, units_required=4)).json()["id"]

    confirm_candidate(client, req_a, "blood_bank", bank_id)
    confirm_candidate(client, req_b, "blood_bank", bank_id)

    def try_allocate(req_id):
        return client.post(f"/api/requests/{req_id}/allocations", json={
            "candidate_type": "blood_bank",
            "candidate_id": bank_id,
            "units": 4,
        })

    with ThreadPoolExecutor(max_workers=2) as executor:
        f_a = executor.submit(try_allocate, req_a)
        f_b = executor.submit(try_allocate, req_b)
        resp_a = f_a.result()
        resp_b = f_b.result()

    statuses = [resp_a.status_code, resp_b.status_code]
    # Exactly one must succeed (201) and one must fail with insufficient stock (422)
    assert statuses.count(201) == 1, f"Expected exactly one 201, got {statuses}"
    assert statuses.count(422) == 1, f"Expected exactly one 422, got {statuses}"

    failed_resp = resp_a if resp_a.status_code == 422 else resp_b
    assert "insufficient stock" in failed_resp.json()["detail"].lower()

    # Verify inventory invariant: sum(active_reservations) <= usable_stock
    with app.state.session_factory() as db:
        info = get_bank_stock_info(db, bank_id)
        assert info["active_reserved_units"] == 4
        assert info["usable_stock"] == 5
        assert info["available_to_allocate"] == 1
        assert info["active_reserved_units"] <= info["usable_stock"]


def test_high_contention_concurrent_allocations(client, app, payload):
    """Stress test: 10 concurrent requests competing for 5 available units."""
    with app.state.session_factory() as db:
        bank = db.scalar(select(BloodBank).where(
            BloodBank.blood_group == "O+",
            BloodBank.component == "Packed Red Cells",
        ))
        assert bank is not None
        bank_id = bank.id
        bank.units_available = 5
        db.commit()

    request_ids = []
    for _ in range(10):
        rid = client.post("/api/requests", json=dict(payload, units_required=2)).json()["id"]
        confirm_candidate(client, rid, "blood_bank", bank_id)
        request_ids.append(rid)

    def do_alloc(rid):
        return client.post(f"/api/requests/{rid}/allocations", json={
            "candidate_type": "blood_bank",
            "candidate_id": bank_id,
            "units": 2,
        })

    results = []
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {executor.submit(do_alloc, rid): rid for rid in request_ids}
        for f in as_completed(futures):
            results.append(f.result())

    successes = [r for r in results if r.status_code == 201]
    failures = [r for r in results if r.status_code == 422]

    # With 5 units total and requests for 2 units each:
    # At most 2 can succeed (4 units total). The 3rd would need 2 units (4+2=6 > 5) so must fail.
    assert len(successes) == 2, f"Expected 2 successes, got {len(successes)}"
    assert len(failures) == 8, f"Expected 8 failures, got {len(failures)}"

    with app.state.session_factory() as db:
        info = get_bank_stock_info(db, bank_id)
        assert info["active_reserved_units"] == 4
        assert info["active_reserved_units"] <= info["usable_stock"]
        assert info["available_to_allocate"] == 1


def test_repeated_concurrency_trials(client, app, payload):
    """Repeat concurrent competition trials to verify determinism and absence of race leaks."""
    for trial in range(5):
        with app.state.session_factory() as db:
            bank = db.scalar(select(BloodBank).where(
                BloodBank.blood_group == "O+",
                BloodBank.component == "Packed Red Cells",
            ))
            assert bank is not None
            bank_id = bank.id
            bank.units_available = 5
            db.commit()

        req_1 = client.post("/api/requests", json=dict(payload, units_required=3)).json()["id"]
        req_2 = client.post("/api/requests", json=dict(payload, units_required=3)).json()["id"]
        confirm_candidate(client, req_1, "blood_bank", bank_id)
        confirm_candidate(client, req_2, "blood_bank", bank_id)

        def alloc_call(rid):
            return client.post(f"/api/requests/{rid}/allocations", json={
                "candidate_type": "blood_bank",
                "candidate_id": bank_id,
                "units": 3,
            })

        with ThreadPoolExecutor(max_workers=2) as executor:
            f1 = executor.submit(alloc_call, req_1)
            f2 = executor.submit(alloc_call, req_2)
            r1, r2 = f1.result(), f2.result()

        codes = {r1.status_code, r2.status_code}
        assert codes == {201, 422}, f"Trial {trial}: expected {{201, 422}}, got {codes}"

        with app.state.session_factory() as db:
            info = get_bank_stock_info(db, bank_id)
            assert info["active_reserved_units"] <= 5
            # Release allocated units before next trial
            from app.models.models import Allocation
            allocs = list(db.scalars(select(Allocation).where(Allocation.candidate_id == bank_id, Allocation.status == "active")))
            for a in allocs:
                a.status = "released"
            db.commit()
