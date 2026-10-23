from datetime import datetime, timezone

from app.core.geo import distance_km
from app.services.freshness import assess_freshness, parse_timestamp, verification_label
from tests.helpers import NOW, iso_ago


def test_recent_record():
    r = assess_freshness(iso_ago(2), NOW)
    assert r.freshness == "recent" and r.age_hours == 2.0


def test_stale_record():
    r = assess_freshness(iso_ago(30), NOW)
    assert r.freshness == "stale" and r.age_hours == 30.0
    assert "older" in r.note


def test_threshold_boundary_is_recent():
    assert assess_freshness(iso_ago(6), NOW).freshness == "recent"
    assert assess_freshness(iso_ago(6.2), NOW).freshness == "stale"


def test_missing_timestamp_is_unknown():
    for value in (None, "", "   "):
        assert assess_freshness(value, NOW).freshness == "unknown"


def test_invalid_timestamp_is_unknown_and_never_raises():
    for value in ("not-a-timestamp", "2026-99-99", 12345, object()):
        assert assess_freshness(value, NOW).freshness == "unknown"


def test_future_timestamp_is_unknown():
    assert assess_freshness(iso_ago(-5), NOW).freshness == "unknown"


def test_naive_and_zulu_timestamps_are_read_as_utc():
    assert parse_timestamp("2026-01-15T11:00:00")[0] == datetime(2026, 1, 15, 11, 0, tzinfo=timezone.utc)
    assert parse_timestamp("2026-01-15T11:00:00Z")[0] == datetime(2026, 1, 15, 11, 0, tzinfo=timezone.utc)


def test_labels_never_promote_stale_or_unknown_to_confirmed():
    assert verification_label("confirmed_available", "recent") == "confirmed"
    assert verification_label("confirmed_available", "stale") == "stale"
    assert verification_label("confirmed_available", "unknown") == "unknown"
    assert verification_label("reported_available", "recent") == "reported"
    assert verification_label("unverified", "recent") == "unverified"
    assert verification_label("unavailable", "recent") == "unavailable"


def test_distance_is_straight_line_and_handles_missing_values():
    assert distance_km(18.5308, 73.8475, 18.5308, 73.8475) == 0.0
    d = distance_km(18.5308, 73.8475, 18.5074, 73.8077)
    assert 4.0 < d < 6.0
    assert distance_km(None, 73.8, 18.5, 73.8) is None
    assert distance_km(18.5, 73.8, 91, 73.8) is None
    assert distance_km(18.5, 73.8, float("nan"), 73.8) is None
