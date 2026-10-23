"""Failure-aware coordination rules (pure).

Turns a coordinator/simulation event into a validated state-change plan.
The database work happens in coordination.py.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from app.core.errors import InvalidTransition, RuleViolation
from app.core.rules import CANDIDATE_TYPES, validate_candidate_transition


@dataclass(frozen=True)
class EventRule:
    target_status: str
    audit_event_type: str
    only_for: Optional[str]       # candidate type restriction, or None
    simulated: bool
    needs_reason: bool
    label: str


EVENT_RULES = {
    "STOCK_UNAVAILABLE": EventRule("unavailable", "STOCK_REPORTED_UNAVAILABLE", "blood_bank", True, False,
                                   "Blood bank reports stock unavailable"),
    "DONOR_DECLINED": EventRule("declined", "CANDIDATE_DECLINED", "donor", True, False, "Donor declines"),
    "DONOR_NO_RESPONSE": EventRule("no_response", "CANDIDATE_NO_RESPONSE", "donor", True, False,
                                   "Donor does not respond"),
    "DATA_STALE": EventRule("stale", "DATA_MARKED_STALE", None, True, False, "Availability record becomes stale"),
    "SELECT_FOR_REVIEW": EventRule("awaiting_confirmation", "RECOMMENDATION_SELECTED_FOR_REVIEW", None, False,
                                   False, "Select for review"),
    "CONFIRM_AVAILABILITY": EventRule("confirmed_available", "AVAILABILITY_CONFIRMED_SIMULATED", None, True,
                                      False, "Record confirmation (simulated)"),
    "REINSTATE_CANDIDATE": EventRule("awaiting_confirmation", "CANDIDATE_REINSTATED", None, False, True,
                                     "Reinstate option (authorised update)"),
}
EVENT_TYPES = tuple(EVENT_RULES)
LEAVES_FINAL_STATES = {"REINSTATE_CANDIDATE"}  # only way out of declined/unavailable


@dataclass(frozen=True)
class TransitionPlan:
    event_type: str
    audit_event_type: str
    previous_status: str
    new_status: str
    simulated: bool
    reason: str


def plan_candidate_event(event_type: str, candidate_type: str, current_status: str,
                         reason: Optional[str], candidate_id: str = "") -> TransitionPlan:
    """Validate an event against the option's current state and return the plan."""
    rule = EVENT_RULES.get(event_type)
    if rule is None:
        raise RuleViolation(f"Unknown event type '{event_type}'.")
    if candidate_type not in CANDIDATE_TYPES:
        raise RuleViolation(f"Unknown candidate type '{candidate_type}'.")
    if rule.only_for and candidate_type != rule.only_for:
        who = "blood banks" if rule.only_for == "blood_bank" else "registered donors"
        raise RuleViolation(f"'{rule.label}' applies to {who} only.")
    reason = (reason or "").strip()
    if rule.needs_reason and len(reason) < 5:
        raise RuleViolation("A reason of at least 5 characters is required for this authorised update.")
    if current_status in ("declined", "unavailable") and event_type not in LEAVES_FINAL_STATES:
        raise InvalidTransition(
            f"This option is '{current_status}' for this request. Only an authorised 'Reinstate option' "
            "update with a reason can bring it back."
        )
    validate_candidate_transition(current_status, rule.target_status)
    who = f" ({candidate_id})" if candidate_id else ""
    default_reason = f"{rule.label}{who}."
    return TransitionPlan(
        event_type=event_type, audit_event_type=rule.audit_event_type,
        previous_status=current_status, new_status=rule.target_status,
        simulated=rule.simulated, reason=(f"{default_reason} Note: {reason}" if reason else default_reason),
    )
