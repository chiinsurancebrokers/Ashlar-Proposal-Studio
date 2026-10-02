from __future__ import annotations

import os
import tempfile
from pathlib import Path
from fastapi import Depends, FastAPI, File, Header, HTTPException, UploadFile
from pydantic import BaseModel, Field

from core.case_archive import load_case, CaseArchiveError
from core.jobs import create_job, get_job, JobQueueError
from core.extract import extract_document
from core.plan_selector import identify_selected_plan
from core.analyzer import analyze_target_plan
from core.carriers import get_carrier_adapter
from core.storage import list_documents, materialize_document, cache_document_text, create_document_signed_url

app = FastAPI(title="Ashlar Proposal Studio API", version="0.5.0")


def _supporting_wording_for(provider_label: str, carrier_id: str) -> tuple[str, list[dict]]:
    """Return cached/extracted wording text and client-safe document metadata.

    Provider Library documents are reusable insurer evidence. Applicant uploads
    remain case-specific and are never promoted into this library.
    """
    provider_key = (provider_label or carrier_id or "").casefold()
    aliases = {provider_key, carrier_id.casefold()}
    if carrier_id == "bupa":
        aliases.update({"bupa", "bupa global"})

    wording_types = {
        "policy wording", "policy_wording", "wording", "terms",
        "terms and conditions", "membership guide", "membership_guide",
        "guide", "table of benefits", "table_of_benefits",
    }
    try:
        docs = list_documents()
    except Exception:
        return "", []

    candidates = []
    for doc in docs:
        hay = " ".join([
            doc.provider or "", doc.product or "", doc.doc_type or "",
            doc.original_filename or "", doc.version or "",
        ]).casefold()
        if not any(alias and alias in hay for alias in aliases):
            continue
        dtype = (doc.doc_type or "").strip().casefold()
        if dtype not in wording_types and not any(k in hay for k in ("membership guide","policy wording","terms and conditions","table of benefits")):
            continue
        candidates.append(doc)

    # Latest uploads first. Limit context size and document count so a generic
    # carrier library cannot swamp the applicant-specific renewal evidence.
    candidates.sort(key=lambda d: (d.uploaded_at or "", d.version or ""), reverse=True)
    texts: list[str] = []
    metadata: list[dict] = []
    for doc in candidates[:4]:
        text_value = (doc.extracted_text or "").strip()
        if not text_value:
            try:
                with materialize_document(doc) as local_path:
                    extracted = extract_document(local_path, doc.original_filename)
                if extracted.ok:
                    text_value = extracted.text
                    try:
                        cache_document_text(doc.id, text_value)
                    except Exception:
                        pass
            except Exception:
                text_value = ""
        if text_value:
            texts.append(f"=== {doc.original_filename} ===\n{text_value[:70000]}")
        try:
            signed = create_document_signed_url(doc, expires_in_seconds=7 * 24 * 60 * 60)
        except Exception:
            signed = None
        metadata.append({
            "id": doc.id,
            "provider": doc.provider,
            "product": doc.product,
            "version": doc.version,
            "doc_type": doc.doc_type,
            "filename": doc.original_filename,
            "url": signed,
        })
    return "\n\n".join(texts), metadata


def require_internal_key(x_ashlar_api_key: str | None = Header(default=None)) -> None:
    expected = os.getenv("ASHLAR_INTERNAL_API_KEY", "").strip()
    if expected and x_ashlar_api_key != expected:
        raise HTTPException(status_code=401, detail="Invalid internal API key")


def require_hal_bridge_key(x_hal_bridge_key: str | None = Header(default=None)) -> None:
    expected = os.getenv("HAL_BRIDGE_API_KEY", "").strip()
    if not expected or x_hal_bridge_key != expected:
        raise HTTPException(status_code=401, detail="Invalid HAL bridge key")


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




@app.post("/api/v1/current-policy/analyze", dependencies=[Depends(require_hal_bridge_key)])
async def analyze_current_policy(file: UploadFile = File(...)):
    """Analyze one applicant-specific current policy/quote without storing it.

    The file is processed in a temporary location, converted into the same
    structured facts used by Proposal Studio, and deleted immediately after
    extraction/analysis. It is never promoted to the Provider Library.
    """
    filename = (file.filename or "current-policy.pdf").strip()
    suffix = Path(filename).suffix.lower()
    if suffix not in {".pdf", ".txt", ".html", ".htm"}:
        raise HTTPException(status_code=400, detail="Supported types: PDF, TXT, HTML")
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")
    if len(content) > 20 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Current policy file exceeds 20 MB")

    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(content)
            tmp_path = tmp.name
        extracted = extract_document(tmp_path, filename)
        if not extracted.ok:
            raise HTTPException(status_code=422, detail=extracted.error)

        adapter = get_carrier_adapter("Current policy", extracted.text)
        deterministic = adapter.extract_quote_facts(extracted.text)
        selection = identify_selected_plan(
            extracted.text,
            provider_label=adapter.display_name if adapter.carrier_id != "generic" else "Current policy",
            manual_override="",
        )
        target_plan = (
            deterministic.get("quoted_plan")
            or selection.get("plan_name")
            or "Current policy"
        ).strip()
        provider_label = adapter.display_name if adapter.carrier_id != "generic" else "Current policy"
        wording_text, supporting_documents = _supporting_wording_for(provider_label, adapter.carrier_id)
        analysis = analyze_target_plan(
            provider_label=provider_label,
            target_plan=target_plan,
            quotation_text=extracted.text,
            brochure_text="",
            wording_text=wording_text,
            focused_table_context="",
        )

        return {
            "filename": filename,
            "pages": extracted.pages,
            "content_hash": extracted.content_hash,
            "plan_name": analysis.get("plan_name") or target_plan,
            "provider": analysis.get("provider") or "Current policy",
            "premium": analysis.get("premium"),
            "deductible_or_excess": analysis.get("deductible_or_excess"),
            "annual_limit": analysis.get("annual_limit"),
            "area_of_cover": analysis.get("area_of_cover"),
            "underwriting": analysis.get("underwriting") or {},
            "benefits": analysis.get("benefits") or {},
            "critical_limitations": analysis.get("critical_limitations") or [],
            "waiting_periods": analysis.get("waiting_periods") or [],
            "source_evidence": analysis.get("source_evidence") or [],
            "confidence": analysis.get("confidence") or "low",
            "supporting_documents": supporting_documents,
            "policy_wording_status": "attached" if wording_text else "not_attached",
        }
    finally:
        if tmp_path:
            try:
                Path(tmp_path).unlink(missing_ok=True)
            except Exception:
                pass


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
