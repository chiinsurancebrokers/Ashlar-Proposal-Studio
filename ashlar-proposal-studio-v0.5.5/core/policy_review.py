"""Website policy-review handler for the Ashlar background worker.

When a visitor at https://ashlarassurance.com/have-my-policy-reviewed/ uploads
their policy, the Supabase edge function `policy-review-intake` creates:
  - a row in `analysis_cases` with source='website_form' and the uploaded file
    stored in the `client-policy-uploads` bucket;
  - a row in `analysis_jobs` with job_type='policy_review', status='pending'.

The worker (`worker.py`) picks the job up and calls `process_policy_review` here.
This module:
  1. Downloads the uploaded policy document from Supabase Storage.
  2. Sends it to Claude together with the ipmi-plan-reader prompt and schema
     (PDFs and images natively; .docx is text-extracted first).
  3. Writes the structured review to `analysis_cases.client_analysis_json`.
  4. Emails the plain-language summary to the client via Resend.
  5. If `second_opinion_requested` is true, also emails Chris so a licensed
     broker can verify HAL's analysis against the client's profile.

HAL fairness rules (ashlar-voice): the AI summary is always labelled as such,
the policy wording is named as the authoritative source, and nothing promises
cover that depends on the insurer's underwriting.
"""
from __future__ import annotations

import base64
import html
import json
import os
import re
from functools import lru_cache
from io import BytesIO
from typing import Optional

import httpx

from .case_archive import load_case, save_case_snapshot
from .jobs import update_job
from .json_utils import parse_best_json_object


POLICY_UPLOAD_BUCKET = os.getenv(
    "ASHLAR_POLICY_UPLOAD_BUCKET", "client-policy-uploads"
).strip() or "client-policy-uploads"

CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-5-20250929").strip()

CHRIS_INBOX = os.getenv("ASHLAR_BROKER_INBOX", "info@ashlarassurance.com").strip()


class PolicyReviewError(RuntimeError):
    pass


@lru_cache(maxsize=1)
def _sb():
    from supabase import create_client

    url = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    if not (url and key):
        raise PolicyReviewError("Supabase is not configured (SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY).")
    return create_client(url, key)


@lru_cache(maxsize=1)
def _anthropic():
    import anthropic

    key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    if not key:
        raise PolicyReviewError("ANTHROPIC_API_KEY is not configured.")
    return anthropic.Anthropic(api_key=key)


# ---------- download + text extraction -----------------------------------


def _download_upload(storage_path: str) -> bytes:
    try:
        return _sb().storage.from_(POLICY_UPLOAD_BUCKET).download(storage_path)
    except Exception as exc:
        raise PolicyReviewError(f"Could not download uploaded policy: {exc}") from exc


def _docx_to_text(blob: bytes) -> str:
    """Extract plain text from a .docx file using the zipfile+xml path.

    We avoid adding python-docx just for this — a .docx is a zip of XML parts
    and the text we want lives in word/document.xml.
    """
    import xml.etree.ElementTree as ET
    import zipfile

    try:
        with zipfile.ZipFile(BytesIO(blob)) as zf:
            with zf.open("word/document.xml") as f:
                tree = ET.parse(f)
    except Exception as exc:
        raise PolicyReviewError(f"Could not read .docx contents: {exc}") from exc

    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    paragraphs: list[str] = []
    for p in tree.getroot().iter("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}p"):
        runs = [t.text or "" for t in p.iter("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}t")]
        line = "".join(runs).strip()
        if line:
            paragraphs.append(line)
    return "\n".join(paragraphs)[:200_000]  # cap at 200k chars to protect the LLM call


# ---------- prompt -------------------------------------------------------


