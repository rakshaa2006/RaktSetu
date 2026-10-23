"""Database-backed workflows: create request, rank, apply events, change status.

Every change and its audit event are written in the same transaction.
"""
from __future__ import annotations

import uuid
from typing import Dict, List, Optional, Tuple

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import InvalidTransition, NotFoundError, RuleViolation
from app.core.rules import (TERMINAL_REQUEST_STATUSES, derive_candidate_status, validate_request_transition)
from app.database import utcnow
from app.models import BloodBank, BloodRequest, CandidateState, Donor, RankingSnapshot
from app.schemas.schemas import RequestCreate
from app.services.audit import record_event
from app.services.allocations import (
    get_allocated_units,
    release_all_request_allocations,
    release_allocations_for_candidate,
)
from app.services.ranking import CandidateInput, Override, RequestInput, describe_changes, rank_candidates
from app.services.recovery import EVENT_RULES, plan_candidate_event


def get_request_or_404(db: Session, request_id: str) -> BloodRequest:
    req = db.get(BloodRequest, request_id)
    if req is None:
        raise NotFoundError(f"Blood request '{request_id}' was not found.")
    req.allocated_units = get_allocated_units(db, req.id)
    return req


def create_request(db: Session, payload: RequestCreate) -> BloodRequest:
    req = BloodRequest(
        id="REQ-" + uuid.uuid4().hex[:8].upper(),
        patient_name=payload.patient_name, patient_age=payload.patient_age,
        patient_gender=payload.patient_gender, patient_blood_group=payload.patient_blood_group,
        component=payload.component, units_required=payload.units_required,
        hospital_name=payload.hospital_name, hospital_location=payload.hospital_location,
        hospital_latitude=payload.hospital_latitude, hospital_longitude=payload.hospital_longitude,
        urgency=payload.urgency, status="open", created_at=utcnow(), updated_at=utcnow(),
    )
    req.allocated_units = 0
    db.add(req)
    db.flush()
    # No patient details in the audit message.
    record_event(db, req.id, "REQUEST_CREATED",
                 f"Blood request created ({req.units_required} unit(s) of {req.component}, urgency {req.urgency}).",
                 new_state="open")
    generate_snapshot(db, req, trigger="Request created")
    db.commit()
    return req


# ------------------------------------------------------------------ ranking
def _candidate_inputs(db: Session) -> List[CandidateInput]:
    out: List[CandidateInput] = []
    for b in db.scalars(select(BloodBank).order_by(BloodBank.id)):
        out.append(CandidateInput("blood_bank", b.id, b.name, b.location, b.latitude, b.longitude, b.blood_group,
                                  b.component, b.units_available, b.availability_status, b.last_updated,
                                  b.data_source))
    for d in db.scalars(select(Donor).order_by(Donor.id)):
        out.append(CandidateInput("donor", d.id, d.display_name, d.location, d.latitude, d.longitude, d.blood_group,
                                  None, None, d.availability_status, d.last_updated, d.data_source,
                                  d.consent_status, d.response_status))
    return out


def _overrides(db: Session, request_id: str) -> Dict[Tuple[str, str], Override]:
    rows = db.scalars(select(CandidateState).where(CandidateState.request_id == request_id))
    return {(r.candidate_type, r.candidate_id): Override(r.status, r.reason) for r in rows}


def latest_snapshot(db: Session, request_id: str) -> Optional[RankingSnapshot]:
    return db.scalar(select(RankingSnapshot).where(RankingSnapshot.request_id == request_id)
                     .order_by(RankingSnapshot.version.desc()).limit(1))


def generate_snapshot(db: Session, req: BloodRequest, trigger: str) -> RankingSnapshot:
    """Rank now, store as a new version (older versions are kept), and audit it."""
    prev = latest_snapshot(db, req.id)
    result = rank_candidates(
        RequestInput(req.id, req.patient_blood_group, req.component, req.units_required, req.urgency,
                     req.hospital_latitude, req.hospital_longitude),
        _candidate_inputs(db), _overrides(db, req.id),
    )
    changes = describe_changes(prev.payload if prev else None, result)
    version = (prev.version + 1) if prev else 1
    snap = RankingSnapshot(
        request_id=req.id, version=version, trigger=trigger, created_at=utcnow(),
        payload={"ranked": result["ranked"], "excluded": result["excluded"],
                 "summary": result["summary"], "changes": changes},
    )
    db.add(snap)
    db.flush()
    s = result["summary"]
    record_event(
        db, req.id, "RANKING_GENERATED" if prev is None else "RANKING_RECALCULATED",
        f"Ranking version {version} {'generated' if prev is None else 'recalculated'}: "
        f"{s['ranked_count']} option(s) ranked, {s['excluded_count']} excluded. Trigger: {trigger}.",
    )
    return snap


def recalculate(db: Session, request_id: str) -> RankingSnapshot:
    req = get_request_or_404(db, request_id)
    snap = generate_snapshot(db, req, trigger="Manual recalculation")
    db.commit()
    return snap


# ------------------------------------------------------------------- events
def _find_record(db: Session, candidate_type: str, candidate_id: str):
    model = BloodBank if candidate_type == "blood_bank" else Donor
    record = db.get(model, candidate_id)
    if record is None:
        raise NotFoundError(f"No {candidate_type.replace('_', ' ')} with ID '{candidate_id}' exists.")
    return record


