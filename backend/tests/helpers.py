"""Shared test data builders (no framework imports, so they work everywhere)."""
from datetime import datetime, timedelta, timezone

from app.services.ranking import CandidateInput, RequestInput

NOW = datetime(2026, 1, 15, 12, 0, tzinfo=timezone.utc)


def iso_ago(hours):
    return None if hours is None else (NOW - timedelta(hours=hours)).isoformat()


def req(group="O+", component="Packed Red Cells", units=2, urgency="Critical", lat=18.53, lng=73.84):
    return RequestInput("REQ-TEST", group, component, units, urgency, lat, lng)


def bank(cid, group="O+", units=5, status="reported_available", hours=1.0, lat=18.50, lng=73.80,
         component="Packed Red Cells"):
    return CandidateInput("blood_bank", cid, f"Bank {cid}", "Test area", lat, lng, group, component, units,
                          status, iso_ago(hours) if not isinstance(hours, str) else hours, "test")


def donor(cid, group="O+", status="reported_available", hours=1.0, lat=18.50, lng=73.80,
          consent="consented_demo", response="responsive"):
    return CandidateInput("donor", cid, f"Donor {cid}", "Test area", lat, lng, group, None, None, status,
                          iso_ago(hours) if not isinstance(hours, str) else hours, "test", consent, response)
