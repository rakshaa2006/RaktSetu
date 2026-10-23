from app.services.ranking import CANDIDATE_FIELDS, Override, describe_changes, rank_candidates
from tests.helpers import NOW, bank, donor, req


def ids(result):
    return [i["candidate_id"] for i in result["ranked"]]


def excluded_ids(result):
    return [i["candidate_id"] for i in result["excluded"]]


def test_candidate_filtering_by_group_and_component():
    cands = [bank("B1", "O+"), bank("B2", "A+"), bank("B3", "O+", component="Platelets"), donor("D1", "B-")]
    r = rank_candidates(req("O+", "Packed Red Cells"), cands, now=NOW)
    assert ids(r) == ["B1"]
    assert set(excluded_ids(r)) == {"B2", "B3", "D1"}
    assert all(i["exclusion_category"] == "not_matched" for i in r["excluded"])


def test_exact_match_beats_compatible_in_same_tier():
    r = rank_candidates(req("O+"), [bank("B1", "O-", lat=18.53, lng=73.84), bank("B2", "O+", lat=18.60, lng=73.90)], now=NOW)
    assert ids(r) == ["B2", "B1"]
    assert r["ranked"][1]["match_level"] == "compatible"


def test_ranking_is_deterministic_and_input_order_independent():
    cands = [bank("B1"), bank("B2", hours=30), donor("D1"), donor("D2", hours=None), bank("B3", status="unverified")]
    a = rank_candidates(req(), cands, now=NOW)
    b = rank_candidates(req(), list(reversed(cands)), now=NOW)
    assert a == b


def test_tier_order_confirmed_reported_stale_unverified_unknown_noresponse():
    cands = [
        bank("NR", status="reported_available", hours=1),
        bank("UNK", status="reported_available", hours=None),
        bank("UNV", status="unverified", hours=1),
        bank("STALE", status="reported_available", hours=48),
        bank("REP", status="reported_available", hours=1),
        bank("CONF", status="confirmed_available", hours=1),
    ]
    ov = {("blood_bank", "NR"): Override("no_response", "x")}
    r = rank_candidates(req(), cands, ov, now=NOW)
    assert ids(r) == ["CONF", "REP", "STALE", "UNV", "UNK", "NR"]


def test_stale_confirmation_is_not_treated_as_confirmed():
    r = rank_candidates(req(), [bank("B1", status="confirmed_available", hours=48), bank("B2", status="reported_available", hours=1)], now=NOW)
    assert ids(r) == ["B2", "B1"]
    stale = r["ranked"][1]
    assert stale["verification_label"] == "stale"
    assert any("old" in t or "stale" in t for t in stale["reduced_priority_reasons"])


def test_missing_and_invalid_timestamps_are_unknown_not_recent():
    r = rank_candidates(req(), [bank("B1", hours=None), bank("B2", hours="garbage")], now=NOW)
    for item in r["ranked"]:
        assert item["freshness"] == "unknown" and item["verification_label"] == "unknown"
        assert item["priority_tier"] == 5


def test_declined_candidate_is_excluded_and_stays_excluded():
    ov = {("donor", "D1"): Override("declined", "no")}
    r = rank_candidates(req(), [donor("D1"), donor("D2")], ov, now=NOW)
    assert ids(r) == ["D2"] and excluded_ids(r) == ["D1"]
    assert r["excluded"][0]["exclusion_category"] == "declined"


def test_unavailable_stock_is_excluded():
    ov = {("blood_bank", "B1"): Override("unavailable", "")}
    r = rank_candidates(req(), [bank("B1"), bank("B2")], ov, now=NOW)
    assert ids(r) == ["B2"] and r["excluded"][0]["exclusion_category"] == "unavailable"


def test_record_level_unavailable_and_zero_units_excluded():
    r = rank_candidates(req(), [bank("B1", status="unavailable"), bank("B2", units=0), bank("B3")], now=NOW)
    assert ids(r) == ["B3"]


def test_reinstated_candidate_overrides_record_level_exclusion():
    c = donor("D1", response="declined_recently")
    assert ids(rank_candidates(req(), [c], now=NOW)) == []
    ov = {("donor", "D1"): Override("awaiting_confirmation", "authorised reinstatement")}
    assert ids(rank_candidates(req(), [c], ov, now=NOW)) == ["D1"]


