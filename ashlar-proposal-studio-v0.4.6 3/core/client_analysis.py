"""Client-facing analysis generation for Ashlar Proposal Studio.

The module separates facts from narrative:
- comparison rows are built deterministically from structured plan extractions;
- the LLM writes client-facing synthesis only from that grounded payload;
- optional benefits are never promoted to included benefits unless the quote analysis says so.
"""
from __future__ import annotations

import json
import os
from typing import Any


from .json_utils import parse_first_json_object


BENEFIT_ORDER = [
    ("inpatient", "In-patient treatment"),
    ("outpatient", "Out-patient treatment"),
    ("cancer", "Cancer / oncology"),
    ("chronic_conditions", "Chronic conditions"),
    ("mental_health", "Mental health"),
    ("maternity", "Maternity"),
    ("dental", "Dental"),
    ("optical", "Optical"),
    ("preventive", "Preventive / wellness"),
    ("evacuation_repatriation", "Evacuation / repatriation"),
]


def plan_display_name(result: dict) -> str:
    a = result.get("analysis") or {}
    provider = a.get("provider") or result.get("provider") or "Provider"
    plan = a.get("plan_name") or result.get("target_plan") or "Plan"
    return f"{provider} - {plan}"


def premium_display(analysis: dict) -> str:
    p = analysis.get("premium") or {}
    amount = p.get("amount")
    if amount in (None, "", "Not specified"):
        return "Not specified"
    currency = p.get("currency") or ""
    frequency = p.get("frequency") or ""
    pieces = [str(currency).strip(), str(amount).strip(), str(frequency).strip()]
    return " ".join(x for x in pieces if x)


def _safe_text(value: Any) -> str:
    if value is None:
        return "Not specified"
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    text = str(value).strip()
    return text or "Not specified"


def build_comparison_matrix(results: list[dict]) -> list[dict]:
    """Build broker/client comparison rows without LLM interpretation."""
    plan_names = [plan_display_name(r) for r in results]
    rows: list[dict] = []

    def add_row(topic: str, getter, category: str = "Core") -> None:
        rows.append({
            "category": category,
            "topic": topic,
            "values": {
                name: _safe_text(getter((r.get("analysis") or {})))
                for name, r in zip(plan_names, results)
            },
        })

    add_row("Premium", premium_display, "Financial")
    add_row("Annual policy limit", lambda a: a.get("annual_limit"), "Financial")
    add_row("Deductible / excess", lambda a: a.get("deductible_or_excess"), "Financial")
    add_row("Area of cover", lambda a: a.get("area_of_cover"), "Core")
    add_row("Underwriting basis", lambda a: (a.get("underwriting") or {}).get("basis"), "Underwriting")
    add_row(
        "Pre-existing conditions",
        lambda a: (a.get("underwriting") or {}).get("pre_existing_conditions"),
        "Underwriting",
    )
    for key, label in BENEFIT_ORDER:
        add_row(label, lambda a, k=key: (a.get("benefits") or {}).get(k), "Benefits")
    return rows


def _source_digest(result: dict) -> list[dict]:
    a = result.get("analysis") or {}
    evidence = []
    for item in (a.get("source_evidence") or [])[:30]:
        if not isinstance(item, dict):
            continue
        evidence.append({
            "field": item.get("field"),
            "value": item.get("value"),
            "document": item.get("document"),
            "page": item.get("page"),
            "evidence": item.get("evidence"),
        })
    # deterministic table rows are especially useful for multi-tier brochures
    for row in (result.get("focused_rows") or [])[:45]:
        evidence.append({
            "field": row.get("benefit"),
            "value": row.get("value"),
            "document": row.get("source_file"),
            "page": row.get("page"),
            "evidence": f"Target-plan table row ({row.get('evidence_type') or 'table'})",
        })
    return evidence


def build_grounded_case_payload(
    *,
    case_reference: str,
    client_name: str,
    client_profile: str,
    client_priorities: str,
    results: list[dict],
) -> dict:
    plans = []
    for result in results:
        a = result.get("analysis") or {}
        plans.append({
            "display_name": plan_display_name(result),
            "provider": a.get("provider") or result.get("provider"),
            "plan_name": a.get("plan_name") or result.get("target_plan"),
            "premium": a.get("premium"),
            "deductible_or_excess": a.get("deductible_or_excess"),
            "annual_limit": a.get("annual_limit"),
            "area_of_cover": a.get("area_of_cover"),
            "underwriting": a.get("underwriting"),
            "benefits": a.get("benefits"),
            "waiting_periods": a.get("waiting_periods"),
            "optional_benefits": a.get("optional_benefits"),
            "critical_limitations": a.get("critical_limitations"),
            "confidence": a.get("confidence"),
            "source_evidence": _source_digest(result),
        })
    return {
        "case_reference": case_reference or "Unnamed case",
        "client_name": client_name or case_reference or "Client",
        "client_profile": client_profile or "Not supplied",
        "client_priorities": client_priorities or "Not supplied",
        "plans": plans,
        "comparison_matrix": build_comparison_matrix(results),
    }


