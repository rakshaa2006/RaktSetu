"""Blood request approval workflows.

Manages targeted blood bank inboxes, explicit review decisions (approval / rejection),
database-level atomic concurrency synchronization, transaction integrity, and audit history.

IMPORTANT:
Approval is an administrative review decision confirming willingness to process
the request. Approval does NOT reserve or allocate stock, issue units, or fulfill
the request.
"""
from __future__ import annotations

import threading
from typing import List, Optional

from sqlalchemy import case, select, update
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, ForbiddenError, NotFoundError, RuleViolation
from app.database import utcnow
from app.models.models import BloodBank, BloodRequest
from app.services import allocations, audit, coordination

# Fast-path in-memory lock for thread-based single-process deployments
_decision_lock = threading.Lock()


def get_inbox_requests(
    db: Session,
    bank_id: str,
    status: Optional[str] = None,
    approval_status: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> List[BloodRequest]:
    """Retrieve blood requests targeted to a specific blood bank."""
    stmt = (
        select(BloodRequest)
        .where(BloodRequest.target_blood_bank_id == bank_id)
        .order_by(BloodRequest.created_at.desc(), BloodRequest.id)
    )
    if status:
        stmt = stmt.where(BloodRequest.status == status)
    if approval_status:
        stmt = stmt.where(BloodRequest.approval_status == approval_status)
    if offset > 0:
        stmt = stmt.offset(offset)
    if limit > 0:
        stmt = stmt.limit(limit)

    rows = list(db.scalars(stmt))
    for r in rows:
        r.allocated_units = allocations.get_allocated_units(db, r.id)
    return rows


def approve_request(
    db: Session,
    request_id: str,
    acting_bank_id: str,
) -> BloodRequest:
    """Approve a targeted blood request.

    Concurrency strategy:
    - Uses an atomic conditional database UPDATE filtered by request_id, acting_bank_id,
      and approval_status == 'pending'.
    - Multi-process / multi-session safe: the database update is atomic; losing or repeated
      attempts update 0 rows and return 409 Conflict.
    - An in-memory lock is also held as a fast-path for intra-process concurrency.
    - Transaction integrity: the request status change, audit event, and ranking snapshot
      all participate in the same database transaction. If any step fails, the entire transaction
      is rolled back so that no partial or orphaned state is committed.
    """
    now = utcnow()
    with _decision_lock:
        try:
            stmt = (
                update(BloodRequest)
                .where(
                    BloodRequest.id == request_id,
                    BloodRequest.target_blood_bank_id == acting_bank_id,
                    BloodRequest.approval_status == "pending",
                )
                .values(
                    approval_status="approved",
                    decided_at=now,
                    decided_by_bank_id=acting_bank_id,
                    updated_at=now,
                    status=case(
                        (BloodRequest.status == "open", "under_review"),
                        else_=BloodRequest.status,
                    ),
                )
            )
            result = db.execute(stmt)

            if result.rowcount == 0:
                db.rollback()
                req = db.get(BloodRequest, request_id)
                if req is None:
                    raise NotFoundError(f"Blood request '{request_id}' was not found.")
                if req.target_blood_bank_id != acting_bank_id:
                    raise ForbiddenError(
                        f"Forbidden: Request '{request_id}' is targeted to '{req.target_blood_bank_id}', not '{acting_bank_id}'."
                    )
                if req.approval_status != "pending":
                    current = req.approval_status or "unassigned"
                    raise ConflictError(
                        f"Cannot approve request '{request_id}': decision has already been recorded (status: '{current}')."
                    )
                raise ConflictError(
                    f"Cannot approve request '{request_id}': request is not in a pending state."
                )

            # Synchronize ORM state in session
            req = db.get(BloodRequest, request_id)
            if req:
                db.refresh(req)
            assert req is not None

            audit.record_event(
                db,
                request_id=req.id,
                event_type="REQUEST_APPROVED",
                reason=f"Blood request approved by blood bank '{acting_bank_id}'.",
                candidate_type="blood_bank",
                candidate_id=acting_bank_id,
                previous_state="pending",
                new_state="approved",
            )

            coordination.generate_snapshot(db, req, trigger="Request approved by blood bank")
            db.commit()

            req.allocated_units = allocations.get_allocated_units(db, req.id)
            return req

        except Exception:
            db.rollback()
            raise


def reject_request(
    db: Session,
    request_id: str,
    acting_bank_id: str,
    reason: str,
) -> BloodRequest:
    """Reject a targeted blood request with a required bounded reason.

    Concurrency strategy:
    - Uses an atomic conditional database UPDATE filtered by request_id, acting_bank_id,
      and approval_status == 'pending'.
    - Multi-process / multi-session safe: the database update is atomic; losing or repeated
      attempts update 0 rows and return 409 Conflict.
    - An in-memory lock is also held as a fast-path for intra-process concurrency.
    - Transaction integrity: the request status change, audit event, and ranking snapshot
      all participate in the same database transaction. If any step fails, the entire transaction
      is rolled back so that no partial or orphaned state is committed.
    """
    trimmed_reason = reason.strip() if reason else ""
    if len(trimmed_reason) < 5 or len(trimmed_reason) > 300:
        raise RuleViolation("Rejection reason must be between 5 and 300 characters.")

    now = utcnow()
    with _decision_lock:
        try:
            stmt = (
                update(BloodRequest)
                .where(
                    BloodRequest.id == request_id,
                    BloodRequest.target_blood_bank_id == acting_bank_id,
                    BloodRequest.approval_status == "pending",
                )
                .values(
                    approval_status="rejected",
                    rejection_reason=trimmed_reason,
                    decided_at=now,
                    decided_by_bank_id=acting_bank_id,
                    updated_at=now,
                )
            )
            result = db.execute(stmt)

            if result.rowcount == 0:
                db.rollback()
                req = db.get(BloodRequest, request_id)
                if req is None:
                    raise NotFoundError(f"Blood request '{request_id}' was not found.")
                if req.target_blood_bank_id != acting_bank_id:
                    raise ForbiddenError(
                        f"Forbidden: Request '{request_id}' is targeted to '{req.target_blood_bank_id}', not '{acting_bank_id}'."
                    )
                if req.approval_status != "pending":
                    current = req.approval_status or "unassigned"
                    raise ConflictError(
                        f"Cannot reject request '{request_id}': decision has already been recorded (status: '{current}')."
                    )
                raise ConflictError(
                    f"Cannot reject request '{request_id}': request is not in a pending state."
                )

            req = db.get(BloodRequest, request_id)
            if req:
                db.refresh(req)
            assert req is not None

            audit.record_event(
                db,
                request_id=req.id,
                event_type="REQUEST_REJECTED",
                reason=f"Blood request rejected by blood bank '{acting_bank_id}': {trimmed_reason}",
                candidate_type="blood_bank",
                candidate_id=acting_bank_id,
                previous_state="pending",
                new_state="rejected",
            )

            coordination.generate_snapshot(db, req, trigger="Request rejected by blood bank")
            db.commit()

            req.allocated_units = allocations.get_allocated_units(db, req.id)
            return req

        except Exception:
            db.rollback()
            raise
