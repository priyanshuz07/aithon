# AI Behavior Firewall 2.0

A local, application-level cybersecurity prototype that collects privacy-limited interaction events, evaluates estimated behavioral patterns with explainable rules and an optional synthetic-data classifier, records an adaptive response, and presents persisted sessions in a live dashboard. It is a hackathon demonstration, not a production firewall and not a guarantee of bot detection.

## System architecture

```text
Browser pages + privacy-aware SDK
  -> POST /api/session/start and POST /api/events
  -> FastAPI validation, deduplication, size limits, and rate limits
  -> SQLite sessions, accepted events, risk scores, decisions, and challenges
  -> Server-derived event features -> explainable rules + optional ML probability
  -> ALLOW / CHALLENGE / DELAY / BLOCK demo policy
  -> Dashboard summary, scenario lab, and session decision history
```

The browser may send an aggregate snapshot for display, but risk scores are computed from accepted database event rows and server-controlled receipt times. Clients cannot provide a risk score or select an action. The recommendation and actual response are stored separately.

## Technologies

- Python 3.14-tested, FastAPI, Pydantic, SQLAlchemy 2, and SQLite.
- Scikit-learn `StandardScaler` + `LogisticRegression`, trained on deterministic synthetic behavioral profiles; joblib artifact is optional.
- HTML, CSS, JavaScript, and CDN-hosted Chart.js and Lucide icons for the website and dashboard.
- `unittest` and FastAPI `TestClient` for API, database, risk, model, migration, privacy, and adaptive-response checks.

Python and the installed `.venv` are used for local development, training, and tests. The browser loads dashboard chart and icon libraries from their CDNs.

## Windows installation

Run from PowerShell at the project root:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
Copy-Item .env.example .env
Push-Location frontend
npm ci
Pop-Location
```

Activation is optional; the run commands below call the virtual-environment Python directly. `.env` is optional. Do not commit administrator keys or other secrets.

## Run the application

Start the backend in the first terminal:

```powershell
Set-Location backend
..\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Start the frontend in a second terminal from the project root. This launcher anchors the static document root to `frontend/`, so internal page links do not depend on the current terminal directory:

```powershell
\.venv\Scripts\python.exe frontend\serve.py --host 127.0.0.1 --port 5500
```

Open <http://127.0.0.1:5500/>. Dashboard: <http://127.0.0.1:5500/dashboard.html>. API health: <http://127.0.0.1:8000/api/health>. Interactive API documentation: <http://127.0.0.1:8000/docs>.

If another process already owns port `5500`, use `--port 5501` and open the matching `http://127.0.0.1:5501/` URLs. The API CORS defaults include both ports. A Python `http.server` 404 saying “File not found” means the URL path is not under that server's document root; use `frontend\serve.py` from the project root instead of launching `python -m http.server` from an arbitrary directory.

At startup the service creates/migrates SQLite tables, then purges sessions older than the configured retention window. The default database is `data/behavior_firewall.db`.

## Deploy on Vercel

The root `main.py` exposes the existing `backend/app/main.py` app using Vercel's default Python entrypoint convention without shadowing the backend's `app` package. With the tool-only `pyproject.toml` removed, Vercel installs the single dependency list from the root `requirements.txt` rather than trying to lock an incomplete project file. The FastAPI app serves the existing `frontend/` directory, and browser API calls use same-origin `/api` paths on Vercel. Local static development keeps using `127.0.0.1:8000` through `frontend/api-config.js`.

1. Import this repository in Vercel and keep the project Root Directory at the repository root. Do not set it to `backend/` or `frontend/`.
2. Use the FastAPI framework preset if Vercel detects it; otherwise choose **Other**. Keep the default install/build settings so Vercel installs from `requirements.txt`.
3. Add a stable, randomly generated `DEMO_CHALLENGE_SECRET` environment variable. Add `ADMIN_API_KEY` only if administrator review is needed. `SAFE_DEMO_MODE` must remain `true`.
4. Deploy a preview with `vercel`, check `/api/health`, `/docs`, `/`, and `/dashboard.html`, then promote it with `vercel --prod` or Vercel's production deployment flow.

The default Vercel SQLite database is `/tmp/behavior_firewall.db`. It is writable for a function instance but ephemeral and not shared across instances; sessions can disappear after a cold start or be inconsistent between instances. Use it only for disposable demos. For persistent production sessions, provision a managed PostgreSQL database, install a PostgreSQL SQLAlchemy driver such as `psycopg[binary]`, set `DATABASE_URL` to its connection URL, and run/validate the schema migrations against that database. This project does not silently replace SQLite or configure a hosted database for you.

