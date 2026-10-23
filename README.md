# RaktSetu

Emergency blood coordination and explainable decision support - a **hackathon demonstration**, not a clinical system.

RaktSetu helps hospital coordinators manage urgent blood requests by discovering nearby options, ranking them
transparently, flagging unreliable availability information, and re-ranking when an option fails.
All patients, donors, blood banks and events are **fictional / simulated**.

## What it does

1. Register a patient blood request (name, age, gender, blood group, component, units, hospital, urgency) - saved in SQLite.
2. Browse blood banks and registered donors with visible freshness labels.
3. Find nearby options by straight-line distance (optional Leaflet / OpenStreetMap map, list always works).
4. Get a rule-based ranking where every option has a plain-language explanation.
5. Simulate failures: stock unavailable, donor declines, donor does not respond, record goes stale - the ranking is recalculated and earlier rankings are kept.
6. See freshness rules applied (recent / stale / unverified / unavailable / unknown).
7. Read an append-only audit timeline for each request.

## Run it

You need Python 3.10+ and Node 18+. Two terminals.

**Backend** (terminal 1, from the project root):

```bash
cd backend
python -m venv .venv
# Windows PowerShell:  .venv\Scripts\Activate.ps1      Windows cmd: .venv\Scripts\activate.bat
# macOS / Linux:       source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

API docs (Swagger): http://localhost:8000/docs

On start-up the backend creates `backend/raktsetu.db` and loads the demo CSVs from `data/` (safe to repeat).

**Frontend** (terminal 2):

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173. The header shows "Server connected" when the backend is reachable.
The dev server must use port 5173 because the backend only allows that origin (change `RAKTSETU_CORS_ORIGINS` in `backend/.env` if needed).

**Seed the database manually** (from the project root, backend venv active):

```bash
python scripts/seed_data.py                      # add missing demo rows; never touches requests
python scripts/seed_data.py --refresh-timestamps # re-base "last updated" times to now
```

Demo timestamps are stored relative to seeding time (`last_updated_hours_ago` in the CSV). If the demo has been
running for a day, "recent" records will have aged into "stale" - that is the freshness rule working. Use
`--refresh-timestamps` to reset them. To start completely fresh, stop the backend and delete `backend/raktsetu.db`.

**Tests** (backend venv active):

```bash
cd backend
pytest
```

**Production build check:** `cd frontend && npm run build`.

## Configuration

| Setting | Where | Default |
|---|---|---|
| Backend URL used by the frontend | `frontend/.env.local` -> `VITE_API_BASE_URL` | `http://localhost:8000` |
| Allowed browser origin(s) | `backend/.env` -> `RAKTSETU_CORS_ORIGINS` | `http://localhost:5173,http://127.0.0.1:5173` |
| Database | `backend/.env` -> `RAKTSETU_DATABASE_URL` | `sqlite:///backend/raktsetu.db` |
| "Recent" window | `backend/app/core/config.py` -> `FRESHNESS.recent_hours` | 6 hours |

Copy the `.env.example` files to use them. No API keys, paid services, Docker or external LLMs are needed.

## Demo walkthrough (about 3 minutes)

1. **New request**: O+, Packed Red Cells, 2 units, Critical, location Shivajinagar (fictional patient).
2. On the request page, read the #1 option's explanation, then the stale and unknown-time options lower down.
3. Open **Failure simulation**, choose the #1 blood bank, and apply "Blood bank reports stock unavailable". See the new ranking, the "What changed" box, and the timeline entry.
4. Pick a donor and apply "Donor declines" - it moves to "Not recommended" and cannot be selected again unless reinstated with a reason.
5. Select an option for review, mark it "Confirmed (simulated)", then mark the request fulfilled (simulated).
6. Open **Ranking history** to view version 1 side by side with the latest.

## Important limitations

- Matching is a conservative application-level screen (see `docs/architecture.md`). It is **not** a medical compatibility decision.
- Distance is straight-line only. No road distance or travel time is shown.
- The audit log is application-level and append-only in code. It is **not** tamper-proof or legally certified.
- No messages are sent to anyone. Events are simulated by the coordinator.

## Packaging note

This archive was assembled in an offline environment. The pure decision logic (ranking, freshness, state rules, seeding)
was executed and tested there, and the frontend was syntax- and render-checked, but the FastAPI/SQLAlchemy API tests and
the Vite production build could not be run there. Run `pytest` and `npm run build` first on your machine and report any failure.

## Team workflow

Use one GitHub repository with `main` as the integration branch and short-lived feature branches merged by pull request.
(The team-collaboration section of the original brief was cut off, so no further conventions are assumed.)
