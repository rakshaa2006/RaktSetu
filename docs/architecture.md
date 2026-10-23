# RaktSetu architecture

## Layers
```
React (Vite)  ->  services/api.js (only place with URLs)  ->  FastAPI routes (app/api/routes.py)
                                                              -> services/coordination.py (DB workflows)
                                                                   -> pure logic: ranking.py, freshness.py,
                                                                      recovery.py, core/rules.py, core/geo.py
                                                              -> SQLAlchemy models -> SQLite
```
The backend is the source of truth. The UI always updates from the server's response.
Pure modules (`ranking`, `freshness`, `recovery`, `rules`, `geo`) import no framework and are unit-tested directly.

## Data model (SQLite)
`blood_banks`, `donors` (seeded from CSV), `blood_requests` (patient + request), `candidate_states` (request-specific
state of one option, unique per request+option), `ranking_snapshots` (every ranking, versioned, never overwritten),
`audit_events` (append-only; no update/delete code). Timestamps are UTC. Record `last_updated` is ISO text so the demo
can include missing/invalid timestamps. Foreign keys are enforced.

## Blood group / component rules (screening only)
| Component | Rule |
|---|---|
| Whole Blood, Platelets | Identical ABO/Rh group only |
| Packed Red Cells | Identical, or standard red-cell compatible group (flagged "compatible - needs qualified review") |
| Plasma | Identical, or ABO-compatible (Rh ignored), flagged for review |

Blood-bank records must also match the requested component. Unknown inputs never match.
Qualified blood-bank staff make every final compatibility, eligibility and stock decision.

## Ranking (deterministic, no scores)
Priority tier (lower first): 0 confirmed+recent (or confirmed by coordinator on this request) - 1 awaiting confirmation -
2 reported+recent - 3 stale - 4 unverified - 5 unknown timestamp - 6 no response.
Then exact before compatible match; then for **Critical/Urgent**: known distance (nearer first), then capacity;
for **Routine**: capacity, then distance. Then blood bank before donor, then ID.
Urgency is a workflow priority and never lifts an option to a better tier.

Excluded: no blood-group/component match; declined; unavailable (record, zero units, or event); donor not consented.
Donors with no consent info, no recent response, or a recent decline are lowered or excluded with a stated reason.
A coordinator "Reinstate" (reason required) overrides record-level exclusions for that request only.

## Freshness
`recent` if age <= 6 h (`core/config.py`), `stale` if older, `unknown` if the timestamp is missing, unreadable, or in the future.
Visible label = unavailable > unknown > stale > confirmed / reported / unverified. Stale confirmation is never shown as confirmed.

## States
Request: open -> under_review / cancelled; under_review -> open / awaiting_confirmation / cancelled;
awaiting_confirmation -> under_review / partially_fulfilled / fulfilled / cancelled; partially_fulfilled -> awaiting_confirmation /
under_review / fulfilled / cancelled; fulfilled and cancelled are final. Fulfilled needs at least one option confirmed by a
recorded coordinator action plus an explicit "simulated action" confirmation.

Option: reported_available -> awaiting_confirmation / declined / unavailable / no_response / stale;
awaiting_confirmation -> confirmed_available / declined / unavailable / no_response / stale;
confirmed_available -> awaiting_confirmation / declined / unavailable / stale;
unverified, stale, no_response -> several non-final states; declined and unavailable -> awaiting_confirmation **only** through
"Reinstate option" with a reason. Invalid transitions return HTTP 409 with the allowed next states.

## API
`GET /api/health`, `/api/meta`, `/api/locations`, `/api/dashboard/summary`, `/api/blood-banks`, `/api/donors`
(optional `near_lat`+`near_lng`, `blood_group`, `component`); `GET/POST /api/requests`; `GET /api/requests/{id}`;
`GET /api/requests/{id}/recommendations[?version=N]`; `POST /api/requests/{id}/recommendations/recalculate`;
`GET /api/requests/{id}/timeline`; `POST /api/requests/{id}/events`; `PATCH /api/requests/{id}/status`.
Errors: 404 not found, 409 invalid transition, 422 validation / rule violation. Swagger at `/docs`.

## Privacy
Patient name, age, gender and blood group are stored only in `blood_requests`, never in CSVs, URLs, audit messages or logs.
Audit messages use generated IDs. Donors are pseudonymous and fictional. (Patient blood group is shown in the UI and in ranking
explanations, which are not part of the audit log.)
