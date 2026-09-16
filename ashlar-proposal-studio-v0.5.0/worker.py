"""Ashlar background worker.

The worker polls a Supabase queue and performs long-running LLM work outside the
Streamlit request lifecycle. One worker is enough for the initial Railway setup.
"""
from __future__ import annotations

import os
import socket
import time
import traceback

from core.case_archive import load_case, save_case_snapshot
from core.chat import ask_case_agent
from core.client_analysis import generate_client_analysis
from core.jobs import claim_next_job, update_job, JobQueueError
from core.report_schema import validate_client_report

POLL_SECONDS = float(os.getenv("ASHLAR_WORKER_POLL_SECONDS", "1.5"))
WORKER_ID = os.getenv("ASHLAR_WORKER_ID", f"{socket.gethostname()}-{os.getpid()}")


def _save_loaded_case(row: dict, *, chat=None, report=None, status=None):
    return save_case_snapshot(
        case_id=row.get("id"),
        case_reference=row.get("case_reference") or "",
        client_name=row.get("client_name") or "",
        client_profile=row.get("client_profile") or "",
        client_priorities=row.get("client_priorities") or "",
        client_sex=row.get("client_sex") or "Not specified",
        client_age=row.get("client_age"),
        report_language=row.get("report_language") or "English",
        results=row.get("results_json") or [],
        case_chat=chat if chat is not None else (row.get("case_chat_json") or []),
        client_analysis=report if report is not None else row.get("client_analysis_json"),
        status=status or row.get("status") or "analyzed",
    )


def process_report(job: dict) -> None:
    jid, cid = job["id"], job["case_id"]
    update_job(jid, progress_stage="Loading saved case")
    row = load_case(cid)
    results = row.get("results_json") or []
    update_job(jid, progress_stage=f"Preparing verified facts for {len(results)} plan(s)")
    update_job(jid, progress_stage="Writing concise decision synthesis and Ashlar Assessment")
    report = generate_client_analysis(
        case_reference=row.get("case_reference") or "",
        client_name=row.get("client_name") or "",
        client_profile=row.get("client_profile") or "",
        client_priorities=row.get("client_priorities") or "",
        client_sex=row.get("client_sex") or "Not specified",
        client_age=row.get("client_age"),
        results=results,
        language=row.get("report_language") or "English",
        strict=True,
    )
    update_job(jid, progress_stage="Validating complete client report")
    validate_client_report(report, results)
    update_job(jid, progress_stage="Saving validated report")
    _save_loaded_case(row, report=report, status="report_ready")
    update_job(jid, status="completed", progress_stage="Report ready", result_json={"case_id": cid})


def process_chat(job: dict) -> None:
    jid, cid = job["id"], job["case_id"]
    question = str((job.get("request_json") or {}).get("question") or "").strip()
    if not question:
        raise ValueError("HAL chat job has no question.")
    update_job(jid, progress_stage="Loading grounded case evidence")
    row = load_case(cid)
    history = row.get("case_chat_json") or []
    update_job(jid, progress_stage="HAL is reviewing the case")
    answer = ask_case_agent(
        question=question,
        case_reference=row.get("case_reference") or "",
        client_profile=row.get("client_profile") or "",
        client_priorities=row.get("client_priorities") or "",
        client_sex=row.get("client_sex") or "Not specified",
        client_age=row.get("client_age"),
        results=row.get("results_json") or [],
        history=history,
    )
    chat = history + [{"role": "user", "content": question}, {"role": "assistant", "content": answer}]
    update_job(jid, progress_stage="Saving HAL conversation")
    _save_loaded_case(row, chat=chat, status="report_ready" if row.get("client_analysis_json") else "analyzed")
    update_job(jid, status="completed", progress_stage="HAL response ready", result_json={"case_id": cid})


def process(job: dict) -> None:
    kind = job.get("job_type")
    if kind == "client_report":
        process_report(job)
    elif kind == "hal_chat":
        process_chat(job)
    else:
        raise ValueError(f"Unsupported job type: {kind}")


def main() -> None:
    print(f"Ashlar worker {WORKER_ID} started")
    while True:
        try:
            job = claim_next_job(WORKER_ID)
            if not job:
                time.sleep(POLL_SECONDS)
                continue
            try:
                process(job)
            except Exception as exc:
                traceback.print_exc()
                update_job(
                    job["id"],
                    status="failed",
                    progress_stage="Job failed",
                    error_message=str(exc)[:4000],
                )
        except JobQueueError as exc:
            print(f"Queue error: {exc}", flush=True)
            time.sleep(max(POLL_SECONDS, 5.0))
        except KeyboardInterrupt:
            break
        except Exception:
            traceback.print_exc()
            time.sleep(max(POLL_SECONDS, 5.0))


if __name__ == "__main__":
    main()
