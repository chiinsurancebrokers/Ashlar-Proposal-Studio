"""Small client used by Streamlit to enqueue/poll FastAPI jobs."""
from __future__ import annotations

import os
import httpx


class AshlarAPIError(RuntimeError):
    pass


def api_url() -> str:
    return os.getenv("ASHLAR_API_URL", "").strip().rstrip("/")


def api_configured() -> bool:
    return bool(api_url())


def _headers() -> dict[str, str]:
    key = os.getenv("ASHLAR_INTERNAL_API_KEY", "").strip()
    return {"x-ashlar-api-key": key} if key else {}


def _request(method: str, path: str, *, json_body: dict | None = None, timeout: float = 15.0) -> dict:
    if not api_configured():
        raise AshlarAPIError("ASHLAR_API_URL is not configured.")
    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.request(method, f"{api_url()}{path}", headers=_headers(), json=json_body)
        response.raise_for_status()
        return response.json()
    except Exception as exc:
        raise AshlarAPIError(f"Ashlar API request failed: {exc}") from exc


def enqueue_report(case_id: str) -> dict:
    return _request("POST", "/api/v1/jobs/report", json_body={"case_id": case_id})


def enqueue_chat(case_id: str, question: str) -> dict:
    return _request("POST", "/api/v1/jobs/chat", json_body={"case_id": case_id, "question": question})


def fetch_job(job_id: str) -> dict:
    return _request("GET", f"/api/v1/jobs/{job_id}")
