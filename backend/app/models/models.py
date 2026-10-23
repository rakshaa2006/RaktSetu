"""SQLAlchemy tables."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import (JSON, Boolean, CheckConstraint, Float, ForeignKey, Index, Integer, String, Text,
                        UniqueConstraint)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base, UTCDateTime, utcnow


class BloodBank(Base):
    __tablename__ = "blood_banks"
    __table_args__ = (
        CheckConstraint("units_available >= 0", name="ck_bank_units_nonneg"),
        Index("ix_bank_group_component", "blood_group", "component"),
    )
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    location: Mapped[str] = mapped_column(String(120))
    latitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    longitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    blood_group: Mapped[str] = mapped_column(String(3))
    component: Mapped[str] = mapped_column(String(32))
    units_available: Mapped[int] = mapped_column(Integer, default=0)
    availability_status: Mapped[str] = mapped_column(String(32))
    # ISO-8601 text on purpose: lets the demo include missing/invalid timestamps safely.
    last_updated: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    data_source: Mapped[str] = mapped_column(String(160), default="")
    is_simulated: Mapped[bool] = mapped_column(Boolean, default=True)


class Donor(Base):
    __tablename__ = "donors"
    __table_args__ = (Index("ix_donor_group", "blood_group"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(80))
    blood_group: Mapped[str] = mapped_column(String(3))
    location: Mapped[str] = mapped_column(String(120))
    latitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    longitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    consent_status: Mapped[str] = mapped_column(String(32))
    availability_status: Mapped[str] = mapped_column(String(32))
    response_status: Mapped[str] = mapped_column(String(32))
    last_updated: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    data_source: Mapped[str] = mapped_column(String(160), default="")
    is_simulated: Mapped[bool] = mapped_column(Boolean, default=True)


class BloodRequest(Base):
    __tablename__ = "blood_requests"
    __table_args__ = (
        CheckConstraint("patient_age >= 0 AND patient_age <= 120", name="ck_request_age"),
        CheckConstraint("units_required >= 1", name="ck_request_units"),
        Index("ix_request_status", "status"),
        Index("ix_request_created", "created_at"),
    )
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    patient_name: Mapped[str] = mapped_column(String(100))
    patient_age: Mapped[int] = mapped_column(Integer)
    patient_gender: Mapped[str] = mapped_column(String(24))
    patient_blood_group: Mapped[str] = mapped_column(String(3))
    component: Mapped[str] = mapped_column(String(32))
    units_required: Mapped[int] = mapped_column(Integer)
    hospital_name: Mapped[str] = mapped_column(String(120))
    hospital_location: Mapped[str] = mapped_column(String(120))
    hospital_latitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    hospital_longitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    urgency: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(32), default="open")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    @property
    def allocated_units(self) -> int:
        return getattr(self, "_allocated_units", 0)

    @allocated_units.setter
    def allocated_units(self, value: int) -> None:
        self._allocated_units = value

    @property
    def remaining_units(self) -> int:
        return max(0, self.units_required - self.allocated_units)


class CandidateState(Base):
    """Request-specific state of one blood bank or donor."""
    __tablename__ = "candidate_states"
    __table_args__ = (
        UniqueConstraint("request_id", "candidate_type", "candidate_id", name="uq_candidate_per_request"),
        Index("ix_candidate_request", "request_id"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    request_id: Mapped[str] = mapped_column(ForeignKey("blood_requests.id", ondelete="CASCADE"))
    candidate_type: Mapped[str] = mapped_column(String(16))
    candidate_id: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(32))
    reason: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class RankingSnapshot(Base):
    """Every ranking ever produced for a request. Never overwritten."""
    __tablename__ = "ranking_snapshots"
    __table_args__ = (UniqueConstraint("request_id", "version", name="uq_snapshot_version"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    request_id: Mapped[str] = mapped_column(ForeignKey("blood_requests.id", ondelete="CASCADE"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    trigger: Mapped[str] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    payload: Mapped[dict] = mapped_column(JSON)


class AuditEvent(Base):
    """Append-only (at application level) event history."""
    __tablename__ = "audit_events"
    __table_args__ = (Index("ix_audit_request_seq", "request_id", "seq"),)
    seq: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_id: Mapped[str] = mapped_column(String(24), unique=True)
    request_id: Mapped[str] = mapped_column(ForeignKey("blood_requests.id", ondelete="CASCADE"))
    event_type: Mapped[str] = mapped_column(String(48))
    timestamp: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    candidate_type: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    candidate_id: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    previous_state: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    new_state: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    reason: Mapped[str] = mapped_column(Text)
    is_simulation: Mapped[bool] = mapped_column(Boolean, default=True)


class Allocation(Base):
    """Persisted unit allocation with lifecycle, stock reservation, and idempotency."""
    __tablename__ = "allocations"
    __table_args__ = (
        CheckConstraint("units >= 1", name="ck_allocation_units_pos"),
        CheckConstraint("candidate_type IN ('blood_bank', 'donor')", name="ck_allocation_candidate_type"),
        CheckConstraint("status IN ('active', 'released')", name="ck_allocation_status"),
        CheckConstraint("candidate_type != 'donor' OR units = 1", name="ck_donor_single_unit"),
        Index("ix_allocation_request", "request_id"),
        Index("ix_allocation_candidate", "candidate_type", "candidate_id", "status"),
        Index("ix_allocation_idempotency", "request_id", "idempotency_key"),
    )
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    request_id: Mapped[str] = mapped_column(ForeignKey("blood_requests.id", ondelete="CASCADE"))
    candidate_type: Mapped[str] = mapped_column(String(16))
    candidate_id: Mapped[str] = mapped_column(String(32))
    units: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(32), default="active")
    idempotency_key: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    payload_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
