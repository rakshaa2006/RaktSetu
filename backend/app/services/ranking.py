"""Deterministic, rule-based ranking with a plain-language explanation per option.

No scores, probabilities or predictions are produced. Options are ordered by an
explicit sort key made of documented tiers, so the same inputs always give the
same output.

Priority tiers (lower is better):
  0 confirmed and recent (or confirmed by a coordinator action on this request)
  1 awaiting confirmation (a coordinator is already contacting this option)
  2 reported available, recent
  3 stale (older than the recent window)
  4 unverified
  5 unknown (missing / unreadable / future timestamp)
  6 no response (never treated as acceptance)
Then: match quality (exact before compatible), then distance/capacity (order
depends on urgency), then blood banks before donors, then ID.
Excluded: no blood-group/component match, declined, unavailable, no consent.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from app.core.config import FRESHNESS, FreshnessConfig
from app.core.geo import distance_km
from app.core.rules import derive_candidate_status, match_blood
from app.services.freshness import assess_freshness, verification_label

RULES_VERSION = "1.0"
DISCLAIMER = (
    "Application-level screening only. Blood group compatibility, donor eligibility, screening and "
    "stock confirmation must be confirmed by qualified blood-bank personnel."
)

CANDIDATE_FIELDS = (
    "rank", "candidate_type", "candidate_id", "display_name", "location", "latitude", "longitude",
    "blood_group", "component", "units_available", "review_status", "verification_label", "freshness",
    "age_hours", "last_updated", "data_source", "distance_km", "distance_note", "match_level",
    "match_rule", "factors", "explanation", "reduced_priority_reasons", "exclusion_reasons",
    "exclusion_category", "priority_tier",
)

TIER_TEXT = {
    0: "confirmed and recent",
    1: "awaiting confirmation",
    2: "reported available and recent",
    3: "stale, needs re-checking",
    4: "unverified",
    5: "unknown update time",
    6: "no response yet",
}
STATUS_TEXT = {
    "reported_available": "Reported available", "awaiting_confirmation": "Awaiting confirmation",
    "confirmed_available": "Confirmed available", "declined": "Declined", "unavailable": "Unavailable",
    "no_response": "No response", "stale": "Stale", "unverified": "Unverified",
}
WORKFLOW_PRIORITY = {
    "Critical": "Immediate review: contact the top options now and keep checking the next ones in parallel.",
    "Urgent": "Prompt review: contact the top options as soon as possible.",
    "Routine": "Routine review: work through the options in order.",
}


@dataclass(frozen=True)
class RequestInput:
    request_id: str
    blood_group: str
    component: str
    units_required: int
    urgency: str
    latitude: Optional[float] = None
    longitude: Optional[float] = None


@dataclass(frozen=True)
class CandidateInput:
    candidate_type: str            # 'blood_bank' | 'donor'
    candidate_id: str
    display_name: str
    location: str
    latitude: Optional[float]
    longitude: Optional[float]
    blood_group: str
    component: Optional[str]       # blood banks only
    units_available: Optional[int]  # blood banks only
    record_status: str
    last_updated: Optional[str]
    data_source: str = ""
    consent_status: Optional[str] = None   # donors only
    response_status: Optional[str] = None  # donors only


@dataclass(frozen=True)
class Override:
    """Request-specific candidate state set by a recorded event."""
    status: str
    reason: str = ""


def _units_text(n: int) -> str:
    return f"{n} unit" + ("" if n == 1 else "s")


def _evaluate(req: RequestInput, c: CandidateInput, ov: Optional[Override],
              now: datetime, cfg: FreshnessConfig) -> Dict[str, Any]:
    fr = assess_freshness(c.last_updated, now, cfg)
    dist = distance_km(req.latitude, req.longitude, c.latitude, c.longitude)
    match = match_blood(req.blood_group, c.blood_group, req.component)
    status = ov.status if ov else derive_candidate_status(c.record_status)
    label = "not_confirmed" if status == "no_response" else verification_label(c.record_status, fr.freshness)

    exclusions: List[Tuple[str, str]] = []
    reduced: List[str] = []

    # ---- exclusions -------------------------------------------------------
    if c.candidate_type == "blood_bank" and c.component != req.component:
        exclusions.append(("not_matched", f"Stock is {c.component}, but the request needs {req.component}."))
    if match.level == "none":
        exclusions.append(("not_matched", match.rule))
    if c.candidate_type == "donor" and c.consent_status == "not_consented":
        exclusions.append(("not_consented", "Donor has not consented to be contacted in this demonstration."))
    if ov is not None:
        if ov.status == "declined":
            exclusions.append(("declined", "Declined for this request. Not recommended again unless an authorised status update reinstates it."))
        elif ov.status == "unavailable":
            exclusions.append(("unavailable", "Reported unavailable for this request. Not recommended again unless an authorised status update reinstates it."))
    else:
        if c.record_status == "unavailable":
            exclusions.append(("unavailable", "The record reports this option as unavailable."))
        if c.candidate_type == "blood_bank" and isinstance(c.units_available, int) and c.units_available <= 0:
            exclusions.append(("unavailable", "The record reports 0 units available."))
        if c.candidate_type == "donor" and c.response_status == "declined_recently":
            status = "declined"
            exclusions.append(("declined", "Donor recently declined. Not recommended unless an authorised status update reinstates the donor."))

    capacity: Optional[int] = None
    if c.candidate_type == "blood_bank":
        capacity = c.units_available if isinstance(c.units_available, int) and c.units_available >= 0 else None
    else:
        capacity = 1

    # ---- tier -------------------------------------------------------------
    tier = 6
    if not exclusions:
        if status == "confirmed_available":
            if ov is not None or fr.freshness == "recent":
                tier = 0
            elif fr.freshness == "stale":
                tier = 3
                reduced.append("The earlier confirmation is old, so it is treated as stale until re-checked.")
            else:
                tier = 5
                reduced.append("The confirmation has no readable update time, so it is treated as unknown.")
        elif status == "awaiting_confirmation":
            tier = 1
            if fr.freshness != "recent":
                reduced.append("The underlying record is " + fr.freshness + "; confirmation is still needed.")
        elif status == "reported_available":
            if fr.freshness == "recent":
                tier = 2
            elif fr.freshness == "stale":
                tier = 3
                reduced.append("Reported availability is stale, so it is ranked below recent options and must be re-checked.")
            else:
                tier = 5
                reduced.append("Reported availability has no readable update time, so it is ranked as unknown.")
        elif status == "stale":
            tier = 3
            reduced.append("Marked stale for this request, so it is ranked below recent options until re-checked.")
        elif status == "unverified":
            tier = 5 if fr.freshness == "unknown" else 4
            reduced.append("Availability is unverified; contact the source before relying on it.")
        elif status == "no_response":
            tier = 6
            reduced.append("No response was received. No response is not acceptance and is not confirmed availability.")
        if c.candidate_type == "donor" and ov is None:
            if c.response_status == "no_recent_response":
                tier = max(tier, 6)
                reduced.append("This donor has not responded recently. No response is not acceptance.")
            if c.consent_status == "unknown":
                tier = max(tier, 4)
                reduced.append("Consent status is unknown; confirm consent before contact.")
        if c.candidate_type == "blood_bank" and capacity is None:
            tier = max(tier, 5)
            reduced.append("Reported unit count is missing or invalid.")
        if match.level == "compatible":
            reduced.append("Not an identical group: a qualified person must confirm compatibility.")
        if capacity is not None and capacity < req.units_required:
            reduced.append(f"Covers {_units_text(capacity)} of the {req.units_required} needed.")

    # ---- facts shown on every card ---------------------------------------
    if dist is not None:
        dist_note = "Straight-line distance, not road distance or travel time."
        dist_factor = f"Distance: about {dist} km straight-line"
    else:
        dist_note = "Distance unknown: coordinates are missing for this record or the request."
        dist_factor = "Distance: unknown (coordinates missing)"
    if capacity is None:
        cap_factor = "Capacity: unknown"
    elif c.candidate_type == "blood_bank":
        cap_factor = f"Stock reported: {_units_text(capacity)} (request needs {req.units_required})"
    else:
        cap_factor = f"Donation: 1 unit per donor (request needs {req.units_required})"
    factors = [
        f"Blood group match: {match.level} ({c.blood_group} for {req.blood_group})",
        f"Option status for this request: {STATUS_TEXT.get(status, status)}",
        f"Data label: {label}",
        f"Freshness: {fr.freshness}" + (f" ({fr.age_hours:g} h old)" if fr.age_hours is not None else ""),
        dist_factor,
        cap_factor,
        f"Urgency: {req.urgency} (workflow priority)",
    ]

    sufficient = capacity is not None and capacity >= req.units_required
    suff_rank = 0 if sufficient else 1
    type_rank = 0 if c.candidate_type == "blood_bank" else 1
    d_known = 0 if dist is not None else 1
    d_val = dist if dist is not None else 0.0
    if req.urgency in ("Critical", "Urgent"):
        key = (tier, 0 if match.level == "exact" else 1, d_known, d_val, suff_rank, type_rank, c.candidate_id)
    else:
        key = (tier, 0 if match.level == "exact" else 1, suff_rank, d_known, d_val, type_rank, c.candidate_id)

    return {
        "_key": key, "_excluded": bool(exclusions),
        "rank": None, "candidate_type": c.candidate_type, "candidate_id": c.candidate_id,
        "display_name": c.display_name, "location": c.location,
        "latitude": c.latitude, "longitude": c.longitude, "blood_group": c.blood_group,
        "component": c.component, "units_available": c.units_available if c.candidate_type == "blood_bank" else None,
        "review_status": status, "verification_label": label, "freshness": fr.freshness,
        "age_hours": fr.age_hours, "last_updated": fr.last_updated, "data_source": c.data_source,
        "distance_km": dist, "distance_note": dist_note, "match_level": match.level, "match_rule": match.rule,
        "factors": factors, "explanation": "", "reduced_priority_reasons": reduced,
        "exclusion_reasons": [t for _, t in exclusions],
        "exclusion_category": exclusions[0][0] if exclusions else None,
        "priority_tier": None if exclusions else tier,
        "_fresh_note": fr.note,
    }


def _explain_ranked(item: Dict[str, Any], req: RequestInput) -> str:
    kind = "Blood bank" if item["candidate_type"] == "blood_bank" else "Registered donor"
    parts = [
        f"{kind} ranked #{item['rank']} in priority tier '{TIER_TEXT[item['priority_tier']]}'.",
        f"Blood group: {item['match_rule']}",
        f"Data: {item['verification_label']}. {item['_fresh_note']}",
    ]
    parts.append(
        f"Distance is about {item['distance_km']} km in a straight line (not road distance)."
        if item["distance_km"] is not None else "Distance is unknown because coordinates are missing."
    )
    if req.urgency in ("Critical", "Urgent"):
        parts.append(f"Because the request is {req.urgency}, nearer options are placed ahead of stock size within the same tier.")
    else:
        parts.append("Because the request is Routine, options that cover more of the needed units are placed ahead of nearer ones within the same tier.")
    if item["reduced_priority_reasons"]:
        parts.append("Points to check: " + " ".join(item["reduced_priority_reasons"]))
    return " ".join(parts)


def _explain_excluded(item: Dict[str, Any]) -> str:
    return "Not recommended. " + " ".join(item["exclusion_reasons"])


def rank_candidates(req: RequestInput, candidates: List[CandidateInput],
                    overrides: Optional[Dict[Tuple[str, str], Override]] = None,
                    now: Optional[datetime] = None,
                    cfg: FreshnessConfig = FRESHNESS) -> Dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    overrides = overrides or {}
    evaluated = [_evaluate(req, c, overrides.get((c.candidate_type, c.candidate_id)), now, cfg) for c in candidates]

    ranked = sorted((e for e in evaluated if not e["_excluded"]), key=lambda e: e["_key"])
    # Relevant exclusions (matched but out of the running) first, then non-matching ones.
    excluded = sorted((e for e in evaluated if e["_excluded"]),
                      key=lambda e: (e["exclusion_category"] == "not_matched", e["candidate_type"], e["candidate_id"]))
    for i, item in enumerate(ranked, start=1):
        item["rank"] = i
        item["explanation"] = _explain_ranked(item, req)
    for item in excluded:
        item["explanation"] = _explain_excluded(item)

    def clean(item: Dict[str, Any]) -> Dict[str, Any]:
        return {k: item[k] for k in CANDIDATE_FIELDS}

    ranked_out = [clean(i) for i in ranked]
    excluded_out = [clean(i) for i in excluded]
    return {
        "ranked": ranked_out,
        "excluded": excluded_out,
        "summary": {
            "total_evaluated": len(evaluated),
            "ranked_count": len(ranked_out),
            "excluded_count": len(excluded_out),
            "not_matched_count": sum(1 for e in excluded_out if e["exclusion_category"] == "not_matched"),
            "urgency": req.urgency,
            "workflow_priority": WORKFLOW_PRIORITY.get(req.urgency, ""),
            "rules_version": RULES_VERSION,
            "disclaimer": DISCLAIMER,
        },
    }


def describe_changes(previous: Optional[Dict[str, Any]], new: Dict[str, Any], limit: int = 12) -> List[str]:
    """Plain-language list of what changed between two ranking results.

    Options that only shifted because something above them was removed or added are
    summarised in one line instead of being listed one by one.
    """
    if previous is None:
        return ["Initial ranking generated."]
    key = lambda i: (i["candidate_type"], i["candidate_id"])  # noqa: E731
    label = lambda i: f"{i['display_name']} ({i['candidate_id']})"  # noqa: E731
    prev_r = {key(i): i for i in previous["ranked"]}
    new_r = {key(i): i for i in new["ranked"]}
    new_x = {key(i): i for i in new["excluded"]}
    prev_x = {key(i): i for i in previous["excluded"]}

    removed = [old for k, old in prev_r.items() if k not in new_r]
    added = [item for k, item in new_r.items() if k not in prev_r]
    out: List[str] = []
    for old in removed:
        k = key(old)
        reason = new_x[k]["exclusion_reasons"][0] if k in new_x and new_x[k]["exclusion_reasons"] else "no longer eligible."
        out.append(f"{label(old)} (was #{old['rank']}) was removed from the ranking: {reason}")
    for item in added:
        was = " (it was excluded before)" if key(item) in prev_x else ""
        out.append(f"{label(item)} is now ranked #{item['rank']}{was}.")

    shifted = 0
    for k, item in new_r.items():
        if k not in prev_r:
            continue
        old = prev_r[k]
        removed_above = sum(1 for r in removed if r["rank"] < old["rank"])
        added_ahead = sum(1 for a in added if a["rank"] < item["rank"])
        expected = old["rank"] - removed_above + added_ahead
        if item["rank"] != expected:
            out.append(f"{label(item)} moved from #{old['rank']} to #{item['rank']}.")
        elif item["rank"] != old["rank"]:
            shifted += 1
        if (old["review_status"], old["verification_label"]) != (item["review_status"], item["verification_label"]):
            out.append(f"{label(item)} changed status from {old['review_status']} to {item['review_status']}"
                       f" (data label {old['verification_label']} to {item['verification_label']}).")
    if shifted:
        out.append(f"{shifted} other option(s) moved up or down a place as a result.")
    if not out:
        out.append("The ranking order did not change.")
    if len(out) > limit:
        extra = len(out) - limit
        out = out[:limit] + [f"...and {extra} more change(s)."]
    return out
