"""Freshness rules. Thresholds live in app.core.config.FRESHNESS.

Stale or unknown data is never silently promoted to confirmed availability.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional, Tuple

from app.core.config import FRESHNESS, FreshnessConfig


@dataclass(frozen=True)
class FreshnessResult:
    freshness: str                 # 'recent' | 'stale' | 'unknown'
    age_hours: Optional[float]
    last_updated: Optional[str]    # normalised ISO-8601 UTC, or None
    note: str


def parse_timestamp(value: Any) -> Tuple[Optional[datetime], Optional[str]]:
    """Return (datetime in UTC, None) or (None, 'missing'|'invalid'). Never raises."""
    if value is None:
        return None, "missing"
    try:
        if isinstance(value, datetime):
            dt = value
        elif isinstance(value, str):
            text = value.strip()
            if not text:
                return None, "missing"
            dt = datetime.fromisoformat(text)
        else:
            return None, "invalid"
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc), None
    except (ValueError, OverflowError, TypeError):
        return None, "invalid"


def assess_freshness(value: Any, now: Optional[datetime] = None,
                     cfg: FreshnessConfig = FRESHNESS) -> FreshnessResult:
    now = now or datetime.now(timezone.utc)
    dt, problem = parse_timestamp(value)
    if problem == "missing":
        return FreshnessResult("unknown", None, None, "No last-updated time is recorded, so freshness is unknown.")
    if problem == "invalid":
        return FreshnessResult("unknown", None, None, "The last-updated time could not be read, so freshness is unknown.")
    age = (now - dt).total_seconds() / 3600.0
    if age < -cfg.future_tolerance_hours:
        return FreshnessResult("unknown", None, dt.isoformat(), "The last-updated time is in the future, so freshness is unknown.")
    age = max(age, 0.0)
    iso = dt.isoformat()
    if age <= cfg.recent_hours:
        return FreshnessResult("recent", round(age, 1), iso, f"Updated {age:.1f} h ago (within the {cfg.recent_hours:g} h recent window).")
    return FreshnessResult("stale", round(age, 1), iso, f"Updated {age:.1f} h ago (older than the {cfg.recent_hours:g} h recent window).")


def verification_label(record_status: str, freshness: str) -> str:
    """Single visible label: confirmed | reported | stale | unverified | unavailable | unknown."""
    if record_status == "unavailable":
        return "unavailable"
    if freshness == "unknown":
        return "unknown"
    if freshness == "stale":
        return "stale"
    if record_status == "confirmed_available":
        return "confirmed"
    if record_status == "reported_available":
        return "reported"
    if record_status == "unverified":
        return "unverified"
    return "unknown"


LABEL_LEGEND = {
    "confirmed": "Confirmed - availability was verified and the record is recent.",
    "reported": "Reported - availability was stated but not verified; record is recent.",
    "stale": "Stale - the record is older than the recent window; ranked lower until re-checked.",
    "unverified": "Unverified - source has not verified this record.",
    "unavailable": "Unavailable - the record says it cannot supply; not recommended.",
    "unknown": "Unknown - the update time is missing or unreadable.",
}
