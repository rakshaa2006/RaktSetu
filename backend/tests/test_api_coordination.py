from tests.conftest import post_event, recs


def ranked_ids(body):
    return [i["candidate_id"] for i in body["current"]["ranked"]]


def excluded_ids(body):
    return [i["candidate_id"] for i in body["current"]["excluded"]]


def test_initial_recommendations_are_filtered_explained_and_deterministic(client, created, payload):
    body = recs(client, created["id"])
    ranked = body["current"]["ranked"]
    assert body["current"]["version"] == 1 and ranked
    assert all(i["explanation"] for i in ranked)
    assert [i["rank"] for i in ranked] == list(range(1, len(ranked) + 1))
    for item in ranked:  # only matched blood groups for O+ red cells; banks must be red-cell stock
        assert item["blood_group"] in ("O+", "O-")
        if item["candidate_type"] == "blood_bank":
            assert item["component"] == "Packed Red Cells"
    other = client.post("/api/requests", json=payload).json()["id"]
    assert ranked_ids(recs(client, other)) == ranked_ids(body)
    assert ranked_ids(recs(client, created["id"])) == ranked_ids(body)   # reading does not change it


def test_stale_and_unknown_records_rank_below_recent_ones(client, created):
    ranked = recs(client, created["id"])["current"]["ranked"]
    labels = [i["verification_label"] for i in ranked]
    first_weak = min(i for i, lab in enumerate(labels) if lab in ("stale", "unknown", "unverified"))
    assert all(lab in ("confirmed", "reported") for lab in labels[:first_weak])
    assert all(lab not in ("confirmed", "reported") for lab in labels[first_weak:])


def test_stock_unavailable_removes_bank_and_recalculates(client, created):
    before = recs(client, created["id"])
    top = before["current"]["ranked"][0]
    assert top["candidate_type"] == "blood_bank"
    r = post_event(client, created["id"], "STOCK_UNAVAILABLE", "blood_bank", top["candidate_id"])
    assert r.status_code == 201, r.text
    body = r.json()["recommendations"]
    assert top["candidate_id"] not in ranked_ids(body)
    assert top["candidate_id"] in excluded_ids(body)
    assert body["current"]["version"] == 2
    assert any(top["candidate_id"] in c for c in body["current"]["changes"])
    assert r.json()["event"]["is_simulation"] is True
    # earlier recommendation is preserved
    old = client.get(f"/api/requests/{created['id']}/recommendations", params={"version": 1}).json()
    assert ranked_ids(old) == ranked_ids(before)
    assert [h["version"] for h in body["history"]] == [2, 1]


def test_declined_donor_is_excluded_and_cannot_be_recommended_again(client, created):
    donor_id = next(i["candidate_id"] for i in recs(client, created["id"])["current"]["ranked"] if i["candidate_type"] == "donor")
    assert post_event(client, created["id"], "DONOR_DECLINED", "donor", donor_id).status_code == 201
    body = recs(client, created["id"])
    assert donor_id not in ranked_ids(body) and donor_id in excluded_ids(body)
    again = post_event(client, created["id"], "SELECT_FOR_REVIEW", "donor", donor_id)
    assert again.status_code == 409
    assert donor_id not in ranked_ids(client.post(f"/api/requests/{created['id']}/recommendations/recalculate").json())


def test_reinstatement_needs_reason_and_restores_the_option(client, created):
    rid = created["id"]
    donor_id = next(i["candidate_id"] for i in recs(client, rid)["current"]["ranked"] if i["candidate_type"] == "donor")
    post_event(client, rid, "DONOR_DECLINED", "donor", donor_id)
    assert post_event(client, rid, "REINSTATE_CANDIDATE", "donor", donor_id).status_code == 422
    ok = post_event(client, rid, "REINSTATE_CANDIDATE", "donor", donor_id, "Donor phoned to say yes")
    assert ok.status_code == 201
    assert donor_id in ranked_ids(ok.json()["recommendations"])


def test_nonresponse_is_not_acceptance(client, created):
    rid = created["id"]
    donor = next(i for i in recs(client, rid)["current"]["ranked"] if i["candidate_type"] == "donor")
    r = post_event(client, rid, "DONOR_NO_RESPONSE", "donor", donor["candidate_id"])
    assert r.status_code == 201
    item = next(i for i in r.json()["recommendations"]["current"]["ranked"] if i["candidate_id"] == donor["candidate_id"])
    assert item["review_status"] == "no_response"
    assert item["verification_label"] == "not_confirmed"
    assert item["rank"] > donor["rank"]


def test_stale_event_lowers_priority(client, created):
    rid = created["id"]
    top = recs(client, rid)["current"]["ranked"][0]
    r = post_event(client, rid, "DATA_STALE", top["candidate_type"], top["candidate_id"])
    assert r.status_code == 201
    new = next(i for i in r.json()["recommendations"]["current"]["ranked"] if i["candidate_id"] == top["candidate_id"])
    assert new["review_status"] == "stale" and new["rank"] > 1


def test_wrong_event_for_candidate_type_is_rejected(client, created):
    assert post_event(client, created["id"], "STOCK_UNAVAILABLE", "donor", "DN-001").status_code == 422
    assert post_event(client, created["id"], "DONOR_DECLINED", "blood_bank", "BB-001").status_code == 422
    assert post_event(client, created["id"], "DONOR_DECLINED").status_code == 422
    assert client.post(f"/api/requests/{created['id']}/events", json={"event_type": "NOPE"}).status_code == 422


