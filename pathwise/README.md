# Pathwise

AI-powered job marketplace: external job aggregation, CV parsing, transparent CV-to-job match scores, recommendations, native applications, email notifications and role-based dashboards.

React + Vite frontend, FastAPI + SQLAlchemy backend, **SQLite as the only database** (WAL, foreign keys, busy timeout, FTS5 search, Alembic migrations). No vector database: embeddings are stored in SQLite and compared in-process.

## Run locally

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m spacy download en_core_web_sm   # used to validate candidate names and locations parsed from CVs
cp .env.example .env                      # set PATHWISE_SECRET_KEY, PATHWISE_ADMIN_EMAIL, PATHWISE_ADMIN_PASSWORD
alembic upgrade head
uvicorn app.main:app --port 8000
```

```bash
cd frontend
npm install
npm run dev        # http://localhost:5173, proxies /api to :8000
```

API docs: http://localhost:8000/docs

The admin account is created at startup from `PATHWISE_ADMIN_EMAIL` / `PATHWISE_ADMIN_PASSWORD` (must be a valid, non-reserved email domain). Register candidate, employer and recruiter accounts from the UI.

## Configuration (`backend/.env`, prefix `PATHWISE_`)

| Variable | Purpose |
|---|---|
| `SECRET_KEY` | Token signing key. Set a long random value in production. |
| `DATABASE_URL` | SQLite URL, default `backend/pathwise.db`. |
| `EMAIL_BACKEND` | `console` (logs emails) or `smtp` with `SMTP_*` settings. |
| `REQUIRE_EMAIL_VERIFICATION` | Block login until the email is verified. |
| `EMBEDDING_BACKEND` | `auto` uses Sentence Transformers when installed, else a TF-IDF fallback. |
| `LLM_EXTRACTION_ENABLED`, `ANTHROPIC_API_KEY` | Optional LLM enrichment. Only used for candidates who consented; never invents qualifications. |
| `ADZUNA_APP_ID`, `ADZUNA_APP_KEY` | Enable the Adzuna source (disabled without credentials). |
| `WORKER_ENABLED` | Background worker: resume processing, email outbox with retries, job refresh and expiry, daily backup. |

## Architecture

```
backend/app
  core/          config, SQLite engine and pragmas, security, dependencies, rate limiting
  models/        SQLAlchemy models (41 tables)
  schemas/       Pydantic request and response models
  routers/       auth, profiles, jobs, candidate_ops, hiring, notifications, admin
  services/      auth, jobs, search (FTS5), aggregation, resume, matching, recommendations,
                 applications, notifications, analytics, worker
  adapters/      one adapter per external source (Remotive, Arbeitnow, Jobicy, Remote OK, Adzuna)
frontend/src     pages by role, shared components, API client
```

## Resume processing

PDF (pypdf) and DOCX (python-docx) text is split into sections, then skills are matched against the admin-managed skills taxonomy, experience and education are parsed with date handling for `Mar 2020`, `2025-06` and `06/2025` styles, and each extracted item keeps the source line as evidence so candidates can verify it. spaCy NER validates the candidate name and location when the `en_core_web_sm` model is installed; without it the parser uses its heuristics only. Candidates review and correct everything before it feeds matching.

## Matching

`score = 0.45 skills + 0.20 experience + 0.10 education + 0.10 location + 0.10 semantic + 0.05 preferences`, each component 0-100. Dimensions with no data (for example a job with no education requirement) are marked not applicable and their weight is redistributed, so a missing requirement never lowers or inflates a score. Weights are versioned in `matching_model_versions` and editable by admins. The score estimates profile-to-job compatibility, not hiring probability. Gender, age, ethnicity, religion and photos are never inputs.

## Job sources

Adapters use official APIs and feeds only, respect each provider's minimum refresh interval, record every run in `source_sync_runs` and `ingestion_logs`, deduplicate by source id and by a normalized title/company/location fingerprint, and expire jobs that disappear from a feed. External jobs show "Originally posted on <source>" and link to the original application page.

## SQLite operations

Run a single API process (one writer) against the database file. Do not share the file between machines.

```bash
python scripts/backup.py                      # online backup to backend/backups (last 14 kept; also runs daily in the worker)
python scripts/restore.py backups/<file>.db   # stop the server first; integrity-checked
```

## Tests

```bash
cd backend && pytest
cd frontend && npm test
```
