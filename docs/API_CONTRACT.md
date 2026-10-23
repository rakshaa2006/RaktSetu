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

Provide both hospital coordinates together or omit both.
The backend validates the request and returns a `RequestOut` response.

## 6. Enums
Blood groups: `A+`, `A-`, `B+`, `B-`, `AB+`, `AB-`, `O+`, `O-`.
Components: `Whole Blood`, `Packed Red Cells`, `Platelets`, `Plasma`.
Gender: `Female`, `Male`, `Other`, `Prefer not to say`.
Urgency: `Critical`, `Urgent`, `Routine`.
Request statuses: `open`, `under_review`, `awaiting_confirmation`,
`partially_fulfilled`, `fulfilled`, `cancelled`.
Candidate types: `blood_bank`, `donor`.
Event types: `STOCK_UNAVAILABLE`, `DONOR_DECLINED`, `DONOR_NO_RESPONSE`,
`DATA_STALE`, `SELECT_FOR_REVIEW`, `CONFIRM_AVAILABILITY`,
`REINSTATE_CANDIDATE`, `COORDINATOR_NOTE`.

Always confirm exact enum values and response fields against `/api/meta`
and the backend's OpenAPI schema.

## 7. Status and Event Operations
`PATCH /api/requests/{request_id}/status` accepts a status update.
`POST /api/requests/{request_id}/events` records a coordination event.
Use only valid state transitions and event types defined by the backend.
A no-response event is not acceptance or confirmation of availability.

## 8. Frontend Integration
- Use `VITE_API_BASE_URL` to configure the backend address.
- Do not hardcode different base URLs throughout the frontend.
- Handle loading, empty results, validation errors and network failures.
- Use the backend's actual response fields; do not invent fields.
- When frontend and backend run on different devices, configure the backend
  host, CORS and frontend base URL for the local network.

## 9. Safety and Demo Limitations
RaktSetu is a hackathon coordination and decision-support prototype.
Demo records and simulated actions do not establish real blood availability.
A human coordinator must independently verify donor or blood-bank availability
before communicating a real-world confirmation.

## 10. Implementation References
Backend routes: `backend/app`
Frontend API client: `frontend/src/services/api.js`
Backend tests: `backend/tests`
