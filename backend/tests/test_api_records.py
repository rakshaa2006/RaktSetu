def test_blood_banks_list_and_labels(client):
    banks = {b["id"]: b for b in client.get("/api/blood-banks").json()}
    assert len(banks) >= 10
    assert banks["BB-001"]["freshness"] == "recent" and banks["BB-001"]["verification_label"] == "confirmed"
    assert banks["BB-003"]["freshness"] == "stale" and banks["BB-003"]["verification_label"] == "stale"
    assert banks["BB-009"]["freshness"] == "unknown"          # missing timestamp
    assert banks["BB-013"]["freshness"] == "unknown"          # invalid timestamp
    assert banks["BB-007"]["verification_label"] == "unavailable"
    assert banks["BB-010"]["latitude"] is None
    assert all(b["is_simulated"] for b in banks.values())


def test_donors_list_is_pseudonymous(client):
    donors = client.get("/api/donors").json()
    assert len(donors) >= 20
    assert all(d["display_name"].startswith("Donor ") for d in donors)
    assert {"declined_recently", "no_recent_response"} <= {d["response_status"] for d in donors}


def test_nearby_discovery_sorts_by_straight_line_distance(client):
    params = {"near_lat": 18.5308, "near_lng": 73.8475}
    banks = client.get("/api/blood-banks", params=params).json()
    known = [b["distance_km"] for b in banks if b["distance_km"] is not None]
    assert known == sorted(known)
    assert banks[-1]["distance_km"] is None                    # missing coordinates last
    assert "not road distance" in banks[0]["distance_note"]


def test_nearby_requires_both_coordinates(client):
    assert client.get("/api/blood-banks", params={"near_lat": 18.5}).status_code == 422


def test_filter_blood_banks_by_group_and_component(client):
    rows = client.get("/api/blood-banks", params={"blood_group": "O+", "component": "Packed Red Cells"}).json()
    assert rows and all(b["blood_group"] == "O+" and b["component"] == "Packed Red Cells" for b in rows)


def test_locations_and_meta_and_dashboard(client, created):
    assert len(client.get("/api/locations").json()) >= 10
    meta = client.get("/api/meta").json()
    assert "O+" in meta["blood_groups"] and "fulfilled" in meta["request_statuses"]
    dash = client.get("/api/dashboard/summary").json()
    assert dash["requests_total"] == 1 and dash["requests_urgent_active"] == 1
    assert dash["recent_activity"]
