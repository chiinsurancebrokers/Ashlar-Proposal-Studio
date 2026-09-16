"""Persistent analyzed-case archive backed by Supabase.

Provider source documents and client case snapshots intentionally live in separate
Supabase tables. A case snapshot stores the structured analysis, evidence map, HAL
chat and generated client narrative so it can be reopened without re-running AI.
Original client quote files are NOT archived by this module.
"""
from __future__ import annotations

from datetime import datetime, timezone
from functools import lru_cache
import json
import os
import uuid


class CaseArchiveError(RuntimeError):
    pass


def _url() -> str:
    return os.getenv("SUPABASE_URL", "").strip().rstrip("/")


def _key() -> str:
    return os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()


def _table() -> str:
    return os.getenv("SUPABASE_CASE_TABLE", "analysis_cases").strip() or "analysis_cases"


def archive_configured() -> bool:
    return bool(_url() and _key())


@lru_cache(maxsize=2)
def _client(url: str, key: str):
    try:
        from supabase import create_client
    except ImportError as exc:
        raise CaseArchiveError("The supabase Python package is not installed.") from exc
    return create_client(url, key)


def _sb():
    if not archive_configured():
        raise CaseArchiveError("Supabase credentials are not configured.")
    return _client(_url(), _key())


def _json_safe(value):
    """Round-trip through JSON to convert tuples/sets and fail early on bad state."""
    def default(obj):
        if isinstance(obj, set):
            return sorted(obj)
        if isinstance(obj, tuple):
            return list(obj)
        return str(obj)
    return json.loads(json.dumps(value, default=default, ensure_ascii=False))


def save_case_snapshot(
    *,
    case_id: str | None,
    case_reference: str,
    client_name: str,
    client_profile: str,
    client_priorities: str,
    client_sex: str = "Not specified",
    client_age: int | None = None,
    report_language: str = "English",
    results: list[dict],
    case_chat: list[dict] | None = None,
    client_analysis: dict | None = None,
    status: str = "analyzed",
) -> dict:
    if not archive_configured():
        raise CaseArchiveError("Supabase Case Archive is not configured.")

    now = datetime.now(timezone.utc).isoformat()
    doc_id = case_id or uuid.uuid4().hex
    row = {
        "id": doc_id,
        "case_reference": (case_reference or "").strip() or None,
        "client_name": (client_name or "").strip() or None,
        "client_profile": (client_profile or "").strip() or None,
        "client_priorities": (client_priorities or "").strip() or None,
        "client_sex": (client_sex or "Not specified").strip(),
        "client_age": int(client_age) if client_age not in (None, "") else None,
        "report_language": report_language or "English",
        "results_json": _json_safe(results or []),
        "case_chat_json": _json_safe(case_chat or []),
        "client_analysis_json": _json_safe(client_analysis) if client_analysis else None,
        "provider_count": len(results or []),
        "plan_summary": " · ".join(
            f"{(r.get('analysis') or {}).get('provider') or r.get('provider') or 'Provider'} {(r.get('analysis') or {}).get('plan_name') or r.get('target_plan') or ''}".strip()
            for r in (results or [])
        ) or None,
        "status": status,
        "updated_at": now,
    }
    try:
        existing = _sb().table(_table()).select("id,created_at").eq("id", doc_id).execute().data or []
        if existing:
            response = _sb().table(_table()).update(row).eq("id", doc_id).execute().data or [row]
        else:
            row["created_at"] = now
            response = _sb().table(_table()).insert(row).execute().data or [row]
        return response[0]
    except Exception as exc:
        raise CaseArchiveError(
            f"Could not save case to Supabase. Run supabase/cases_schema.sql once. Technical detail: {exc}"
        ) from exc


def list_saved_cases(limit: int = 100) -> list[dict]:
    if not archive_configured():
        return []
    try:
        rows = (
            _sb().table(_table())
            .select("id,case_reference,client_name,plan_summary,provider_count,status,report_language,created_at,updated_at")
            .order("updated_at", desc=True)
            .limit(limit)
            .execute()
        ).data or []
        return rows
    except Exception as exc:
        raise CaseArchiveError(
            f"Could not read saved cases. Run supabase/cases_schema.sql once. Technical detail: {exc}"
        ) from exc


def load_case(case_id: str) -> dict:
    try:
        rows = _sb().table(_table()).select("*").eq("id", case_id).execute().data or []
    except Exception as exc:
        raise CaseArchiveError(f"Could not load saved case: {exc}") from exc
    if not rows:
        raise CaseArchiveError("Saved case was not found.")
    return rows[0]


def delete_case(case_id: str) -> bool:
    try:
        rows = _sb().table(_table()).delete().eq("id", case_id).execute().data or []
        return bool(rows) or True
    except Exception as exc:
        raise CaseArchiveError(f"Could not delete saved case: {exc}") from exc