The generated model artifact `data/behavior_model.joblib` is ignored by Git. Vercel can bundle it when it is supplied in the deployment source, but a Git-based deployment will not contain this ignored local file by default. Without the artifact, the existing rule-based risk scoring still runs and the dashboard reports the optional classifier as unavailable. To deploy the trained classifier, deliberately add the artifact to the deployment source and set `ML_MODEL_PATH` only if it is stored at a non-default path.

The dashboard chart and icon scripts use external CDNs, as the existing product images do. A restrictive network or Content Security Policy that blocks those CDNs will disable charts/icons, but does not affect the API or stored session data.

## Machine-learning model

The classifier is optional. With no artifact, the application uses rules only and reports that the model is not trained. Train a local artifact from the project root:

```powershell
.\.venv\Scripts\python.exe -m ml.train --samples 2000 --seed 2026
```

The model is written to `data/behavior_model.joblib` (ignored by Git). The backend loads it automatically; restart the backend if it was already running when training completed. Alternatively, from `backend/`:

```powershell
..\.venv\Scripts\python.exe -m app.ml.train --samples 2000 --seed 2026
```

Training uses a deterministic balanced synthetic dataset and a held-out split. The dashboard/API show accuracy, precision, recall, F1, ROC-AUC, sample type, and training time when an artifact is present. **These metrics describe only the generated synthetic split. They do not establish real-world accuracy, generalization, or detection of real bots.**

The model contributes at most 15 points to the rule score, and is not sufficient by itself to produce a high-risk response. The rules and model probability are both returned/persisted as explainable signals. Model-assisted results are not machine-learned intent claims.

## Risk and adaptive response

Rule-based levels default to low `0-29`, medium `30-59`, high `60-79`, and critical `80-100`. Responses map independently: allow, demo verification challenge, configurable delay, and demo block page. Categories are estimated behavioral patterns, not assertions about a user's intent. Thresholds are configured with `RISK_MEDIUM_THRESHOLD`, `RISK_HIGH_THRESHOLD`, and `RISK_CRITICAL_THRESHOLD`.

`SAFE_DEMO_MODE` must remain `true`. Responses are enforced only in the local demo interface; the API, collector, and dashboard remain accessible for recovery/review. The arithmetic challenge is a human-verifiable prototype, not a production CAPTCHA. Critical response opens `frontend/blocked.html` with a persisted request ID and explanation; it is not a network-level block.

Administrator review is optional. Set `ADMIN_API_KEY` to a private value at least 24 characters long before starting the backend. The session detail panel sends it as a one-request Bearer token; it is not saved in browser storage. Without a configured key, the review endpoint returns `503`; invalid credentials return `401`. Manual review appends an actual-response decision and never overwrites the original recommendation. Review notes are stored but not returned by unauthenticated dashboard reads.

## AITHON demonstration

1. Start the backend and frontend using the commands above.
2. Open the dashboard and go to **Scenario lab**.
3. Run each server-defined synthetic profile:
   - A: normal browsing -> low risk / allow.
   - B: repetitive scraping-like page/request burst -> medium risk / challenge.
   - C: high-frequency repeated activity -> high risk / delay.
   - D: critical simulated combined signals -> critical risk / block.
4. Each result shows its score, estimated behavioral pattern, rule/model contributions, explanation, and recommended/actual response. Select the persisted session for its complete feature values and decision history.
5. The challenge scenario can also be demonstrated on a guarded storefront interaction after a session's server-computed response is `challenge`.

Only the named scenario IDs are accepted by the demo endpoint. Their events and timestamps are generated locally by the server; they do not use real users or send traffic to outside sites.

## Privacy and retention

The SDK records action identifiers/counts, page identifiers, event timing, request counts, and random UUID session/event IDs. It does not read or transmit passwords, form values, typed text, keystrokes, or payment data. Event payload schemas accept only short identifiers; invalid requests return sanitized validation errors. The SDK has a visible monitoring notice and can be disabled from the dashboard tools or through `monitor.disable()`.

Set `DATA_RETENTION_ENABLED=true|false` and `DATA_RETENTION_DAYS` (default `90`, range `1-3650`). On startup, expired sessions and linked events, risk scores, decisions, challenges, deduplication entries, and identities are purged together. The SQLite database is local and excluded from Git. This prototype does not provide a user-facing export/erasure workflow or a distributed retention scheduler.

## Configuration

Settings may be supplied in `.env` or as environment variables:

