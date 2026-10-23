"""Allocation and shared inventory reservation workflows.

Persists allocations atomically with inventory reservations, fulfillment updates,
and audit events. Shared blood-bank inventory is enforced across all active requests.
"""
from __future__ import annotations

import hashlib
import threading
import uuid
from typing import Dict, List, Optional, Tuple

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.core.errors import InvalidTransition, NotFoundError, RuleViolation
from app.core.rules import match_blood, validate_request_transition
from app.database import utcnow
from app.models.models import Allocation, BloodBank, BloodRequest, CandidateState, Donor
from app.services.audit import record_event

_allocation_lock = threading.Lock()


def get_allocated_units(db: Session, request_id: str) -> int:
    """Sum of all active allocated units for a given blood request."""
    total = db.scalar(
        select(func.sum(Allocation.units)).where(
            Allocation.request_id == request_id,
            Allocation.status == "active",
        )
    )
    return int(total or 0)


def get_active_allocations(db: Session, request_id: str) -> List[Allocation]:
    """Retrieve all active allocations for a request, ordered chronologically."""
    return list(
        db.scalars(
            select(Allocation)
            .where(Allocation.request_id == request_id, Allocation.status == "active")
            .order_by(Allocation.created_at.asc(), Allocation.id.asc())
        )
    )


def get_all_allocations(db: Session, request_id: str) -> List[Allocation]:
    """Retrieve all allocations (active and released) for a request."""
    return list(
        db.scalars(
            select(Allocation)
            .where(Allocation.request_id == request_id)
            .order_by(Allocation.created_at.asc(), Allocation.id.asc())
        )
    )


def get_bank_stock_info(db: Session, bank_id: str) -> Dict[str, int]:
    """Compute usable stock, active reservations across all requests, and available units."""
    bank = db.get(BloodBank, bank_id)
    if bank is None:
        raise NotFoundError(f"Blood bank '{bank_id}' was not found.")

    usable_stock = 0 if bank.availability_status == "unavailable" else max(0, bank.units_available)
    reserved = db.scalar(
        select(func.sum(Allocation.units)).where(
            Allocation.candidate_type == "blood_bank",
            Allocation.candidate_id == bank_id,
            Allocation.status == "active",
        )
    )
    active_reserved = int(reserved or 0)
    available_to_allocate = max(0, usable_stock - active_reserved)
    return {
        "usable_stock": usable_stock,
        "active_reserved_units": active_reserved,
        "available_to_allocate": available_to_allocate,
    }


