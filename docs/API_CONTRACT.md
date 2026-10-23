# RaktSetu API Contract

## 1. Purpose
This document defines the HTTP API used by the RaktSetu frontend and backend.
The backend's FastAPI OpenAPI schema is the source of truth for exact fields.

## 2. Base URL
Default local backend: `http://localhost:8000`
Frontend environment variable: `VITE_API_BASE_URL`
Remove trailing slashes from the configured base URL before joining paths.

## 3. Endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/health` | Backend health |
| GET | `/api/meta` | Enums, rules and metadata |
| GET | `/api/locations` | Available locations |
| GET | `/api/blood-banks` | List/filter blood banks |
| GET | `/api/donors` | List/filter donors |
| GET | `/api/requests` | List requests |
| POST | `/api/requests` | Create a request; returns 201 |
| GET | `/api/requests/{request_id}` | Get request details |
| GET | `/api/requests/{request_id}/recommendations` | Get recommendations |
| POST | `/api/requests/{request_id}/recommendations/recalculate` | Recalculate recommendations; returns 201 |
| GET | `/api/requests/{request_id}/timeline` | Get audit timeline |
| POST | `/api/requests/{request_id}/events` | Record a coordination event; returns 201 |
| PATCH | `/api/requests/{request_id}/status` | Update request status |
| GET | `/api/requests/{request_id}/allocations` | List active and released allocations for a request |
| POST | `/api/requests/{request_id}/allocations` | Persist an allocation & stock reservation; returns 201 |
| POST | `/api/requests/{request_id}/allocations/{allocation_id}/release` | Release an allocation & recalculate fulfillment |
| GET | `/api/blood-banks/inbox` | List requests targeted to the authenticated blood bank |
| GET | `/api/blood-banks/{bank_id}/inbox` | List requests targeted to specified blood bank (token-verified) |
| POST | `/api/requests/{request_id}/approve` | Approve a targeted request (authenticated bank) |
| POST | `/api/blood-banks/{bank_id}/requests/{request_id}/approve` | Alias to approve a targeted request (token-verified) |
| POST | `/api/requests/{request_id}/reject` | Reject a targeted request with reason (authenticated bank) |
| POST | `/api/blood-banks/{bank_id}/requests/{request_id}/reject` | Alias to reject a targeted request (token-verified) |
| GET | `/api/dashboard/summary` | Dashboard summary |

## 4. Filters
Blood-bank filters: `near_lat`, `near_lng`, `blood_group`, `component`.
Donor filters: `near_lat`, `near_lng`, `blood_group`.
Supply `near_lat` and `near_lng` together or omit both. Latitude must be -90 to 90; longitude must be -180 to 180.
Any distance returned by the application is not a road-travel distance.
Recommendations support an optional `version` query parameter.

## 5. Create Request
`POST /api/requests`

Required fields:
- `patient_name`: string
- `patient_age`: integer, 0â€“120
- `patient_gender`: string enum
- `patient_blood_group`: string enum
- `component`: string enum
- `units_required`: integer, 1â€“20
- `hospital_name`: string
- `hospital_location`: string
- `urgency`: string enum

Optional fields:
- `hospital_latitude`: number or null
- `hospital_longitude`: number or null
- `target_blood_bank_id`: string (blood bank ID, e.g. "BB-001") or null. When supplied, validates the blood bank exists and initializes `approval_status` to `"pending"`. Retained as optional on the backend for backward compatibility with general pool requests, but requests requiring bank approval must target a valid blood bank.

Provide both hospital coordinates together or omit both.
The backend validates the request and returns a `RequestOut` response.

## 6. Authentication & Hackathon Demo Identity
Bank-specific operations (viewing inbox, approving, or rejecting targeted requests) require authentication via Bearer token:
`Authorization: Bearer <demo_token>`