- `DATABASE_URL`: local default is `sqlite:///../data/behavior_firewall.db`, relative to the backend working directory. On Vercel, the default is ephemeral `sqlite:////tmp/behavior_firewall.db`; configure a managed database URL for persistent storage.
- `ML_MODEL_PATH`: optional local joblib artifact; defaults to `data/behavior_model.joblib` at the project root.
- `RISK_MEDIUM_THRESHOLD`, `RISK_HIGH_THRESHOLD`, `RISK_CRITICAL_THRESHOLD`: defaults `30`, `60`, and `80`; values must be increasing.
- `DATA_RETENTION_ENABLED`, `DATA_RETENTION_DAYS`: startup cleanup switch and retention window (default enabled, 90 days).
- `SAFE_DEMO_MODE`: must remain `true`; the project intentionally has no production-enforcement mode.
- `ADAPTIVE_DELAY_MS`, `DEMO_CHALLENGE_TTL_SECONDS`: demo delay and challenge lifetime.
- `DEMO_CHALLENGE_SECRET`: optional stable challenge-signing secret; otherwise a process-local random secret is generated.
- `ADMIN_API_KEY`: optional private Bearer key, at least 24 characters, for manual review.
- `CORS_ORIGINS`: JSON array of browser origins, with local defaults in `.env.example`.

## REST API

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `POST` | `/api/session/start` | Create or return a random UUID session. |
| `POST` | `/api/events` | Validate, deduplicate, and store privacy-limited event batches. |
| `GET` | `/api/session/{session_id}` | Read timestamps, event counts, and latest aggregate snapshot. |
| `POST` | `/api/session/{session_id}/analyze` | Run server-derived rules plus optional ML inference and record recommendation/decision. |
| `GET` | `/api/session/{session_id}/access` | Return the server-computed recommendation and actual response. Client scores/actions are ignored/not accepted. |
| `POST` | `/api/session/{session_id}/challenge` | Issue a short-lived human demo challenge for a challenge decision. |
| `POST` | `/api/session/{session_id}/challenge/{challenge_id}/verify` | Record a challenge attempt and pass/fail decision. |
| `GET` | `/api/decision/{request_id}` | Read the safe explanation for a recorded block. |
| `POST` | `/api/admin/sessions/{session_id}/review` | Append an authenticated actual-response override. Requires `Authorization: Bearer <ADMIN_API_KEY>`. |
| `POST` | `/api/demo/scenarios/{normal\|automated\|high_frequency\|critical}` | Create one fixed synthetic demo session and return its analysis. |
| `GET` | `/api/dashboard/summary` | Return database-backed counters, recent sessions, distributions, hourly activity, and model status. |
| `GET` | `/api/dashboard/sessions/{session_id}` | Return a session's features, signals, model prediction, and decision history. |
| `GET` | `/api/health` | Check service/database availability. |

The event collector accepts batches of up to 50 events and 64 KiB per request. Event batches are limited to 120/minute per client; session starts to 30/minute; synthetic scenario creation to 12/minute. Existing `/api/v1` compatibility routes remain available.

## Automated tests

From the project root, run all backend tests:

```powershell
Set-Location backend
..\.venv\Scripts\python.exe -m unittest discover -s tests
```

This covers rule scoring and thresholds, synthetic data/model training and inference, model-plus-rule scoring, all four adaptive responses, human challenge pass/fail, administrator authentication and override history, client-metric tamper resistance, dashboard-to-database details, request validation/size limits, event deduplication, and schema/retention migrations.

Run the HTTP smoke test separately while the backend is running:

```powershell
Set-Location ..
.\.venv\Scripts\python.exe backend\tests\test_event_collection.py
```

## Current limitations

- The model is trained only on synthetic data; perfect or high synthetic metrics are not evidence of real-world performance.
- Heuristic and model categories are estimated patterns, not reliable attribution of user identity or intent.
- Safe responses are enforced in the local demo UI, not at a proxy, network, or production application boundary.
- The math challenge is not a CAPTCHA and can be automated.
- Request/session limits and demo scenario throttling are process-local and not distributed.
- Optional model artifacts are local joblib files and should be treated as trusted executable artifacts.
- The dashboard requires the local API. Chart.js is installed locally with `npm ci`; Lucide icons are CDN-hosted and may be absent without network access. Data endpoints remain local.

## Project layout

```text
backend/app/       FastAPI routes, scoring, ML runtime, persistence, and schemas
backend/tests/     API, risk, ML, adaptive, privacy, and database tests
frontend/          Multi-page website, privacy-aware SDK, adaptive guard, dashboard
ml/                Project-root model-training command
data/              Local SQLite database and ignored model artifact
requirements.txt   Python dependencies
```
