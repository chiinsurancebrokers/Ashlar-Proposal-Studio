from __future__ import annotations

import os
from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from core.case_archive import load_case, CaseArchiveError
from core.jobs import create_job, get_job, JobQueueError
from core.storage import get_documents, list_catalog, materialize_document, LibraryStorageError
from core.brochure_tables import extract_target_plan_from_pdf

app = FastAPI(title="Ashlar Proposal Studio API", version="0.5.0")


def require_internal_key(x_ashlar_api_key: str | None = Header(default=None)) -> None:
    expected = os.getenv("ASHLAR_INTERNAL_API_KEY", "").strip()
    adviser_key = os.getenv("ADVISER_OS_LIBRARY_KEY", "").strip()
    allowed = {value for value in (expected, adviser_key) if value}
    if allowed and x_ashlar_api_key not in allowed:
        raise HTTPException(status_code=401, detail="Invalid internal API key")


class CaseJobRequest(BaseModel):
    case_id: str = Field(min_length=1)


class ChatJobRequest(CaseJobRequest):
    question: str = Field(min_length=1, max_length=8000)


class LibraryPlanRequest(BaseModel):
    provider: str = Field(min_length=1, max_length=120)
    product: str = Field(min_length=1, max_length=200)
    version: str = Field(min_length=1, max_length=80)
    target_plan: str = Field(min_length=1, max_length=200)


@app.get("/health")
def health():
    return {"status": "ok", "service": "ashlar-api", "version": "0.5.0"}


@app.get("/api/v1/library/catalog", dependencies=[Depends(require_internal_key)])
def provider_library_catalog():
    try:
        return {"catalog": list_catalog()}
    except LibraryStorageError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.post("/api/v1/library/plan-context", dependencies=[Depends(require_internal_key)])
def provider_library_plan_context(body: LibraryPlanRequest):
    try:
        docs = get_documents(body.provider, body.product, body.version)
    except LibraryStorageError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if not docs:
        raise HTTPException(status_code=404, detail="Provider Library product/version not found.")

    payload = []
    for doc in docs:
        focused = ""
        if doc.doc_type in {"brochure", "tob"} and doc.original_filename.lower().endswith(".pdf"):
            try:
                with materialize_document(doc) as path:
                    isolated = extract_target_plan_from_pdf(path, body.target_plan)
                focused = isolated.to_prompt_context() if isolated.rows else ""
            except Exception:
                focused = ""
        payload.append({
            "document_id": doc.id,
            "provider": doc.provider,
            "product": doc.product,
            "version": doc.version,
            "doc_type": doc.doc_type,
            "filename": doc.original_filename,
            "effective_from": doc.effective_from,
            "effective_to": doc.effective_to,
            "extracted_text": (doc.extracted_text or "")[:160000],
            "focused_table_context": focused[:60000],
        })
    return {
        "provider": body.provider,
        "product": body.product,
        "version": body.version,
        "target_plan": body.target_plan,
        "documents": payload,
    }


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
