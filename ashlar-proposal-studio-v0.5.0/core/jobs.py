"""Persistent background-job queue backed by Supabase Postgres."""
from __future__ import annotations

from datetime import datetime, timezone
from functools import lru_cache
import json
import os
import uuid


class JobQueueError(RuntimeError):
    pass


def _url() -> str:
    return os.getenv("SUPABASE_URL", "").strip().rstrip("/")


def _key() -> str:
    return os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()


def _table() -> str:
    return os.getenv("SUPABASE_JOB_TABLE", "analysis_jobs").strip() or "analysis_jobs"


def jobs_configured() -> bool:
    return bool(_url() and _key())


@lru_cache(maxsize=2)
def _client(url: str, key: str):
    from supabase import create_client
    return create_client(url, key)


def _sb():
    if not jobs_configured():
        raise JobQueueError("Supabase job queue is not configured.")
    return _client(_url(), _key())


def _safe(value):
    return json.loads(json.dumps(value, default=str, ensure_ascii=False))


def create_job(*, case_id: str, job_type: str, request: dict | None = None) -> dict:
    now = datetime.now(timezone.utc).isoformat()
    row = {
        "id": uuid.uuid4().hex,
        "case_id": case_id,
        "job_type": job_type,
        "status": "pending",
        "progress_stage": "Queued",
        "request_json": _safe(request or {}),
        "result_json": None,
        "error_message": None,
        "attempts": 0,
        "created_at": now,
        "updated_at": now,
    }
    try:
        data = _sb().table(_table()).insert(row).execute().data or [row]
        return data[0]
    except Exception as exc:
        raise JobQueueError(f"Could not create background job: {exc}") from exc


def get_job(job_id: str) -> dict:
    try:
        rows = _sb().table(_table()).select("*").eq("id", job_id).execute().data or []
    except Exception as exc:
        raise JobQueueError(f"Could not read background job: {exc}") from exc
    if not rows:
        raise JobQueueError("Background job not found.")
    return rows[0]


def update_job(job_id: str, **fields) -> dict:
    fields["updated_at"] = datetime.now(timezone.utc).isoformat()
    if "request_json" in fields:
        fields["request_json"] = _safe(fields["request_json"])
    if "result_json" in fields:
        fields["result_json"] = _safe(fields["result_json"])
    try:
        rows = _sb().table(_table()).update(fields).eq("id", job_id).execute().data or []
    except Exception as exc:
        raise JobQueueError(f"Could not update background job: {exc}") from exc
    return rows[0] if rows else {"id": job_id, **fields}


def claim_next_job(worker_id: str) -> dict | None:
    """Atomically claim one pending job via the SQL RPC from jobs_schema.sql."""
    try:
        rows = _sb().rpc("claim_analysis_job", {"p_worker_id": worker_id}).execute().data or []
    except Exception as exc:
        raise JobQueueError(
            f"Could not claim background job. Run supabase/jobs_schema.sql once. Technical detail: {exc}"
        ) from exc
    return rows[0] if rows else None