SYSTEM_PROMPT = """You are HAL, Ashlar Assurance's AI policy reader for international private
medical insurance (IPMI), travel, group, maritime and student plans. You are
reviewing one specific policy document that a prospective or current client has
uploaded. Your job is to produce a plain-English review in Ashlar's voice.

HARD RULES (never break):
- Never invent figures. If a benefit, limit, exclusion or rule is not visible
  in the document, say so plainly ("The wording does not state..." or
  "Not visible in this document — we will confirm with the insurer").
- Never translate an exclusion into a qualified cover statement. If the wording
  says excluded, your summary says not covered.
- Never promise portability or direct billing without naming the policy wording
  and insurer confirmation as the authority.
- The policy wording prevails over any summary you write.
- Mark the review as an AI-generated summary. A licensed Ashlar broker verifies
  it on request.
- Ashlar voice: plain English, short sentences, active voice, the way a
  knowledgeable friend would talk. No scare tactics. No "the best / only /
  revolutionary". No mannered "not X, but Y" framing. No "honestly" or "to tell
  the truth". No peace-of-mind platitudes.

OUTPUT: a single JSON object with these top-level keys, in order:

{
  "identity": {
    "insurer": "...",
    "plan_name": "...",
    "tier": "...",
    "document_code": "...",
    "document_version": "...",
    "effective_dates": "...",
    "coverage_area": "..."
  },
  "scope": {
    "annual_limit": "...",
    "deductible": "...",
    "coinsurance": "...",
    "household_composition": "..."
  },
  "benefits": [
    { "name": "Hospital accommodation and surgeons' fees", "state": "covered|instructional|caution|serious",
      "detail": "..." },
    ...
  ],
  "rules": {
    "pre_authorisation": "...",
    "direct_billing": "...",
    "network": "...",
    "underwriting_method": "...",
    "waiting_periods": "...",
    "age_limits": "..."
  },
  "exclusions_to_flag": ["..."],
  "price": {
    "premium_stated": "...",
    "profile": "...",
    "payment_frequency": "..."
  },
  "ashlar_summary": {
    "what_this_plan_is_good_at": "one paragraph in Ashlar voice",
    "what_it_is_not": "one paragraph in Ashlar voice",
    "things_to_know_before_using_it": [
      "which hospitals",
      "who to call for pre-auth",
      "what needs a receipt",
      "what a waiting period applies to"
    ],
    "fit_statement": "one line on whose expectations this plan fits, whose it does not"
  },
  "client_fit": {
    "fits": "yes|partial|no|unclear",
    "reason": "one or two sentences, grounded in what the client told us about their situation"
  },
  "unclear_in_document": ["..."],
  "attributions": [
    { "claim": "...", "page_or_section": "..." }
  ]
}

Benefit `state` meanings (match Ashlar's insurance-marks skill):
- covered: paid under the plan as written
- instructional: action is needed before the benefit applies (pre-auth, claim form)
- caution: benefit exists but with a condition that must be noticed (sub-limit,
  waiting period, age-rated)
- serious: not covered, declined, or outside the plan

Only emit the JSON object, nothing before or after.
"""


def _build_prompt(client_profile: str, client_priorities: str) -> str:
    return (
        "The client provided this profile:\n"
        f"{client_profile or '(not provided)'}\n\n"
        "They told us to focus on:\n"
        f"{client_priorities or '(not provided)'}\n\n"
        "Read the attached policy document and return the JSON object as instructed."
    )


# ---------- Claude call --------------------------------------------------


