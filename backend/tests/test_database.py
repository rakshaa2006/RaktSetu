from pathlib import Path

from sqlalchemy import func, inspect, select

from app.database import init_db, make_engine, make_session_factory
from app.models import BloodBank, BloodRequest, Donor
from app.services.seed import seed_database
from tests.conftest import DATA_DIR


def test_database_initialisation_creates_all_tables(tmp_path):
    engine = make_engine(f"sqlite:///{(tmp_path / 'x.db').as_posix()}")
    init_db(engine)
    init_db(engine)  # safe to repeat
    tables = set(inspect(engine).get_table_names())
    assert {"blood_requests", "blood_banks", "donors", "candidate_states", "ranking_snapshots",
            "audit_events", "allocations"} <= tables


def test_seeding_is_idempotent(tmp_path):
    engine = make_engine(f"sqlite:///{(tmp_path / 'x.db').as_posix()}")
    init_db(engine)
    factory = make_session_factory(engine)
    with factory() as db:
        first = seed_database(db, DATA_DIR)
        second = seed_database(db, DATA_DIR)
        assert first.banks_added >= 10 and first.donors_added >= 20
        assert second.banks_added == 0 and second.donors_added == 0
        assert db.scalar(select(func.count()).select_from(BloodBank)) == first.banks_added
        assert db.scalar(select(func.count()).select_from(Donor)) == first.donors_added


def test_reseeding_keeps_request_history(client, created, app):
    with app.state.session_factory() as db:
        seed_database(db, DATA_DIR)
        assert db.get(BloodRequest, created["id"]) is not None


def test_demo_data_meets_minimum_variety(app):
    with app.state.session_factory() as db:
        banks = list(db.scalars(select(BloodBank)))
        donors = list(db.scalars(select(Donor)))
    assert len(banks) >= 10 and len(donors) >= 20
    assert any(b.latitude is None for b in banks) and any(d.latitude is None for d in donors)
    assert any(b.last_updated is None for b in banks)
    assert {"confirmed_available", "unverified", "unavailable", "reported_available"} <= {b.availability_status for b in banks}
    assert {"declined_recently", "no_recent_response"} <= {d.response_status for d in donors}
    assert all(b.is_simulated for b in banks) and all(d.is_simulated for d in donors)