CLIENT_ANALYSIS_PROMPT = """You are the senior advisory-writing engine inside Ashlar Proposal Studio.
You are preparing a CLIENT-FACING comparative health-insurance analysis on behalf of an insurance broker.

Use ONLY the supplied structured case evidence. Do not add general product knowledge or facts that are not in the payload.

Core rules:
- This is an advisory comparison, not insurer underwriting or a guarantee of cover.
- Applicant-specific quote facts take priority over generic product material.
- "Optional" or "available" must NEVER be described as included unless the case evidence confirms selection.
- If evidence is incomplete or ambiguous, say so clearly and include it under important_considerations.
- Do not rank plans using an arbitrary numeric AI score.
- The recommendation must be reasoned from the CLIENT'S stated priorities and the actual material differences.
- A higher headline annual limit is not automatically "better" if another feature matters more for this client.
- Avoid marketing superlatives such as "best policy" or "comprehensive" unless the evidence itself supports the wording.
- When useful, cite sources in plain text using document/page from the supplied evidence, e.g. "[IMG brochure, p.6]".
- Keep the tone professional, independent, concise and suitable to send directly to a private client.
- Do not mention Claude, AI, LLM, model, prompt, extraction engine, or internal broker tooling.

Return ONLY one valid JSON object with this schema:
{
  "report_title": "",
  "executive_summary": "",
  "client_needs_summary": "",
  "plans": [
    {
      "provider": "",
      "plan_name": "",
      "positioning": "one sentence describing where this plan sits in this comparison",
      "summary": "2-4 client-facing sentences",
      "strengths": ["", ""],
      "considerations": ["", ""],
      "best_suited_when": "",
      "source_notes": [""]
    }
  ],
  "key_differences": [
    {
      "title": "",
      "analysis": "",
      "client_impact": ""
    }
  ],
  "ashlar_assessment": {
    "recommended_provider": "",
    "recommended_plan": "",
    "headline": "",
    "reasoning": ["", "", ""],
    "alternative_provider": "",
    "alternative_plan": "",
    "alternative_reason": "",
    "when_the_alternative_may_be_better": ""
  },
  "important_considerations": [""],
  "next_steps": [""],
  "disclaimer": ""
}

If the evidence is insufficient for a responsible single recommendation, leave recommended_provider/recommended_plan empty and explain in headline/reasoning what must be confirmed first.
"""


def _fallback_analysis(payload: dict, language: str) -> dict:
    greek = language.lower().startswith("el") or language.lower().startswith("gr") or "greek" in language.lower()
    plans = []
    for p in payload.get("plans", []):
        plans.append({
            "provider": p.get("provider") or "",
            "plan_name": p.get("plan_name") or "",
            "positioning": "",
            "summary": "",
            "strengths": [],
            "considerations": ["AI narrative unavailable; review the comparison facts directly." if not greek else "Η αφηγηματική ανάλυση δεν είναι διαθέσιμη· ελέγξτε απευθείας τα συγκριτικά στοιχεία."],
            "best_suited_when": "",
            "source_notes": [],
        })
    return {
        "report_title": "Συγκριτική Ανάλυση Ασφάλισης Υγείας" if greek else "Health Insurance Comparative Analysis",
        "executive_summary": "",
        "client_needs_summary": payload.get("client_priorities") or "",
        "plans": plans,
        "key_differences": [],
        "ashlar_assessment": {
            "recommended_provider": "",
            "recommended_plan": "",
            "headline": "Απαιτείται αξιολόγηση broker." if greek else "Broker assessment required.",
            "reasoning": [],
            "alternative_provider": "",
            "alternative_plan": "",
            "alternative_reason": "",
            "when_the_alternative_may_be_better": "",
        },
        "important_considerations": [],
        "next_steps": [],
        "disclaimer": "Η τελική κάλυψη και αποδοχή υπόκεινται στους όρους και την επιβεβαίωση της ασφαλιστικής." if greek else "Final cover and acceptance remain subject to the insurer's current terms and confirmation.",
    }


def generate_client_analysis(
    *,
    case_reference: str,
    client_name: str,
    client_profile: str,
    client_priorities: str,
    results: list[dict],
    language: str = "English",
) -> dict:
    payload = build_grounded_case_payload(
        case_reference=case_reference,
        client_name=client_name,
        client_profile=client_profile,
        client_priorities=client_priorities,
        results=results,
    )
    api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        out = _fallback_analysis(payload, language)
        out["comparison_matrix"] = payload["comparison_matrix"]
        out["client_name"] = payload["client_name"]
        out["case_reference"] = payload["case_reference"]
        return out

    model = os.getenv("CLIENT_ANALYSIS_MODEL", os.getenv("CLAUDE_MODEL", "claude-haiku-4-5-20251001"))
    language_instruction = (
        "Write every client-facing field in Greek. Keep provider/product names and standard insurance acronyms as stated in source evidence."
        if language.lower().startswith(("gr", "el")) or "greek" in language.lower()
        else "Write every client-facing field in professional English."
    )
    user_prompt = f"""{CLIENT_ANALYSIS_PROMPT}

LANGUAGE REQUIREMENT:
{language_instruction}

=== GROUNDED CASE PAYLOAD ===
{json.dumps(payload, ensure_ascii=False, indent=2, default=str)}
"""
    import anthropic
    client = anthropic.Anthropic(api_key=api_key)
    response = client.messages.create(
        model=model,
        max_tokens=7000,
        messages=[{"role": "user", "content": user_prompt}],
    )
    raw = "".join(block.text for block in response.content if getattr(block, "type", None) == "text").strip()
    try:
        out = parse_first_json_object(raw)
    except json.JSONDecodeError as exc:
        out = _fallback_analysis(payload, language)
        out["generation_warning"] = f"Client narrative returned malformed JSON: {exc}"
        out["raw_response_excerpt"] = raw[:1800]

    out["comparison_matrix"] = payload["comparison_matrix"]
    out["client_name"] = payload["client_name"]
    out["case_reference"] = payload["case_reference"]
    out["client_profile"] = payload["client_profile"]
    out["client_priorities"] = payload["client_priorities"]
    return out
