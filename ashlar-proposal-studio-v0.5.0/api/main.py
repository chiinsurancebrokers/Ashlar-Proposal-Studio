from __future__ import annotations

import os
from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from core.case_archive import load_case, CaseArchiveError
from core.jobs import create_job, get_job, JobQueueError

app = FastAPI(title="Ashlar Proposal Studio API", version="0.5.0")


def require_internal_key(x_ashlar_api_key: str | None = Header(default=None)) -> None:
    expected = os.getenv("ASHLAR_INTERNAL_API_KEY", "").strip()
    if expected and x_ashlar_api_key != expected:
        raise HTTPException(status_code=401, detail="Invalid internal API key")


class CaseJobRequest(BaseModel):
    case_id: str = Field(min_length=1)


class ChatJobRequest(CaseJobRequest):
    question: str = Field(min_length=1, max_length=8000)


@app.get("/health")
def health():
    return {"status": "ok", "service": "ashlar-api", "version": "0.5.0"}


def _ensure_case(case_id: str) -> None:
    try:
        load_case(case_id)
    except CaseArchiveError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/v1/jobs/report", dependencies=[Depends(require_internal_key)], status_code=202)
def report_job(body: CaseJobRequest):
    _ensure_case(body.case_id)
    try:
        job = create_job(case_id=body.case_id, job_type="client_report")
    except JobQueueError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"job_id": job["id"], "status": job.get("status", "pending")}


@app.post("/api/v1/jobs/chat", dependencies=[Depends(require_internal_key)], status_code=202)
def chat_job(body: ChatJobRequest):
    _ensure_case(body.case_id)
    try:
        job = create_job(case_id=body.case_id, job_type="hal_chat", request={"question": body.question})
    except JobQueueError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"job_id": job["id"], "status": job.get("status", "pending")}


@app.get("/api/v1/jobs/{job_id}", dependencies=[Depends(require_internal_key)])
def job_status(job_id: str):
    try:
        job = get_job(job_id)
    except JobQueueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {
        "job_id": job.get("id"),
        "case_id": job.get("case_id"),
        "job_type": job.get("job_type"),
        "status": job.get("status"),
        "progress_stage": job.get("progress_stage"),
        "error_message": job.get("error_message"),
        "result": job.get("result_json"),
        "updated_at": job.get("updated_at"),
    }
