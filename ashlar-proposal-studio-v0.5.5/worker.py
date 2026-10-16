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
from core.case_runner import analyze_option, disambiguate_plan_names, reanalysis_inputs
from core.chat import ask_case_agent
from core.client_analysis import generate_client_analysis
from core.jobs import claim_next_job, update_job, JobQueueError
from core.policy_review import process_policy_review
from core.report_schema import validate_client_report

POLL_SECONDS = float(os.getenv("ASHLAR_WORKER_POLL_SECONDS", "1.5"))
WORKER_ID = os.getenv("ASHLAR_WORKER_ID", f"{socket.gethostname()}-{os.getpid()}")


_KEEP = object()


def _save_loaded_case(row: dict, *, chat=None, report=_KEEP, status=None, results=None):
    return save_case_snapshot(
        case_id=row.get("id"),
        case_reference=row.get("case_reference") or "",
        client_name=row.get("client_name") or "",
        client_profile=row.get("client_profile") or "",
        client_priorities=row.get("client_priorities") or "",
        client_sex=row.get("client_sex") or "Not specified",
        client_age=row.get("client_age"),
        report_language=row.get("report_language") or "English",
        results=results if results is not None else (row.get("results_json") or []),
        case_chat=chat if chat is not None else (row.get("case_chat_json") or []),
        client_analysis=row.get("client_analysis_json") if report is _KEEP else report,
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
        household_members=row.get("household_members_json") or [],
    )
    update_job(jid, progress_stage="Validating complete client report")
    validate_client_report(report, results)
    update_job(jid, progress_stage="Saving validated report")
    _save_loaded_case(row, report=report, status="report_ready")
    update_job(jid, status="completed", progress_stage="Report ready", result_json={"case_id": cid})


def process_case_analysis(job: dict) -> None:
    """Re-analyse every option of a saved case from its stored quotation text.

    Used after a Provider Library fix: the quotes are not uploaded again.
    request_json may carry {"labels": {"<old label>": "<new label>"}} to correct
    an option label at the same time.
    """
    jid, cid = job["id"], job["case_id"]
    request = job.get("request_json") or {}
    relabel = request.get("labels") or {}
    keep_existing = bool(request.get("keep_existing"))
    update_job(jid, progress_stage="Loading saved case")
    row = load_case(cid)
    saved = list(row.get("results_json") or [])
    # New options from a quote received later (e.g. the insurer's revised
    # quote): {"label", "quotation_text", "target_plan", "library_from"}.
    for opt in request.get("add_options") or []:
        base = next((r for r in saved if r.get("provider") == opt.get("library_from")), {})
        target = str(opt.get("target_plan") or "").strip()
        saved.append({
            "provider": opt.get("label") or "Option",
            "quotation_text": opt.get("quotation_text") or "",
            "library_source": opt.get("library_source") or base.get("library_source"),
            "plan_selection": {"plan_name": target, "method": "broker_override"} if target else {},
        })
    missing = [r.get("provider") for r in saved if not (r.get("quotation_text") or "").strip()]
    if missing:
        raise ValueError(
            "Saved case has no stored quotation text for: " + ", ".join(str(m) for m in missing)
            + ". Re-run the analysis from the case form with the quote uploaded."
        )
    results, notes = [], []
    for idx, old in enumerate(saved, start=1):
        if keep_existing and old.get("analysis"):
            # Already analysed and reviewed: keep it, apart from a label fix.
            results.append({**old, "provider": relabel.get(old.get("provider"), old.get("provider"))})
            continue
        args = reanalysis_inputs(old)
        args["label"] = relabel.get(args["label"], args["label"])
        update_job(jid, progress_stage=f"Analysing option {idx}/{len(saved)}: {args['label']}")
        result, warnings = analyze_option(**args)
        results.append(result)
        notes.extend(warnings)
    disambiguate_plan_names(results)
    update_job(jid, progress_stage="Saving analysed case")
    # A new analysis invalidates the previous client report.
    _save_loaded_case(row, results=results, report=None, status="analyzed")
    update_job(jid, status="completed", progress_stage="Case re-analysed",
               result_json={"case_id": cid, "options": len(results), "warnings": notes[:20]})


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
    elif kind == "case_analysis":
        process_case_analysis(job)
    elif kind == "hal_chat":
        process_chat(job)
    elif kind == "policy_review":
        # Website intake from https://ashlarassurance.com/have-my-policy-reviewed/
        # Reads the uploaded policy, generates HAL summary, emails the client.
        process_policy_review(job)
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
