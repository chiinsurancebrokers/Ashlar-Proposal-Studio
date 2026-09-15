"""LLM extraction for a target plan after deterministic brochure isolation."""
from __future__ import annotations

import json
import os

import anthropic


SCHEMA_PROMPT = """You are the analysis engine inside Ashlar Proposal Studio.
You are comparing insurance propositions for a professional broker.

A carrier brochure may show MANY plan tiers side by side. You will receive an explicit
TARGET PLAN and, where available, deterministic TARGET PLAN TABLE EVIDENCE isolated
from that exact column. You must analyze ONLY the target plan.

Priority of evidence:
1. Applicant-specific Quotation / Certificate: premium, chosen excess/deductible,
   selected options, exact plan, area, applicant-specific endorsements.
2. TARGET PLAN TABLE EVIDENCE: plan-specific benefits isolated from a multi-plan table.
3. Policy wording / member guide: exclusions, definitions, underwriting, conditions.
4. Generic brochure prose/supporting documents.

NON-NEGOTIABLE RULES:
- Never borrow a figure from a neighbouring tier.
- If a brochure says a benefit is OPTIONAL, do not present it as included unless the
  applicant-specific quote/certificate confirms the option was selected.
- Distinguish "Included", "Optional — not confirmed selected", "Not covered",
  "Not mentioned", and "Unclear".
- A visual table checkmark in TARGET PLAN TABLE EVIDENCE means that benefit is shown
  as covered in the target plan's table cell, subject to the governing policy.
- Keep source page numbers wherever PAGE markers or target-table page references exist.
- If the target plan cannot be found in the supplied source, say so; do not guess.
- Brochures are summaries. Policy wording/certificate remains the governing source.

Return ONLY valid JSON:
{
  "provider": null,
  "plan_name": null,
  "target_plan_found": true,
  "premium": {"amount": null, "currency": null, "frequency": null},
  "deductible_or_excess": "Not specified",
  "annual_limit": "Not specified",
  "area_of_cover": "Not specified",
  "underwriting": {
    "basis": "Not specified",
    "pre_existing_conditions": "Not specified"
  },
  "benefits": {
    "inpatient": "Not mentioned",
    "outpatient": "Not mentioned",
    "cancer": "Not mentioned",
    "chronic_conditions": "Not mentioned",
    "mental_health": "Not mentioned",
    "maternity": "Not mentioned",
    "dental": "Not mentioned",
    "optical": "Not mentioned",
    "preventive": "Not mentioned",
    "evacuation_repatriation": "Not mentioned"
  },
  "waiting_periods": [],
  "optional_benefits": [
    {
      "benefit": "",
      "status": "Optional — not confirmed selected",
      "limit": "",
      "waiting_period": "",
      "source_page": null
    }
  ],
  "critical_limitations": [
    {"topic": "", "detail": "", "source_page": null}
  ],
  "source_evidence": [
    {
      "field": "annual_limit",
      "value": "",
      "document": "",
      "page": null,
      "evidence": ""
    }
  ],
  "confidence": "high|medium|low"
}
"""


def analyze_target_plan(
    *,
    provider_label: str,
    target_plan: str,
    quotation_text: str,
    brochure_text: str,
    wording_text: str,
    focused_table_context: str = "",
) -> dict:
    api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        return {
            "provider": provider_label,
            "plan_name": target_plan or None,
            "target_plan_found": bool(focused_table_context),
            "error": "ANTHROPIC_API_KEY is not configured",
            "focused_table_context": focused_table_context,
            "confidence": "low",
        }

    model = os.getenv("CLAUDE_MODEL", "claude-haiku-4-5-20251001")
    target_lock = target_plan or "NOT YET IDENTIFIED"
    payload = f"""{SCHEMA_PROMPT}

=== TARGET PLAN LOCK ===
Provider label: {provider_label}
TARGET PLAN: {target_lock}

=== DETERMINISTIC TARGET PLAN TABLE EVIDENCE ===
{focused_table_context or "No deterministic multi-plan table extraction was available."}

=== APPLICANT-SPECIFIC QUOTATION / CERTIFICATE ===
{quotation_text[:50000] or "Not supplied"}

=== BROCHURE / TABLE OF BENEFITS ===
{brochure_text[:90000] or "Not supplied"}

=== POLICY WORDING / SUPPORTING TERMS ===
{wording_text[:90000] or "Not supplied"}
"""

    client = anthropic.Anthropic(api_key=api_key)
    response = client.messages.create(
        model=model,
        max_tokens=7000,
        messages=[{"role": "user", "content": payload}],
    )
    raw = "".join(
        block.text for block in response.content
        if getattr(block, "type", None) == "text"
    ).strip()
    raw = raw.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    return json.loads(raw)