def test_timeline_is_ordered_complete_and_free_of_patient_details(client, created, payload):
    rid = created["id"]
    top = recs(client, rid)["current"]["ranked"][0]
    post_event(client, rid, "STOCK_UNAVAILABLE", "blood_bank", top["candidate_id"])
    events = client.get(f"/api/requests/{rid}/timeline").json()
    types = [e["event_type"] for e in events]
    assert types[0] == "REQUEST_CREATED" and types[1] == "RANKING_GENERATED"
    assert "STOCK_REPORTED_UNAVAILABLE" in types and types[-1] == "RANKING_RECALCULATED"
    stamps = [e["timestamp"] for e in events]
    assert stamps == sorted(stamps)
    ids = [e["event_id"] for e in events]
    assert len(set(ids)) == len(ids)
    failure = next(e for e in events if e["event_type"] == "STOCK_REPORTED_UNAVAILABLE")
    assert failure["previous_state"] and failure["new_state"] == "unavailable" and failure["candidate_id"] == top["candidate_id"]
    text = " ".join(e["reason"] for e in events)
    assert payload["patient_name"] not in text and "Alpha" not in text


def test_events_are_never_deleted_when_ranking_changes(client, created):
    rid = created["id"]
    n0 = len(client.get(f"/api/requests/{rid}/timeline").json())
    top = recs(client, rid)["current"]["ranked"][0]
    post_event(client, rid, "STOCK_UNAVAILABLE", "blood_bank", top["candidate_id"])
    n1 = len(client.get(f"/api/requests/{rid}/timeline").json())
    assert n1 > n0


def test_selecting_for_review_does_not_fulfil_the_request(client, created):
    rid = created["id"]
    top = recs(client, rid)["current"]["ranked"][0]
    r = post_event(client, rid, "SELECT_FOR_REVIEW", top["candidate_type"], top["candidate_id"])
    assert r.status_code == 201
    assert r.json()["request"]["status"] == "under_review"
    item = next(i for i in r.json()["recommendations"]["current"]["ranked"] if i["candidate_id"] == top["candidate_id"])
    assert item["review_status"] == "awaiting_confirmation"


def test_invalid_status_transitions(client, created):
    rid = created["id"]
    r = client.patch(f"/api/requests/{rid}/status", json={"status": "fulfilled", "simulated_confirmation": True})
    assert r.status_code == 409 and "Allowed next statuses" in r.json()["detail"]
    assert client.patch(f"/api/requests/{rid}/status", json={"status": "open"}).status_code == 409
    assert client.patch(f"/api/requests/{rid}/status", json={"status": "nonsense"}).status_code == 422
    assert client.patch(f"/api/requests/{rid}/status", json={"status": "cancelled"}).status_code == 422  # reason needed


def test_full_happy_path_to_simulated_fulfilment(client, created):
    rid = created["id"]
    top = recs(client, rid)["current"]["ranked"][0]
    post_event(client, rid, "SELECT_FOR_REVIEW", top["candidate_type"], top["candidate_id"])
    assert client.patch(f"/api/requests/{rid}/status", json={"status": "awaiting_confirmation"}).status_code == 200
    # fulfilled without a recorded confirmation is refused
    refused = client.patch(f"/api/requests/{rid}/status", json={"status": "fulfilled", "simulated_confirmation": True})
    assert refused.status_code == 422
    assert post_event(client, rid, "CONFIRM_AVAILABILITY", top["candidate_type"], top["candidate_id"]).status_code == 201
    no_flag = client.patch(f"/api/requests/{rid}/status", json={"status": "fulfilled"})
    assert no_flag.status_code == 422
    done = client.patch(f"/api/requests/{rid}/status", json={"status": "fulfilled", "simulated_confirmation": True})
    assert done.status_code == 200 and done.json()["status"] == "fulfilled"
    events = client.get(f"/api/requests/{rid}/timeline").json()
    last_status = [e for e in events if e["event_type"] == "REQUEST_STATUS_UPDATED"][-1]
    assert last_status["is_simulation"] is True and "simulated" in last_status["reason"].lower()
    # a finished request accepts no more events or transitions
    assert post_event(client, rid, "DATA_STALE", "donor", "DN-001").status_code == 409
    assert client.patch(f"/api/requests/{rid}/status", json={"status": "open"}).status_code == 409


def test_coordinator_note_is_recorded_without_changing_ranking(client, created):
    rid = created["id"]
    r = client.post(f"/api/requests/{rid}/events", json={"event_type": "COORDINATOR_NOTE", "reason": "Called ward to confirm need"})
    assert r.status_code == 201 and r.json()["event"]["event_type"] == "COORDINATOR_ACTION_RECORDED"
    assert r.json()["recommendations"]["current"]["version"] == 1
    assert client.post(f"/api/requests/{rid}/events", json={"event_type": "COORDINATOR_NOTE"}).status_code == 422


def test_manual_recalculation_adds_a_version_and_event(client, created):
    rid = created["id"]
    body = client.post(f"/api/requests/{rid}/recommendations/recalculate").json()
    assert body["current"]["version"] == 2
    assert client.get(f"/api/requests/{rid}/timeline").json()[-1]["event_type"] == "RANKING_RECALCULATED"
    assert client.get(f"/api/requests/{rid}/recommendations", params={"version": 99}).status_code == 404
