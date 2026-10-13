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
import traceback
from datetime import datetime, timezone
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
reviewing one or more documents a prospective or current client has uploaded
for this policy — up to three, each labelled by purpose in the user turn:
  (1) Table of Benefits / Benefit Schedule — the summary of what IS covered,
      always provided when the client sends anything;
  (2) Full policy wording — the authoritative document; it holds the real
      exclusions, waiting periods, pre-authorisation rules, portability
      clauses and governing law. When provided, you MUST cross-reference it
      against the Table of Benefits: if the wording restricts, qualifies or
      excludes something the Benefits schedule shows as covered, the wording
      wins and your review reflects that;
  (3) Current invoice / premium notice — confirms the real annual premium
      being charged, the payment frequency, any loading, and the currency.
      When provided, use its figures in the `price` section; do not re-read
      prices from the Benefits sheet (prices there are often illustrative).

Some documents may be missing. For any missing document, state what remains
unverifiable in the `unclear_in_document` list, do not guess.

Your job is to produce a plain-English review in Ashlar's voice.

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


DocBundle = dict  # keys: slot ('benefits'|'wording'|'invoice'), blob, mime


def _doc_label(slot: str) -> str:
    return {
        "benefits": "Table of Benefits / Benefit Schedule",
        "wording": "Full policy wording",
        "invoice": "Current invoice / premium notice",
    }.get(slot, slot)


def _attach_doc(user_content: list[dict], slot: str, blob: bytes, mime: str) -> None:
    """Attach one document to the Claude user turn, labelled by purpose."""
    label = _doc_label(slot)
    user_content.append(
        {
            "type": "text",
            "text": f"--- Attachment: {label} ---",
        }
    )
    if mime == "application/pdf":
        user_content.append(
            {
                "type": "document",
                "source": {
                    "type": "base64",
                    "media_type": "application/pdf",
                    "data": base64.standard_b64encode(blob).decode("ascii"),
                },
            }
        )
    elif mime in ("image/png", "image/jpeg"):
        user_content.append(
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": mime,
                    "data": base64.standard_b64encode(blob).decode("ascii"),
                },
            }
        )
    elif mime == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
        text = _docx_to_text(blob)
        user_content.append(
            {
                "type": "text",
                "text": (
                    f"The {label.lower()} was uploaded as a .docx file. Below is "
                    "the extracted text; treat it as that document.\n\n"
                    f"<document>\n{text}\n</document>"
                ),
            }
        )
    else:
        raise PolicyReviewError(f"Unsupported upload type for AI review ({slot}): {mime}")


def _build_prompt(client_profile: str, client_priorities: str, received_slots: list[str]) -> str:
    labels = ", ".join(_doc_label(s) for s in received_slots) if received_slots else "(none)"
    missing = [s for s in ("benefits", "wording", "invoice") if s not in received_slots]
    missing_note = (
        "\n\nDocuments NOT provided: "
        + ", ".join(_doc_label(s) for s in missing)
        + ". For anything that would normally live in a missing document, say so "
          "plainly in `unclear_in_document`."
        if missing
        else ""
    )
    return (
        f"The client provided this profile:\n{client_profile or '(not provided)'}\n\n"
        f"They told us to focus on:\n{client_priorities or '(not provided)'}\n\n"
        f"Documents attached in this turn: {labels}.{missing_note}\n\n"
        "Read every attached document and return the JSON object as instructed."
    )


# ---------- Claude call --------------------------------------------------


