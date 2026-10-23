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
`audit_events` (append-only; no update/delete code), `allocations` (persisted unit allocations, lifecycle status
active/released, idempotency key and hash, shared inventory reservation tracking). Timestamps are UTC. Record
`last_updated` is ISO text so the demo can include missing/invalid timestamps. Foreign keys are enforced.

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

## States & Fulfillment
Request: open -> under_review / cancelled; under_review -> open / awaiting_confirmation / partially_fulfilled / fulfilled / cancelled;
awaiting_confirmation -> under_review / partially_fulfilled / fulfilled / cancelled; partially_fulfilled -> awaiting_confirmation /
under_review / fulfilled / cancelled; fulfilled and cancelled are terminal for manual status patching.

Fulfillment is strictly derived from active allocated units (A) versus required units (R):
- A = 0: request cannot be marked fulfilled or partially fulfilled.
- 0 < A < R: request is partially fulfilled.
- A = R: request is fulfilled.
- A > R: over-allocation is rejected.
- Allocation release recomputes fulfillment: if A becomes 0, status returns to awaiting_confirmation.
- Request cancellation automatically releases all active allocations back to available stock.

## Shared Inventory & Concurrency
Shared blood-bank stock is enforced across all concurrent requests:
`available_to_allocate = usable_stock - active_reserved_units`
Where usable_stock is bank inventory (0 if marked unavailable), and active_reserved_units is the sum of units across all
active allocations. Donors contribute at most 1 unit per donation and verified consent is enforced. Duplicate active donor
allocations on the same request are rejected. Process-level mutex synchronization combined with SQLite transaction boundaries
guarantees that race conditions cannot oversubscribe inventory (`sum(active_reservations) <= usable_stock`).

## API
`GET /api/health`, `/api/meta`, `/api/locations`, `/api/dashboard/summary`, `/api/blood-banks`, `/api/donors`
(optional `near_lat`+`near_lng`, `blood_group`, `component`); `GET/POST /api/requests`; `GET /api/requests/{id}`;
`GET /api/requests/{id}/recommendations[?version=N]`; `POST /api/requests/{id}/recommendations/recalculate`;
`GET /api/requests/{id}/timeline`; `POST /api/requests/{id}/events`; `PATCH /api/requests/{id}/status`;
`GET /api/requests/{id}/allocations`; `POST /api/requests/{id}/allocations`;
`POST /api/requests/{id}/allocations/{allocation_id}/release`.
Errors: 404 not found, 409 invalid transition, 422 validation / rule violation. Swagger at `/docs`.

## Privacy
Patient name, age, gender and blood group are stored only in `blood_requests`, never in CSVs, URLs, audit messages or logs.
Audit messages use generated IDs. Donors are pseudonymous and fictional. (Patient blood group is shown in the UI and in ranking
explanations, which are not part of the audit log.)
