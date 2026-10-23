"""SQLite engine/session helpers (SQLAlchemy 2.0). All timestamps are stored as UTC."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import Request
from sqlalchemy import DateTime, create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy.types import TypeDecorator


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class UTCDateTime(TypeDecorator):
    """Stores naive UTC in SQLite, always returns timezone-aware UTC."""

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).replace(tzinfo=None)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return value.replace(tzinfo=timezone.utc)


class Base(DeclarativeBase):
    pass


def make_engine(url: str) -> Engine:
    kwargs = {}
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
        if url in ("sqlite://", "sqlite:///:memory:"):
            kwargs["poolclass"] = StaticPool
    engine = create_engine(url, **kwargs)
    if url.startswith("sqlite"):
        @event.listens_for(engine, "connect")
        def _fk_on(dbapi_conn, _):  # enforce foreign keys in SQLite
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA foreign_keys=ON")
            cur.close()
    return engine


def make_session_factory(engine: Engine) -> sessionmaker:
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, class_=Session)


def _migrate_db(engine: Engine) -> None:
    """Safely and idempotently add missing columns and indexes to existing SQLite tables."""
    with engine.connect() as conn:
        res = conn.exec_driver_sql(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='blood_requests'"
        ).fetchone()
        if res:
            cursor = conn.exec_driver_sql("PRAGMA table_info(blood_requests)")
            existing_cols = {row[1] for row in cursor.fetchall()}
            cols_to_add = [
                ("target_blood_bank_id", "VARCHAR(32) REFERENCES blood_banks(id) ON DELETE SET NULL"),
                ("approval_status", "VARCHAR(16)"),
                ("rejection_reason", "TEXT"),
                ("decided_at", "DATETIME"),
                ("decided_by_bank_id", "VARCHAR(32)"),
            ]
            for col_name, col_type in cols_to_add:
                if col_name not in existing_cols:
                    conn.exec_driver_sql(f"ALTER TABLE blood_requests ADD COLUMN {col_name} {col_type}")

            conn.exec_driver_sql(
                "CREATE INDEX IF NOT EXISTS ix_request_target_bank ON blood_requests (target_blood_bank_id)"
            )
            conn.exec_driver_sql(
                "CREATE INDEX IF NOT EXISTS ix_request_approval_status ON blood_requests (approval_status)"
            )
            conn.commit()


def init_db(engine: Engine) -> None:
    """Safe to call repeatedly: creates missing tables and columns."""
    from app.models import models  # noqa: F401  (registers the tables)
    Base.metadata.create_all(engine)
    if engine.dialect.name == "sqlite":
        _migrate_db(engine)


def get_db(request: Request):
    db = request.app.state.session_factory()
    try:
        yield db
    finally:
        db.close()