def _call_claude(docs: list[DocBundle], client_profile: str, client_priorities: str) -> dict:
    if not docs:
        raise PolicyReviewError("No documents were provided for review.")
    client = _anthropic()
    user_content: list[dict] = []

    for d in docs:
        _attach_doc(user_content, d["slot"], d["blob"], d["mime"])

    received_slots = [d["slot"] for d in docs]
    user_content.append({"type": "text", "text": _build_prompt(client_profile, client_priorities, received_slots)})

    message = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=16000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_content}],
    )

    # Collect all text segments from the response
    raw = "".join(
        block.text for block in message.content if getattr(block, "type", None) == "text"
    ).strip()

    # The top-level object must carry every top-level key the schema defines,
    # otherwise we picked a nested fragment such as the "identity" object.
    REQUIRED_TOP_KEYS = (
        "identity", "scope", "benefits", "rules",
        "exclusions_to_flag", "price", "ashlar_summary",
        "client_fit", "unclear_in_document", "attributions",
    )
    parsed = parse_best_json_object(raw, required_keys=REQUIRED_TOP_KEYS)
    if not parsed:
        raise PolicyReviewError("Claude did not return a valid JSON policy review.")
    # Guard against nested-fragment selection: the top-level MUST have identity + benefits.
    if not (isinstance(parsed.get("identity"), dict) and isinstance(parsed.get("benefits"), list)):
        raise PolicyReviewError(
            f"Claude JSON missing identity/benefits top-level keys. Got keys: {list(parsed.keys())[:12]}"
        )
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

    docs_received = review.get("_documents_received") or {}
    docs_rows: list[str] = []
    doc_labels = (
        ("benefits", "Table of Benefits"),
        ("wording", "Full policy wording"),
        ("invoice", "Current invoice"),
    )
    for slot, label in doc_labels:
        got = bool(docs_received.get(slot))
        mark = "✓" if got else "—"
        colour = "#4A6E6B" if got else "#98a2c8"
        state = "Read" if got else "Not provided"
        docs_rows.append(
            f"<li style='font-family:Georgia,serif;margin:0;padding:2px 0;'>"
            f"<span style='color:{colour};font-weight:600;'>{mark}</span> "
            f"{html.escape(label)} — <span style='color:#4A6E6B;font-family:monospace;font-size:12px;'>{state}</span></li>"
        )
    docs_block = (
        "<div style='margin-top:20px;padding:14px 18px;border:1px solid #D7CDBC;background:#F9F6EE;'>"
        "<p style='margin:0 0 6px;font-family:monospace;font-size:11px;letter-spacing:0.1em;text-transform:uppercase;color:#4A6E6B;'>Documents HAL read</p>"
        "<ul style='list-style:none;margin:0;padding:0;'>" + "".join(docs_rows) + "</ul>"
        "</div>"
    )

    second_opinion_block = ""
    if second_opinion:
        wording_note = ""
        if not docs_received.get("wording"):
            wording_note = (
                "<p style='margin:8px 0 0;font-family:Georgia,serif;color:#70181C;'>"
                "You did not attach your full policy wording. The broker review needs it to confirm exclusions, waiting periods and pre-authorisation rules. "
                "Please reply to this email with the wording attached, or write to " + html.escape(CHRIS_INBOX) + "."
                "</p>"
            )
        second_opinion_block = (
            "<div style='margin-top:28px;padding:16px 20px;border:1px solid #D7CDBC;background:#F9F6EE;'>"
            "<p style='margin:0 0 8px;font-family:Georgia,serif;'><strong>Second opinion requested.</strong></p>"
            "<p style='margin:0;font-family:Georgia,serif;'>A licensed Ashlar broker will verify HAL's analysis against your profile and reply within one business day.</p>"
            f"{wording_note}"
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

  {docs_block}

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

    docs_received = review.get("_documents_received") or {}
    paths = {
        "benefits": case.get("uploaded_file_path"),
        "wording": case.get("uploaded_wording_path"),
        "invoice": case.get("uploaded_invoice_path"),
    }
    doc_rows: list[str] = []
    for slot, label in (("benefits", "Table of Benefits"), ("wording", "Full policy wording"), ("invoice", "Current invoice")):
        got = bool(docs_received.get(slot))
        path = paths.get(slot)
        mark = "✓" if got else "✗"
        colour = "#4A6E6B" if got else "#70181C"
        detail = f"<code>{html.escape(path)}</code>" if path else "<em>not provided</em>"
        doc_rows.append(
            f"<tr>"
            f"<td style='padding:4px 10px;border-bottom:1px solid #D7CDBC;color:{colour};font-weight:600;'>{mark} {html.escape(label)}</td>"
            f"<td style='padding:4px 10px;border-bottom:1px solid #D7CDBC;font-family:monospace;font-size:11px;'>{detail}</td>"
            f"</tr>"
        )
    docs_table = (
        "<table style='border-collapse:collapse;width:100%;margin:12px 0 16px;'>"
        + "".join(doc_rows)
        + "</table>"
    )

    wording_warning = ""
    if not docs_received.get("wording"):
        wording_warning = (
            "<p style='margin:8px 0 16px;padding:10px 14px;border:1px solid #70181C;background:#faecec;font-family:Georgia,serif;color:#70181C;'>"
            "<strong>Policy wording not attached.</strong> Second opinion was requested without the wording — "
            "ask the client to send it before writing the broker review. HAL could not confirm exclusions, "
            "waiting periods or pre-authorisation rules from the Table of Benefits alone."
            "</p>"
        )

    return f"""
<div style="font-family:Georgia,serif;color:#1B2432;max-width:720px;margin:0 auto;padding:20px;">
  <p style="font-family:monospace;color:#70181C;letter-spacing:0.14em;text-transform:uppercase;font-size:12px;margin:0 0 8px;">Second-opinion requested · {html.escape(reference)}</p>
  <h1 style="font-family:Georgia,serif;font-size:22px;margin:0 0 12px;">{html.escape(case.get('client_name') or '')} — {html.escape(case.get('client_email') or '')}</h1>
  <p style="font-family:Georgia,serif;margin:0 0 4px;"><strong>Policy:</strong> {html.escape(plan_label)}</p>
  <p style="font-family:Georgia,serif;margin:0 0 16px;"><strong>HAL verdict:</strong> {html.escape((fit.get('fits') or 'unclear').title())} — {html.escape(fit.get('reason') or '')}</p>

  {wording_warning}

  <p style="font-family:Georgia,serif;margin:12px 0 4px;"><strong>Documents (bucket: <code>{html.escape(POLICY_UPLOAD_BUCKET)}</code>)</strong></p>
  {docs_table}

  <p style="font-family:Georgia,serif;margin:12px 0 4px;"><strong>Client profile</strong></p>
  <pre style="white-space:pre-wrap;font-family:monospace;background:#F9F6EE;padding:12px;border:1px solid #D7CDBC;margin:0 0 16px;">{client_profile}</pre>

  <p style="font-family:Georgia,serif;margin:12px 0 4px;"><strong>Focus the client asked for</strong></p>
  <pre style="white-space:pre-wrap;font-family:monospace;background:#F9F6EE;padding:12px;border:1px solid #D7CDBC;margin:0 0 16px;">{client_priorities}</pre>

  <p style="font-family:Georgia,serif;margin:12px 0 4px;"><strong>Full HAL review (JSON)</strong></p>
  <pre style="white-space:pre-wrap;font-family:monospace;font-size:11px;background:#F9F6EE;padding:12px;border:1px solid #D7CDBC;margin:0 0 16px;max-height:400px;overflow:auto;">{html.escape(json.dumps(review, indent=2, ensure_ascii=False))}</pre>

  <p style="font-family:Georgia,serif;color:#4A6E6B;font-size:12px;">
    The client ticked "second opinion". Reply within one business day.
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

    # Collect every uploaded document the intake stored for this case.
    doc_slots: list[DocBundle] = []
    for slot, path_key, mime_key in (
        ("benefits", "uploaded_file_path", "uploaded_file_mime"),
        ("wording", "uploaded_wording_path", "uploaded_wording_mime"),
        ("invoice", "uploaded_invoice_path", "uploaded_invoice_mime"),
    ):
        p = case.get(path_key)
        m = (case.get(mime_key) or "").lower()
        if not (p and m):
            continue
        try:
            blob = _download_upload(p)
        except PolicyReviewError as exc:
            print(f"[policy_review] {cid}: download of {slot} ({p}) failed: {exc}", flush=True)
            continue
        doc_slots.append({"slot": slot, "blob": blob, "mime": m})

    if not doc_slots:
        raise PolicyReviewError(f"Case {cid} has no readable uploaded documents.")

    update_job(jid, progress_stage=f"HAL is reading {len(doc_slots)} document(s)")
    review = _call_claude(
        docs=doc_slots,
        client_profile=case.get("client_profile") or "",
        client_priorities=case.get("client_priorities") or "",
    )
    # Record which documents HAL actually read, for the email + broker.
    review["_documents_received"] = {d["slot"]: True for d in doc_slots}
    for s in ("benefits", "wording", "invoice"):
        review["_documents_received"].setdefault(s, False)

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
    email_errors: list[str] = []
    try:
        _send_email(
            to=client_email,
            subject=f"Your policy review from HAL · {reference}",
            html_body=_client_email_html(review, reference, second_opinion),
        )
        _sb().table("analysis_cases").update({
            "summary_sent_at": datetime.now(timezone.utc).isoformat(),
        }).eq("id", cid).execute()
        print(f"[policy_review] {reference}: client summary emailed to {client_email}", flush=True)
    except Exception as exc:
        # Don't fail the whole job if email fails — the review is saved in Supabase.
        print(f"[policy_review] {reference}: CLIENT EMAIL FAILED: {exc}", flush=True)
        traceback.print_exc()
        email_errors.append(f"client email: {exc}")

    if second_opinion:
        update_job(jid, progress_stage="Notifying broker for second opinion")
        try:
            _send_email(
                to=CHRIS_INBOX,
                subject=f"Second-opinion requested — {case.get('client_name') or 'client'} ({reference})",
                html_body=_broker_email_html(case, review, reference),
            )
            _sb().table("analysis_cases").update({
                "broker_notified_at": datetime.now(timezone.utc).isoformat(),
            }).eq("id", cid).execute()
            print(f"[policy_review] {reference}: broker notified at {CHRIS_INBOX}", flush=True)
        except Exception as exc:
            print(f"[policy_review] {reference}: BROKER EMAIL FAILED: {exc}", flush=True)
            traceback.print_exc()
            email_errors.append(f"broker email: {exc}")

    final = {
        "status": "completed",
        "progress_stage": "Policy review complete" if not email_errors else "Policy review complete — email failed",
        "result_json": {
            "case_id": cid,
            "reference": reference,
            "fit": (review.get("client_fit") or {}).get("fits") or "unclear",
            "second_opinion_requested": second_opinion,
            "email_errors": email_errors,
        },
    }
    # Preserve email failures where they survive the completion update.
    if email_errors:
        final["error_message"] = " | ".join(email_errors)[:4000]
    update_job(jid, **final)
