"""Enumerations, blood-matching rules and state-transition tables.

Pure Python, no framework imports.

IMPORTANT: matching here is a conservative, application-level screen used only to
decide which options a coordinator should review first. It is NOT a medical
compatibility determination. Qualified blood-bank staff make the final decision.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.core.errors import InvalidTransition

BLOOD_GROUPS = ("A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-")
COMPONENTS = ("Whole Blood", "Packed Red Cells", "Platelets", "Plasma")
GENDERS = ("Female", "Male", "Other", "Prefer not to say")
URGENCIES = ("Critical", "Urgent", "Routine")

CANDIDATE_TYPES = ("blood_bank", "donor")

RECORD_STATUSES = ("reported_available", "confirmed_available", "unavailable", "unverified", "unknown")
CONSENT_STATUSES = ("consented_demo", "not_consented", "unknown")
DONOR_RESPONSE_STATUSES = ("responsive", "no_recent_response", "declined_recently", "unknown")

REQUEST_STATUSES = (
    "open", "under_review", "awaiting_confirmation",
    "partially_fulfilled", "fulfilled", "cancelled",
)
APPROVAL_STATUSES = ("pending", "approved", "rejected")
CANDIDATE_STATUSES = (
    "reported_available", "awaiting_confirmation", "confirmed_available",
    "declined", "unavailable", "no_response", "stale", "unverified",
)

# ---- Request transitions ---------------------------------------------------
REQUEST_TRANSITIONS = {
    "open": {"under_review", "cancelled"},
    "under_review": {"open", "awaiting_confirmation", "partially_fulfilled", "fulfilled", "cancelled"},
    "awaiting_confirmation": {"under_review", "partially_fulfilled", "fulfilled", "cancelled"},
    "partially_fulfilled": {"awaiting_confirmation", "under_review", "fulfilled", "cancelled"},
    "fulfilled": set(),
    "cancelled": set(),
}
TERMINAL_REQUEST_STATUSES = ("fulfilled", "cancelled")

# ---- Candidate transitions -------------------------------------------------
# declined / unavailable can only be left through an authorised reinstatement.
CANDIDATE_TRANSITIONS = {
    "reported_available": {"awaiting_confirmation", "declined", "unavailable", "no_response", "stale"},
    "awaiting_confirmation": {"confirmed_available", "declined", "unavailable", "no_response", "stale"},
    "confirmed_available": {"awaiting_confirmation", "declined", "unavailable", "no_response", "stale"},
    "unverified": {"reported_available", "awaiting_confirmation", "declined", "unavailable", "no_response", "stale"},
    "stale": {"reported_available", "awaiting_confirmation", "declined", "unavailable", "no_response"},
    "no_response": {"awaiting_confirmation", "reported_available", "declined", "unavailable", "stale"},
    "declined": {"awaiting_confirmation"},
    "unavailable": {"awaiting_confirmation"},
}


def derive_candidate_status(record_status: str) -> str:
    """Starting candidate state for a request, derived from the base record."""
    if record_status == "reported_available":
        return "reported_available"
    if record_status == "confirmed_available":
        return "confirmed_available"
    if record_status == "unavailable":
        return "unavailable"
    return "unverified"  # 'unverified' and 'unknown' both need checking


def validate_request_transition(current: str, new: str) -> None:
    if current not in REQUEST_TRANSITIONS:
        raise InvalidTransition(f"Unknown current request status '{current}'.")
    if new not in REQUEST_TRANSITIONS:
        raise InvalidTransition(f"Unknown request status '{new}'.")
    if current == new:
        raise InvalidTransition(f"Request is already '{current}'.")
    if new not in REQUEST_TRANSITIONS[current]:
        allowed = sorted(REQUEST_TRANSITIONS[current])
        hint = ", ".join(allowed) if allowed else "none (this status is final)"
        raise InvalidTransition(
            f"Cannot change a request from '{current}' to '{new}'. Allowed next statuses: {hint}."
        )


def validate_candidate_transition(current: str, new: str) -> None:
    if current == new:
        raise InvalidTransition(f"This option is already '{current}'.")
    allowed = CANDIDATE_TRANSITIONS.get(current, set())
    if new not in allowed:
        hint = ", ".join(sorted(allowed)) if allowed else "none"
        raise InvalidTransition(
            f"Cannot change this option from '{current}' to '{new}'. Allowed next states: {hint}."
        )


# ---- Blood group / component matching -------------------------------------
# Red cells: donor groups that may be considered for a recipient group.
RBC_DONORS = {
    "O-": {"O-"},
    "O+": {"O-", "O+"},
    "A-": {"O-", "A-"},
    "A+": {"O-", "O+", "A-", "A+"},
    "B-": {"O-", "B-"},
    "B+": {"O-", "O+", "B-", "B+"},
    "AB-": {"O-", "A-", "B-", "AB-"},
    "AB+": set(BLOOD_GROUPS),
}
# Plasma: ABO only (Rh ignored), reverse of red cells.
PLASMA_DONOR_ABO = {"O": {"O", "A", "B", "AB"}, "A": {"A", "AB"}, "B": {"B", "AB"}, "AB": {"AB"}}

MATCH_RULES_DOC = {
    "Whole Blood": "Identical ABO/Rh group only.",
    "Packed Red Cells": "Identical group, or a standard ABO/Rh red-cell compatible group (flagged for review).",
    "Platelets": "Identical ABO/Rh group only.",
    "Plasma": "Identical group, or an ABO-compatible plasma group, Rh ignored (flagged for review).",
}


@dataclass(frozen=True)
class MatchResult:
    level: str  # 'exact' | 'compatible' | 'none'
    rule: str


def _abo(group: str) -> str:
    return group[:-1]


def match_blood(recipient_group: str, candidate_group: str, component: str) -> MatchResult:
    """Conservative blood-group screen. Unknown inputs never match."""
    if recipient_group not in BLOOD_GROUPS or candidate_group not in BLOOD_GROUPS or component not in COMPONENTS:
        return MatchResult("none", "Blood group or component not recognised, so no match is assumed.")
    if recipient_group == candidate_group:
        return MatchResult("exact", f"Identical group ({candidate_group}) for {component}.")
    if component == "Packed Red Cells" and candidate_group in RBC_DONORS[recipient_group]:
        return MatchResult(
            "compatible",
            f"{candidate_group} is a standard red-cell compatible group for {recipient_group}; blood-bank staff must confirm.",
        )
    if component == "Plasma" and _abo(candidate_group) in PLASMA_DONOR_ABO[_abo(recipient_group)]:
        return MatchResult(
            "compatible",
            f"{candidate_group} is ABO-compatible plasma for {recipient_group}; blood-bank staff must confirm.",
        )
    return MatchResult(
        "none",
        f"{candidate_group} is not matched to {recipient_group} for {component} under the configured conservative rules.",
    )