def _call_claude(file_blob: bytes, mime: str, client_profile: str, client_priorities: str) -> dict:
    client = _anthropic()
    user_content: list[dict] = []

    text_prompt = _build_prompt(client_profile, client_priorities)

    if mime == "application/pdf":
        b64 = base64.standard_b64encode(file_blob).decode("ascii")
        user_content.append(
            {
                "type": "document",
                "source": {"type": "base64", "media_type": "application/pdf", "data": b64},
            }
        )
    elif mime in ("image/png", "image/jpeg"):
        b64 = base64.standard_b64encode(file_blob).decode("ascii")
        user_content.append(
            {
                "type": "image",
                "source": {"type": "base64", "media_type": mime, "data": b64},
            }
        )
    elif mime == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
        text = _docx_to_text(file_blob)
        user_content.append(
            {
                "type": "text",
                "text": (
                    "The policy was uploaded as a .docx file. Below is the "
                    "extracted text; treat it as the policy document.\n\n"
                    f"<policy_document>\n{text}\n</policy_document>"
                ),
            }
        )
    else:
        raise PolicyReviewError(f"Unsupported upload type for AI review: {mime}")

    user_content.append({"type": "text", "text": text_prompt})

    message = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=4096,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_content}],
    )

    # Collect all text segments from the response
    raw = "".join(
        block.text for block in message.content if getattr(block, "type", None) == "text"
    ).strip()

    parsed = parse_best_json_object(raw)
    if not parsed:
        raise PolicyReviewError("Claude did not return a valid JSON policy review.")
    return parsed


# ---------- email --------------------------------------------------------


def _email_configured() -> bool:
    return bool(os.getenv("RESEND_API_KEY", "").strip() and os.getenv("ASHLAR_EMAIL_FROM", "").strip())