def test_nonresponse_is_never_acceptance():
    ov = {("donor", "D1"): Override("no_response", "")}
    r = rank_candidates(req(), [donor("D1"), bank("B1", status="unverified")], ov, now=NOW)
    nr = [i for i in r["ranked"] if i["candidate_id"] == "D1"][0]
    assert nr["review_status"] == "no_response"
    assert nr["verification_label"] != "confirmed"
    assert any("not acceptance" in t.lower() for t in nr["reduced_priority_reasons"])
    assert r["ranked"][-1]["candidate_id"] == "D1"


def test_donor_consent_rules():
    r = rank_candidates(req(), [donor("D1", consent="not_consented"), donor("D2", consent="unknown"), donor("D3")], now=NOW)
    assert ids(r) == ["D3", "D2"] and excluded_ids(r) == ["D1"]


def test_distance_unknown_is_shown_and_ranked_after_known_for_critical():
    r = rank_candidates(req(urgency="Critical"), [bank("FAR", lat=18.7, lng=74.0), bank("NONE", lat=None, lng=None), bank("NEAR", lat=18.531, lng=73.841)], now=NOW)
    assert ids(r) == ["NEAR", "FAR", "NONE"]
    none_item = r["ranked"][2]
    assert none_item["distance_km"] is None and "unknown" in none_item["distance_note"].lower()
    assert "not road distance" in r["ranked"][0]["distance_note"]


def test_urgency_changes_tie_break_order_but_never_the_tier():
    cands = [bank("NEAR_SMALL", units=1, lat=18.531, lng=73.841), bank("FAR_BIG", units=9, lat=18.7, lng=74.0)]
    assert ids(rank_candidates(req(urgency="Critical"), cands, now=NOW)) == ["NEAR_SMALL", "FAR_BIG"]
    assert ids(rank_candidates(req(urgency="Routine"), cands, now=NOW)) == ["FAR_BIG", "NEAR_SMALL"]


def test_every_result_has_all_fields_and_an_explanation():
    r = rank_candidates(req(), [bank("B1"), donor("D1"), bank("B2", "A+"), bank("B3", hours=40)], now=NOW)
    for item in r["ranked"] + r["excluded"]:
        assert set(item) == set(CANDIDATE_FIELDS)
        assert item["explanation"].strip()
        assert item["factors"]
    for i, item in enumerate(r["ranked"], start=1):
        assert item["rank"] == i and "ranked #" in item["explanation"]
    for item in r["excluded"]:
        assert item["rank"] is None and item["exclusion_reasons"]


def test_partial_capacity_is_explained():
    r = rank_candidates(req(units=4), [bank("B1", units=1)], now=NOW)
    assert any("1 unit of the 4" in t for t in r["ranked"][0]["reduced_priority_reasons"])


def test_summary_has_disclaimer_and_counts():
    r = rank_candidates(req(), [bank("B1"), bank("B2", "A+")], now=NOW)
    s = r["summary"]
    assert s["ranked_count"] == 1 and s["excluded_count"] == 1 and s["not_matched_count"] == 1
    assert "qualified" in s["disclaimer"]


def test_describe_changes_after_failure():
    cands = [bank("B1"), bank("B2", lat=18.6, lng=73.9), bank("B3", lat=18.7, lng=74.0)]
    before = rank_candidates(req(), cands, now=NOW)
    after = rank_candidates(req(), cands, {("blood_bank", "B1"): Override("unavailable", "")}, now=NOW)
    changes = describe_changes(before, after)
    assert any("B1" in c and "removed from the ranking" in c for c in changes)
    assert any("other option(s) moved" in c for c in changes)
    assert len(changes) == 2
    assert describe_changes(None, after) == ["Initial ranking generated."]
    assert describe_changes(after, after) == ["The ranking order did not change."]


def test_describe_changes_reports_real_reordering_and_status_change():
    cands = [bank("B1", lat=18.531, lng=73.841), bank("B2", lat=18.6, lng=73.9)]
    before = rank_candidates(req(), cands, now=NOW)
    after = rank_candidates(req(), cands, {("blood_bank", "B1"): Override("stale", "marked")}, now=NOW)
    changes = describe_changes(before, after)
    assert any("B1" in c and "moved from #1 to #2" in c for c in changes)
    assert any("B1" in c and "changed status" in c for c in changes)