def process_event(db: Session, request_id: str, event_type: str, candidate_type: Optional[str],
                  candidate_id: Optional[str], reason: Optional[str]):
    """Validate -> update state -> audit -> recalculate. Returns (event, snapshot, request)."""
    req = get_request_or_404(db, request_id)
    if req.status in TERMINAL_REQUEST_STATUSES:
        raise InvalidTransition(f"This request is '{req.status}', so no further events can be recorded.")

    if event_type == "COORDINATOR_NOTE":
        note = (reason or "").strip()
        if len(note) < 3:
            raise RuleViolation("Please write a short note (at least 3 characters).")
        event = record_event(db, req.id, "COORDINATOR_ACTION_RECORDED", note, candidate_type, candidate_id,
                             is_simulation=False)
        db.commit()
        return event, latest_snapshot(db, req.id), req

    if event_type not in EVENT_RULES:
        raise RuleViolation(f"Unknown event type '{event_type}'.")
    if not candidate_type or not candidate_id:
        raise RuleViolation("Choose the blood bank or donor this event is about.")

    record = _find_record(db, candidate_type, candidate_id)

    if candidate_type == "donor":
        if event_type == "SELECT_FOR_REVIEW" and record.consent_status == "not_consented":
            raise RuleViolation("Donor has not consented to be contacted in this demonstration.")
        if event_type in ("CONFIRM_AVAILABILITY", "DONOR_DECLINED", "DONOR_NO_RESPONSE") \
                and record.consent_status != "consented_demo":
            raise RuleViolation(
                "Verified donor consent is required before confirming availability or recording a donor response."
            )

    state_row = db.scalar(select(CandidateState).where(
        CandidateState.request_id == req.id, CandidateState.candidate_type == candidate_type,
        CandidateState.candidate_id == candidate_id))
    if state_row is not None:
        current = state_row.status
    elif candidate_type == "donor" and record.response_status == "declined_recently":
        current = "declined"
    else:
        current = derive_candidate_status(record.availability_status)

    plan = plan_candidate_event(event_type, candidate_type, current, reason, candidate_id)

    now = utcnow()
    if state_row is None:
        db.add(CandidateState(request_id=req.id, candidate_type=candidate_type, candidate_id=candidate_id,
                              status=plan.new_status, reason=plan.reason, updated_at=now))
    else:
        state_row.status, state_row.reason, state_row.updated_at = plan.new_status, plan.reason, now
    event = record_event(db, req.id, plan.audit_event_type, plan.reason, candidate_type, candidate_id,
                         plan.previous_status, plan.new_status, is_simulation=plan.simulated)

    if event_type in ("STOCK_UNAVAILABLE", "DONOR_DECLINED", "DONOR_NO_RESPONSE"):
        release_allocations_for_candidate(db, req.id, candidate_type, candidate_id, plan.reason)

    if event_type == "SELECT_FOR_REVIEW" and req.status == "open":
        validate_request_transition("open", "under_review")
        record_event(db, req.id, "REQUEST_STATUS_UPDATED",
                     "Request moved to under review because an option was selected for review.",
                     previous_state="open", new_state="under_review")
        req.status = "under_review"

    req.updated_at = now
    req.allocated_units = get_allocated_units(db, req.id)
    db.flush()
    snap = generate_snapshot(db, req, trigger=f"{plan.audit_event_type} ({candidate_id})")
    db.commit()
    return event, snap, req


# ------------------------------------------------------------------- status
def update_status(db: Session, request_id: str, new_status: str, reason: Optional[str],
                  simulated_confirmation: bool):
    req = get_request_or_404(db, request_id)
    validate_request_transition(req.status, new_status)
    note = (reason or "").strip()
    if new_status == "cancelled" and len(note) < 3:
        raise RuleViolation("Please give a short reason (at least 3 characters) for cancelling.")

    allocated = get_allocated_units(db, req.id)
    fulfilment = new_status in ("fulfilled", "partially_fulfilled")
    if fulfilment:
        if not simulated_confirmation:
            raise RuleViolation("Marking a request fulfilled needs an explicit coordinator confirmation of this "
                                "simulated action.")
        if new_status == "fulfilled":
            if allocated == 0:
                raise RuleViolation("Cannot mark request fulfilled: no units have been allocated to this request. "
                                    "Candidate availability confirmation is not an allocation.")
            if allocated < req.units_required:
                raise RuleViolation(f"Cannot mark request fulfilled: only {allocated} of {req.units_required} "
                                    "unit(s) have been allocated. Request is partially fulfilled.")
        elif new_status == "partially_fulfilled":
            if allocated == 0:
                raise RuleViolation("Cannot mark request partially fulfilled: no units have been allocated to this request.")
            if allocated >= req.units_required:
                raise RuleViolation(f"Request has all {allocated} units allocated and should be marked fulfilled.")

    if new_status == "cancelled":
        release_all_request_allocations(db, req.id, reason=note)

    previous = req.status
    req.status = new_status
    req.updated_at = utcnow()
    req.allocated_units = get_allocated_units(db, req.id)
    text = f"Request status changed from {previous} to {new_status}."
    if fulfilment:
        text += " This is a simulated coordinator action, not a real medical transaction."
    if note:
        text += f" Note: {note}"
    event = record_event(db, req.id, "REQUEST_STATUS_UPDATED", text, previous_state=previous,
                         new_state=new_status, is_simulation=fulfilment)
    db.commit()
    return event, req