def _hash_payload(candidate_type: str, candidate_id: str, units: int) -> str:
    raw = f"{candidate_type.strip()}:{candidate_id.strip()}:{int(units)}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def create_allocation(
    db: Session,
    request_id: str,
    candidate_type: str,
    candidate_id: str,
    units: int,
    idempotency_key: Optional[str] = None,
) -> Tuple[Allocation, BloodRequest]:
    """Atomically reserve stock and create an allocation.

    Enforces eligibility, blood matching, donor one-unit capacity, shared blood-bank
    inventory, request capacity, and request lifecycle transitions.
    """
    with _allocation_lock:
        if db.bind and db.bind.dialect.name == "sqlite":
            try:
                db.execute(text("BEGIN IMMEDIATE"))
            except Exception:
                pass

        req = db.get(BloodRequest, request_id)
        if req is None:
            raise NotFoundError(f"Blood request '{request_id}' was not found.")

        if req.status in ("fulfilled", "cancelled"):
            raise RuleViolation(f"Cannot allocate units to a {req.status} request.")

        if not isinstance(units, int) or units <= 0:
            raise RuleViolation("Allocated units must be a positive integer.")
        if units > 20:
            raise RuleViolation("Allocated units cannot exceed 20.")

        # Idempotency check
        if idempotency_key:
            idempotency_key = idempotency_key.strip()
            existing_key_alloc = db.scalar(
                select(Allocation).where(
                    Allocation.request_id == req.id,
                    Allocation.idempotency_key == idempotency_key,
                )
            )
            if existing_key_alloc is not None:
                current_hash = _hash_payload(candidate_type, candidate_id, units)
                if existing_key_alloc.payload_hash == current_hash:
                    # Idempotent retry: return existing allocation and current request state
                    req.allocated_units = get_allocated_units(db, req.id)
                    return existing_key_alloc, req
                raise RuleViolation(
                    f"Idempotency key '{idempotency_key}' was already used with different allocation parameters."
                )

        if candidate_type not in ("blood_bank", "donor"):
            raise RuleViolation(f"Invalid candidate type '{candidate_type}'.")

        # Verify candidate exists
        if candidate_type == "blood_bank":
            candidate = db.get(BloodBank, candidate_id)
        else:
            candidate = db.get(Donor, candidate_id)
        if candidate is None:
            raise NotFoundError(
                f"No {candidate_type.replace('_', ' ')} with ID '{candidate_id}' exists."
            )

        # Blood matching compatibility
        match_result = match_blood(req.patient_blood_group, candidate.blood_group, req.component)
        if match_result.level == "none":
            raise RuleViolation(
                f"Candidate {candidate_id} ({candidate.blood_group}) is not compatible with patient "
                f"({req.patient_blood_group}) for {req.component}."
            )

        if candidate_type == "blood_bank":
            if candidate.component != req.component:
                raise RuleViolation(
                    f"Blood bank {candidate_id} component '{candidate.component}' does not match "
                    f"requested component '{req.component}'."
                )

        # Candidate must be confirmed available for this request
        state_row = db.scalar(
            select(CandidateState).where(
                CandidateState.request_id == req.id,
                CandidateState.candidate_type == candidate_type,
                CandidateState.candidate_id == candidate_id,
            )
        )
        if state_row is None or state_row.status != "confirmed_available":
            raise RuleViolation(
                f"Option {candidate_id} must be confirmed available for this request before allocating units."
            )

        # Candidate-specific rules
        if candidate_type == "donor":
            if candidate.consent_status != "consented_demo":
                raise RuleViolation("Verified donor consent is required before allocating donor units.")
            if units != 1:
                raise RuleViolation("A donor can contribute at most one unit.")
            existing_donor_alloc = db.scalar(
                select(Allocation).where(
                    Allocation.request_id == req.id,
                    Allocation.candidate_type == "donor",
                    Allocation.candidate_id == candidate_id,
                    Allocation.status == "active",
                )
            )
            if existing_donor_alloc is not None:
                raise RuleViolation(
                    f"Donor {candidate_id} already has an active allocation for this request."
                )
        else:
            stock_info = get_bank_stock_info(db, candidate_id)
            available = stock_info["available_to_allocate"]
            if units > available:
                raise RuleViolation(
                    f"Insufficient stock for blood bank {candidate_id}: requested {units} unit(s), "
                    f"but only {available} unit(s) available considering active reservations."
                )

        # Request capacity check
        current_allocated = get_allocated_units(db, req.id)
        remaining_needed = req.units_required - current_allocated
        if units > remaining_needed:
            raise RuleViolation(
                f"Cannot allocate {units} unit(s): request only requires {remaining_needed} more unit(s) "
                f"({current_allocated}/{req.units_required} currently allocated)."
            )

        # Persist allocation
        alloc_id = "ALL-" + uuid.uuid4().hex[:10].upper()
        now = utcnow()
        payload_hash = _hash_payload(candidate_type, candidate_id, units)
        allocation = Allocation(
            id=alloc_id,
            request_id=req.id,
            candidate_type=candidate_type,
            candidate_id=candidate_id,
            units=units,
            status="active",
            idempotency_key=idempotency_key,
            payload_hash=payload_hash,
            created_at=now,
            updated_at=now,
        )
        db.add(allocation)
        db.flush()

        # Update request status
        new_allocated = current_allocated + units
        req.allocated_units = new_allocated
        prev_status = req.status
        if new_allocated == req.units_required:
            req.status = "fulfilled"
        elif new_allocated > 0:
            req.status = "partially_fulfilled"
        req.updated_at = now

        # Audit event
        display_name = candidate.name if candidate_type == "blood_bank" else candidate.display_name
        record_event(
            db,
            req.id,
            "UNITS_ALLOCATED",
            f"Allocated {units} unit(s) from {candidate_type.replace('_', ' ')} {display_name} ({candidate_id}). "
            f"Total allocated: {new_allocated}/{req.units_required} unit(s).",
            candidate_type=candidate_type,
            candidate_id=candidate_id,
            previous_state=prev_status,
            new_state=req.status,
            is_simulation=True,
        )

        if req.status != prev_status:
            record_event(
                db,
                req.id,
                "REQUEST_STATUS_UPDATED",
                f"Request status changed from {prev_status} to {req.status}. This is a simulated coordinator action, not a real medical transaction.",
                previous_state=prev_status,
                new_state=req.status,
                is_simulation=True,
            )

        db.commit()
        return allocation, req