- Demo token configuration is loaded via environment variable `RAKTSETU_DEMO_TOKENS` (JSON mapping `{"<token>": "<bank_id>"}` or comma-separated pairs `<token>:<bank_id>`).
- If `RAKTSETU_DEMO_TOKENS` is unconfigured, empty, or token is invalid, endpoints fail closed with `401 Unauthorized` (`WWW-Authenticate: Bearer`).
- The authenticated blood bank identity is derived strictly from the validated bearer token, never from a client-supplied query, path, or body parameter.
- Cross-bank isolation: If an endpoint includes `{bank_id}` in its path, the authenticated bank ID must match `{bank_id}`, else `403 Forbidden` is returned.
- If a blood bank attempts to approve or reject a request targeted to another bank, `403 Forbidden` is returned.
- **Security Notice**: Demo credentials and tokens do not verify real bank employees and must never be used in production environments.

## 7. Blood Request Approval Workflow
Patients and hospitals can submit requests targeted to a specific blood bank. The targeted blood bank reviews the request and either approves or rejects it.

### Workflow Separation:
Approval is an explicit administrative decision confirming willingness to process the request. **Approval does NOT reserve or allocate stock, issue units, or fulfill the request.** Stock reservation, candidate matching, and allocation remain separate operational steps.

### Inbox Endpoints
- `GET /api/blood-banks/inbox`: Lists requests targeted to the authenticated blood bank.
- `GET /api/blood-banks/{bank_id}/inbox`: Lists requests targeted to `{bank_id}` (requires Bearer token matching `{bank_id}`).
  - Query parameters (optional): `status` (open, under_review, etc.), `approval_status` (`pending`, `approved`, `rejected`), `limit`, `offset`.
  - Returns `list[RequestOut]`.

### Approve Endpoint
- `POST /api/requests/{request_id}/approve`
- `POST /api/blood-banks/{bank_id}/requests/{request_id}/approve` (alias, verifies `{bank_id}`)
  - Header: `Authorization: Bearer <token>`
  - Request body: `{}` (empty JSON object or omitted)
  - Success: `200 OK` returning updated `RequestOut`.
  - Status updates:
    - Sets `approval_status = "approved"`
    - Sets `decided_at = UTC timestamp`
    - Sets `decided_by_bank_id = <authenticated_bank_id>`
    - If request status was `open`, transitions request status to `under_review`
  - Audit Event: Records `REQUEST_APPROVED` in append-only audit log.
  - Conflict: Returns `409 Conflict` if `approval_status` is not `"pending"`.
  - Forbidden: Returns `403 Forbidden` if request is not targeted to the authenticated bank.

### Reject Endpoint
- `POST /api/requests/{request_id}/reject`
- `POST /api/blood-banks/{bank_id}/requests/{request_id}/reject` (alias, verifies `{bank_id}`)
  - Header: `Authorization: Bearer <token>`
  - Request body:
    ```json
    {
      "reason": "Required explanation of rejection (5 to 300 characters)"
    }
    ```
  - Validation: `reason` is required, trimmed length between 5 and 300 characters. Fails with `422 Unprocessable Entity` if omitted or out of bounds.
  - Success: `200 OK` returning updated `RequestOut`.
  - Status updates:
    - Sets `approval_status = "rejected"`
    - Sets `rejection_reason = <reason>`
    - Sets `decided_at = UTC timestamp`
    - Sets `decided_by_bank_id = <authenticated_bank_id>`
  - Audit Event: Records `REQUEST_REJECTED` in append-only audit log.
  - Conflict: Returns `409 Conflict` if `approval_status` is not `"pending"`.
  - Forbidden: Returns `403 Forbidden` if request is not targeted to the authenticated bank.

### Concurrency, Transaction Integrity, and Idempotency
- Approval and rejection decisions are executed via atomic conditional database updates (`UPDATE ... WHERE id = :id AND target_blood_bank_id = :bank_id AND approval_status = 'pending'`).
- Multi-process and multi-session concurrency safety: losing or repeated concurrent decision attempts update 0 rows, check current state, and return HTTP `409 Conflict`.
- Transaction atomicity: status modification, audit event recording, and ranking snapshot generation all participate in a single database transaction. If any step (such as audit logging or snapshot persistence) fails, the entire transaction is rolled back so that no partial, orphaned, or un-audited state remains committed.
- Exactly one decision is permitted per request; approved or rejected requests cannot be re-decided.

