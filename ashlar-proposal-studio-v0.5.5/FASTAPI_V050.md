# v0.5 — FastAPI + Background Worker

v0.5 separates the UI from long-running Claude work.

## Architecture

```text
Browser
  |
  v
Streamlit web service
  |  quick HTTP requests only
  v
FastAPI service
  |  creates/polls persistent jobs
  v
Supabase analysis_jobs
  |
  v
Worker service
  |-- Claude report generation
  |-- HAL chat
  |-- Pydantic report validation
  v
Supabase analysis_cases
```

The Provider Library remains in Supabase exactly as before.

## Why this fixes the blank/grey report problem

The old Streamlit monolith waited for the whole Claude request inside one Streamlit rerun. A slow request greyed the page, and syntactically valid but incomplete JSON could replace a good report.

v0.5 changes this:

1. Streamlit saves the analyzed case.
2. FastAPI creates a persistent job and immediately returns a `job_id`.
3. The worker performs the long-running model call outside Streamlit.
4. The resulting JSON must pass the `ClientReport` Pydantic schema and include every analyzed plan.
5. Only a validated report is written back to `analysis_cases`.
6. If generation fails, the previous report remains untouched.

The report prompt also receives a compact evidence digest (maximum 14 supporting evidence items per plan) rather than the full extraction audit.

## Supabase setup

Run these once in Supabase SQL Editor:

1. `supabase/schema.sql` — Provider Library (already done on existing installs)
2. `supabase/cases_schema.sql` — Saved Cases (already done on existing installs)
3. `supabase/jobs_schema.sql` — **new for v0.5**

No new Storage bucket is required for background jobs.

## Railway: three services from the SAME GitHub repository

Create three Railway services from the Proposal Studio repository.

### 1. Web service

Environment:

```env
ASHLAR_SERVICE=web
ASHLAR_API_URL=https://YOUR-ASHLAR-API-DOMAIN
ASHLAR_INTERNAL_API_KEY=<same-random-secret-as-api>
```

Keep the existing Supabase, Anthropic and Proposal Studio variables. The web service still uses Anthropic for quote/document extraction; client report generation and HAL will use the worker when `ASHLAR_API_URL` is configured.

Optional Railway health check (set in the Web service settings): `/_stcore/health`

### 2. API service

Environment:

```env
ASHLAR_SERVICE=api
ASHLAR_INTERNAL_API_KEY=<same-random-secret-as-web>
SUPABASE_URL=...
SUPABASE_SERVICE_ROLE_KEY=...
SUPABASE_CASE_TABLE=analysis_cases
SUPABASE_JOB_TABLE=analysis_jobs
```

Generate a Railway domain for this service and put that URL into the web service's `ASHLAR_API_URL`.

Optional Railway health check (set in the API service settings): `/health`

The API does not need the Anthropic key.

### 3. Worker service

Environment:

```env
ASHLAR_SERVICE=worker
ANTHROPIC_API_KEY=...
CLAUDE_MODEL=...
HAL_CHAT_MODEL=...
CLIENT_ANALYSIS_MODEL=...
SUPABASE_URL=...
SUPABASE_SERVICE_ROLE_KEY=...
SUPABASE_CASE_TABLE=analysis_cases
SUPABASE_JOB_TABLE=analysis_jobs
```

Do not expose a public domain for the worker. Leave HTTP health checks disabled for this service; Railway should simply keep the process running.

`railway.json` intentionally does not hard-code a health-check path because the same repository is used by all three service types.

Optional:

```env
CLIENT_ANALYSIS_TIMEOUT_SECONDS=90
CLIENT_ANALYSIS_MAX_TOKENS=4500
HAL_CHAT_TIMEOUT_SECONDS=45
ASHLAR_WORKER_POLL_SECONDS=1.5
```

## FastAPI endpoints

- `GET /health`
- `POST /api/v1/jobs/report`
- `POST /api/v1/jobs/chat`
- `GET /api/v1/jobs/{job_id}`

If `ASHLAR_INTERNAL_API_KEY` is configured, all `/api/v1/*` routes require it via `x-ashlar-api-key`.

## Safe fallback

If `ASHLAR_API_URL` is not configured, Streamlit falls back to local synchronous report/HAL generation. Even in fallback mode, v0.5 validates the report before replacing the previous version.