def release_allocation(
    db: Session,
    request_id: str,
    allocation_id: str,
    reason: Optional[str] = None,
) -> Tuple[Allocation, BloodRequest]:
    """Release an active allocation and recompute request fulfillment status."""
    with _allocation_lock:
        if db.bind and db.bind.dialect.name == "sqlite":
            try:
                db.execute(text("BEGIN IMMEDIATE"))
            except Exception:
                pass

        req = db.get(BloodRequest, request_id)
        if req is None:
            raise NotFoundError(f"Blood request '{request_id}' was not found.")

        allocation = db.get(Allocation, allocation_id)
        if allocation is None or allocation.request_id != req.id:
            raise NotFoundError(f"Allocation '{allocation_id}' was not found for this request.")

        if allocation.status == "released":
            raise RuleViolation(f"Allocation '{allocation_id}' has already been released.")

        allocation.status = "released"
        now = utcnow()
        allocation.updated_at = now
        db.flush()

        # Recompute fulfillment
        new_allocated = get_allocated_units(db, req.id)
        req.allocated_units = new_allocated
        prev_status = req.status

        if req.status != "cancelled":
            if new_allocated == 0:
                req.status = "awaiting_confirmation"
            elif new_allocated < req.units_required:
                req.status = "partially_fulfilled"
            else:
                req.status = "fulfilled"
        req.updated_at = now

        note = f" Note: {reason.strip()}" if reason and reason.strip() else ""
        record_event(
            db,
            req.id,
            "ALLOCATION_RELEASED",
            f"Released {allocation.units} unit(s) previously allocated to {allocation.candidate_id}. "
            f"Remaining allocated: {new_allocated}/{req.units_required} unit(s).{note}",
            candidate_type=allocation.candidate_type,
            candidate_id=allocation.candidate_id,
            previous_state=prev_status,
            new_state=req.status,
            is_simulation=True,
        )

        db.commit()
        return allocation, req


def release_allocations_for_candidate(
    db: Session,
    request_id: str,
    candidate_type: str,
    candidate_id: str,
    reason: str,
) -> int:
    """Release all active allocations for a candidate when that candidate becomes unavailable/declined."""
    active_allocs = list(
        db.scalars(
            select(Allocation).where(
                Allocation.request_id == request_id,
                Allocation.candidate_type == candidate_type,
                Allocation.candidate_id == candidate_id,
                Allocation.status == "active",
            )
        )
    )
    if not active_allocs:
        return 0

    now = utcnow()
    released_units = 0
    for alloc in active_allocs:
        alloc.status = "released"
        alloc.updated_at = now
        released_units += alloc.units
    db.flush()

    req = db.get(BloodRequest, request_id)
    if req:
        new_allocated = get_allocated_units(db, req.id)
        req.allocated_units = new_allocated
        prev_status = req.status
        if req.status != "cancelled":
            if new_allocated == 0:
                req.status = "awaiting_confirmation"
            elif new_allocated < req.units_required:
                req.status = "partially_fulfilled"
            else:
                req.status = "fulfilled"
        req.updated_at = now

        record_event(
            db,
            req.id,
            "ALLOCATION_RELEASED",
            f"Automatically released {released_units} unit(s) from {candidate_type.replace('_', ' ')} "
            f"{candidate_id} due to status change: {reason}. Total allocated: {new_allocated}/{req.units_required} unit(s).",
            candidate_type=candidate_type,
            candidate_id=candidate_id,
            previous_state=prev_status,
            new_state=req.status,
            is_simulation=True,
        )
    return released_units


def release_all_request_allocations(db: Session, request_id: str, reason: str = "") -> int:
    """Release all active allocations when a request is cancelled."""
    active_allocs = list(
        db.scalars(
            select(Allocation).where(
                Allocation.request_id == request_id,
                Allocation.status == "active",
            )
        )
    )
    if not active_allocs:
        return 0

    now = utcnow()
    total_released = 0
    for alloc in active_allocs:
        alloc.status = "released"
        alloc.updated_at = now
        total_released += alloc.units
    db.flush()

    note = f" Reason: {reason.strip()}" if reason and reason.strip() else ""
    record_event(
        db,
        request_id,
        "ALLOCATIONS_CANCELLED",
        f"Released all {total_released} allocated unit(s) due to request cancellation.{note}",
        is_simulation=True,
    )
    return total_released