def _send_email(*, to: str, subject: str, html_body: str) -> dict:
    if not _email_configured():
        raise PolicyReviewError(
            "Email delivery not configured — set RESEND_API_KEY and ASHLAR_EMAIL_FROM."
        )
    payload = {
        "from": os.getenv("ASHLAR_EMAIL_FROM", "").strip(),
        "to": [to],
        "subject": subject,
        "html": html_body,
    }
    reply_to = os.getenv("ASHLAR_EMAIL_REPLY_TO", "").strip()
    if reply_to:
        payload["reply_to"] = reply_to
    response = httpx.post(
        "https://api.resend.com/emails",
        headers={
            "Authorization": f"Bearer {os.getenv('RESEND_API_KEY', '').strip()}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=30.0,
    )
    if response.status_code >= 300:
        raise PolicyReviewError(f"Resend send failed ({response.status_code}): {response.text[:400]}")
    try:
        return response.json()
    except Exception:
        return {"ok": True}


def _format_benefits_html(benefits: list[dict]) -> str:
    if not benefits:
        return ""
    state_mark = {
        "covered": ("#4A6E6B", "In network · covered"),
        "instructional": ("#1B2432", "Action needed"),
        "caution": ("#B88A2B", "Condition applies"),
        "serious": ("#70181C", "Not covered"),
    }
    rows = []
    for b in benefits:
        state = (b.get("state") or "").lower()
        color, label = state_mark.get(state, ("#1B2432", "Noted"))
        rows.append(
            f"<tr>"
            f"<td style='padding:8px 12px;border-bottom:1px solid #D7CDBC;vertical-align:top;'><strong>{html.escape(b.get('name') or '')}</strong></td>"
            f"<td style='padding:8px 12px;border-bottom:1px solid #D7CDBC;vertical-align:top;color:{color};font-family:monospace;font-size:12px;letter-spacing:.08em;text-transform:uppercase;'>{html.escape(label)}</td>"
            f"<td style='padding:8px 12px;border-bottom:1px solid #D7CDBC;vertical-align:top;'>{html.escape(b.get('detail') or '')}</td>"
            f"</tr>"
        )
    return (
        "<table style='border-collapse:collapse;width:100%;margin-top:16px;font-family:Georgia,serif;'>"
        + "".join(rows)
        + "</table>"
    )


def _client_email_html(review: dict, reference: str, second_opinion: bool) -> str:
    identity = review.get("identity") or {}
    scope = review.get("scope") or {}
    summary = review.get("ashlar_summary") or {}
    rules = review.get("rules") or {}
    fit = review.get("client_fit") or {}
    exclusions = review.get("exclusions_to_flag") or []
    unclear = review.get("unclear_in_document") or []

    plan_label = " · ".join(
        [x for x in [identity.get("insurer"), identity.get("plan_name"), identity.get("tier")] if x]
    ) or "Your policy"

    things = summary.get("things_to_know_before_using_it") or []
    things_html = "".join(f"<li>{html.escape(str(t))}</li>" for t in things)

    exclusions_html = "".join(f"<li>{html.escape(str(e))}</li>" for e in exclusions)
    unclear_html = "".join(f"<li>{html.escape(str(u))}</li>" for u in unclear)

    second_opinion_block = ""
    if second_opinion:
        second_opinion_block = (
            "<div style='margin-top:28px;padding:16px 20px;border:1px solid #D7CDBC;background:#F9F6EE;'>"
            "<p style='margin:0 0 8px;font-family:Georgia,serif;'><strong>Second opinion requested.</strong></p>"
            "<p style='margin:0;font-family:Georgia,serif;'>A licensed Ashlar broker will verify HAL's analysis against your profile and reply within one business day.</p>"
            "</div>"
        )

    return f"""
<div style="font-family:Georgia,serif;color:#1B2432;max-width:640px;margin:0 auto;padding:24px;">
  <p style="font-family:monospace;color:#4A6E6B;letter-spacing:0.14em;text-transform:uppercase;font-size:12px;margin:0 0 8px;">Ashlar Assurance · policy review · {html.escape(reference)}</p>
  <h1 style="font-family:Georgia,serif;font-size:28px;line-height:1.2;margin:0 0 16px;color:#1B2432;">We read your policy.</h1>
  <p style="font-family:Georgia,serif;margin:0 0 8px;"><strong>{html.escape(plan_label)}</strong></p>
  <p style="font-family:Georgia,serif;margin:0 0 24px;color:#4A6E6B;">Coverage area: {html.escape(identity.get('coverage_area') or 'Not stated in document')} · Annual limit: {html.escape(scope.get('annual_limit') or 'Not stated')} · Deductible: {html.escape(scope.get('deductible') or 'Not stated')}</p>

  <h2 style="font-family:Georgia,serif;font-size:18px;margin:24px 0 8px;">What this plan is good at</h2>
  <p style="font-family:Georgia,serif;margin:0;">{html.escape(summary.get('what_this_plan_is_good_at') or '')}</p>

  <h2 style="font-family:Georgia,serif;font-size:18px;margin:24px 0 8px;">What it isn't</h2>
  <p style="font-family:Georgia,serif;margin:0;">{html.escape(summary.get('what_it_is_not') or '')}</p>

  <h2 style="font-family:Georgia,serif;font-size:18px;margin:24px 0 8px;">Three or four things to know before using it</h2>
  <ul style="font-family:Georgia,serif;margin:0 0 16px 20px;padding:0;">{things_html}</ul>

  <h2 style="font-family:Georgia,serif;font-size:18px;margin:24px 0 8px;">The benefits, state by state</h2>
  {_format_benefits_html(review.get('benefits') or [])}

  <h2 style="font-family:Georgia,serif;font-size:18px;margin:24px 0 8px;">Rules you should notice</h2>
  <p style="font-family:Georgia,serif;margin:0 0 4px;"><strong>Pre-authorisation:</strong> {html.escape(rules.get('pre_authorisation') or 'Not stated')}</p>
  <p style="font-family:Georgia,serif;margin:0 0 4px;"><strong>Direct billing:</strong> {html.escape(rules.get('direct_billing') or 'Not stated')}</p>
  <p style="font-family:Georgia,serif;margin:0 0 4px;"><strong>Network:</strong> {html.escape(rules.get('network') or 'Not stated')}</p>
  <p style="font-family:Georgia,serif;margin:0 0 4px;"><strong>Waiting periods:</strong> {html.escape(rules.get('waiting_periods') or 'Not stated')}</p>

  { ("<h2 style='font-family:Georgia,serif;font-size:18px;margin:24px 0 8px;'>Exclusions worth flagging</h2><ul style='font-family:Georgia,serif;margin:0 0 16px 20px;padding:0;'>" + exclusions_html + "</ul>") if exclusions_html else "" }

  { ("<h2 style='font-family:Georgia,serif;font-size:18px;margin:24px 0 8px;'>Not clear in this document</h2><ul style='font-family:Georgia,serif;margin:0 0 16px 20px;padding:0;'>" + unclear_html + "</ul>") if unclear_html else "" }

  <h2 style="font-family:Georgia,serif;font-size:18px;margin:24px 0 8px;">Does this plan fit you?</h2>
  <p style="font-family:Georgia,serif;margin:0;"><strong>{html.escape((fit.get('fits') or 'unclear').title())}.</strong> {html.escape(fit.get('reason') or '')}</p>

  {second_opinion_block}

  <p style="font-family:monospace;color:#70181C;font-size:12px;margin-top:28px;padding-top:16px;border-top:1px solid #D7CDBC;">
    This is an AI-generated summary written by HAL. The policy wording prevails over any summary.
    Benefit summaries are simplified from the insurer's Table of Benefits; the policy wording is the authority.
    Not an offer of cover. Final eligibility, terms and premium are confirmed by the insurer after your application and underwriting.
  </p>

  <p style="font-family:Georgia,serif;color:#4A6E6B;font-size:12px;margin-top:16px;">
    Reference {html.escape(reference)} · uploaded documents are kept for 90 days from submission, then deleted.
    Reply to this email or write to {html.escape(CHRIS_INBOX)} to request earlier deletion.
  </p>
</div>
""".strip()


def _broker_email_html(case: dict, review: dict, reference: str) -> str:
    identity = review.get("identity") or {}
    plan_label = " · ".join(
        [x for x in [identity.get("insurer"), identity.get("plan_name"), identity.get("tier")] if x]
    ) or "(unknown plan)"
    fit = review.get("client_fit") or {}
    client_profile = html.escape(case.get("client_profile") or "")
    client_priorities = html.escape(case.get("client_priorities") or "")
    return f"""
<div style="font-family:Georgia,serif;color:#1B2432;max-width:720px;margin:0 auto;padding:20px;">
  <p style="font-family:monospace;color:#70181C;letter-spacing:0.14em;text-transform:uppercase;font-size:12px;margin:0 0 8px;">Second-opinion requested · {html.escape(reference)}</p>
  <h1 style="font-family:Georgia,serif;font-size:22px;margin:0 0 12px;">{html.escape(case.get('client_name') or '')} — {html.escape(case.get('client_email') or '')}</h1>
  <p style="font-family:Georgia,serif;margin:0 0 4px;"><strong>Policy:</strong> {html.escape(plan_label)}</p>
  <p style="font-family:Georgia,serif;margin:0 0 16px;"><strong>HAL verdict:</strong> {html.escape((fit.get('fits') or 'unclear').title())} — {html.escape(fit.get('reason') or '')}</p>

  <p style="font-family:Georgia,serif;margin:12px 0 4px;"><strong>Client profile</strong></p>
  <pre style="white-space:pre-wrap;font-family:monospace;background:#F9F6EE;padding:12px;border:1px solid #D7CDBC;margin:0 0 16px;">{client_profile}</pre>

  <p style="font-family:Georgia,serif;margin:12px 0 4px;"><strong>Focus the client asked for</strong></p>
  <pre style="white-space:pre-wrap;font-family:monospace;background:#F9F6EE;padding:12px;border:1px solid #D7CDBC;margin:0 0 16px;">{client_priorities}</pre>

  <p style="font-family:Georgia,serif;margin:12px 0 4px;"><strong>Full HAL review (JSON)</strong></p>
  <pre style="white-space:pre-wrap;font-family:monospace;font-size:11px;background:#F9F6EE;padding:12px;border:1px solid #D7CDBC;margin:0 0 16px;max-height:400px;overflow:auto;">{html.escape(json.dumps(review, indent=2, ensure_ascii=False))}</pre>

  <p style="font-family:Georgia,serif;color:#4A6E6B;font-size:12px;">
    The client ticked "second opinion". Reply within one business day. The uploaded policy document is in the Supabase bucket <code>{html.escape(POLICY_UPLOAD_BUCKET)}</code> under <code>{html.escape(case.get('uploaded_file_path') or '')}</code>.
  </p>
</div>
""".strip()


# ---------- main entrypoint ----------------------------------------------


def process_policy_review(job: dict) -> None:
    jid = job["id"]
    cid = job["case_id"]
    update_job(jid, progress_stage="Loading case")
    case = load_case(cid)
    if not case:
        raise PolicyReviewError(f"Case {cid} not found.")

    source = case.get("source") or "manual"
    if source != "website_form":
        raise PolicyReviewError(f"Case {cid} source is {source!r}; policy_review only handles website_form.")

    client_email = (case.get("client_email") or "").strip().lower()
    if not client_email:
        raise PolicyReviewError(f"Case {cid} has no client_email.")

    uploaded_path = case.get("uploaded_file_path")
    uploaded_mime = (case.get("uploaded_file_mime") or "").lower()
    if not uploaded_path or not uploaded_mime:
        raise PolicyReviewError(f"Case {cid} has no uploaded_file_path/mime.")

    update_job(jid, progress_stage="Downloading uploaded policy")
    blob = _download_upload(uploaded_path)

    update_job(jid, progress_stage="HAL is reading the policy")
    review = _call_claude(
        file_blob=blob,
        mime=uploaded_mime,
        client_profile=case.get("client_profile") or "",
        client_priorities=case.get("client_priorities") or "",
    )

    update_job(jid, progress_stage="Saving review")
    save_case_snapshot(
        case_id=cid,
        case_reference=case.get("case_reference") or cid,
        client_name=case.get("client_name") or "",
        client_profile=case.get("client_profile") or "",
        client_priorities=case.get("client_priorities") or "",
        client_sex=case.get("client_sex") or "Not specified",
        client_age=case.get("client_age"),
        report_language=case.get("report_language") or "English",
        results=case.get("results_json") or [],
        case_chat=case.get("case_chat_json") or [],
        client_analysis=review,
        status="report_ready",
    )

    reference = case.get("case_reference") or cid
    second_opinion = bool(case.get("second_opinion_requested"))

    update_job(jid, progress_stage="Emailing summary to the client")
    try:
        _send_email(
            to=client_email,
            subject=f"Your policy review from HAL · {reference}",
            html_body=_client_email_html(review, reference, second_opinion),
        )
        _sb().table("analysis_cases").update({"summary_sent_at": "now()"}).eq("id", cid).execute()
    except Exception as exc:
        # Don't fail the whole job if email fails — the review is saved in Supabase.
        update_job(jid, progress_stage=f"Client email failed: {exc}")

    if second_opinion:
        update_job(jid, progress_stage="Notifying broker for second opinion")
        try:
            _send_email(
                to=CHRIS_INBOX,
                subject=f"Second-opinion requested — {case.get('client_name') or 'client'} ({reference})",
                html_body=_broker_email_html(case, review, reference),
            )
            _sb().table("analysis_cases").update({"broker_notified_at": "now()"}).eq("id", cid).execute()
        except Exception as exc:
            update_job(jid, progress_stage=f"Broker notification failed: {exc}")

    update_job(
        jid,
        status="completed",
        progress_stage="Policy review complete",
        result_json={
            "case_id": cid,
            "reference": reference,
            "fit": (review.get("client_fit") or {}).get("fits") or "unclear",
            "second_opinion_requested": second_opinion,
        },
    )