## 8. Enums
Blood groups: `A+`, `A-`, `B+`, `B-`, `AB+`, `AB-`, `O+`, `O-`.
Components: `Whole Blood`, `Packed Red Cells`, `Platelets`, `Plasma`.
Gender: `Female`, `Male`, `Other`, `Prefer not to say`.
Urgency: `Critical`, `Urgent`, `Routine`.
Request statuses: `open`, `under_review`, `awaiting_confirmation`,
`partially_fulfilled`, `fulfilled`, `cancelled`.
Approval statuses: `pending`, `approved`, `rejected`.
Candidate types: `blood_bank`, `donor`.
Event types: `STOCK_UNAVAILABLE`, `DONOR_DECLINED`, `DONOR_NO_RESPONSE`,
`DATA_STALE`, `SELECT_FOR_REVIEW`, `CONFIRM_AVAILABILITY`,
`REINSTATE_CANDIDATE`, `COORDINATOR_NOTE`, `REQUEST_APPROVED`, `REQUEST_REJECTED`.

Always confirm exact enum values and response fields against `/api/meta`
and the backend's OpenAPI schema.

## 9. Status and Event Operations
`PATCH /api/requests/{request_id}/status` accepts a status update.
`POST /api/requests/{request_id}/events` records a coordination event.
Use only valid state transitions and event types defined by the backend.
A no-response event is not acceptance or confirmation of availability.

## 10. Persisted Allocations and Shared Inventory
### Create Allocation
`POST /api/requests/{request_id}/allocations`

Request body:
```json
{
  "candidate_type": "blood_bank",
  "candidate_id": "BB-001",
  "units": 2,
  "idempotency_key": "optional-uuid"
}
```

Rules:
- Requires candidate confirmation (`confirmed_available`) for the request.
- Candidate blood group and component must be compatible with request.
- Donors: maximum 1 unit per request; verified consent required (`consented_demo`). Duplicate active donor allocation on the same request is rejected.
- Blood banks: units must not exceed usable stock minus active reservations across all requests (`available_to_allocate = usable_stock - active_reserved_units`).
- Total allocated units `A` cannot exceed request required units `R` (over-allocation rejected).
- Request status transitions automatically:
  - `A = 0`: request is not fulfilled.
  - `0 < A < R`: request is `partially_fulfilled`.
  - `A = R`: request is `fulfilled`.
- Atomic transaction: allocation, inventory reservation, request status update, and audit event are written together.
- Idempotency: replaying with the same key and identical payload returns the existing allocation without double-reserving; conflicting payload returns HTTP 422.

### Release Allocation
`POST /api/requests/{request_id}/allocations/{allocation_id}/release`

Optional request body:
```json
{
  "reason": "Coordinator note explaining release"
}
```

Releases reserved stock back to available inventory and recomputes request fulfillment state:
- If `A` drops to 0, request transitions to `awaiting_confirmation`.
- If `0 < A < R`, request transitions to `partially_fulfilled`.
- Audit event `ALLOCATION_RELEASED` is recorded.
- Request cancellation (`PATCH /status` with `cancelled`) automatically releases all active reservations.

## 11. Frontend Integration
- Use `VITE_API_BASE_URL` to configure the backend address.
- Do not hardcode different base URLs throughout the frontend.
- Handle loading, empty results, validation errors and network failures.
- Use the backend's actual response fields; do not invent fields.
- When frontend and backend run on different devices, configure the backend
  host, CORS and frontend base URL for the local network.

## 12. Safety and Demo Limitations
RaktSetu is a hackathon coordination and decision-support prototype.
Demo records and simulated actions do not establish real blood availability.
A human coordinator must independently verify donor or blood-bank availability
before communicating a real-world confirmation.

## 13. Implementation References
Backend routes: `backend/app`
Frontend API client: `frontend/src/services/api.js`
Backend tests: `backend/tests`
