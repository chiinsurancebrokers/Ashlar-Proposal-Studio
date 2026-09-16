"""LLM extraction for a target plan after deterministic brochure isolation."""
from __future__ import annotations

import json
import os
import re


from .json_utils import parse_first_json_object
from .carriers import get_carrier_adapter, carrier_metadata


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
- If deterministic evidence contains a value, DO NOT return null for that field.
- Keep diagnostics/advanced imaging separate from preventive or wellness benefits. MRI, CT and PET are diagnostic imaging, not wellness benefits.

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
    "diagnostics_imaging": "Not mentioned",
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


_MISSING_TEXT = {"", "—", "-", "not specified", "not mentioned", "unclear", "null", "none"}


def _missing(value) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip().casefold() in _MISSING_TEXT
    return False


def _amount_number(raw: str) -> float:
    try:
        return float(raw.replace(",", ""))
    except Exception:
        return -1.0


def _currency_symbol(token: str) -> str:
    token = token.upper()
    if token in {"EUR", "€"}:
        return "EUR"
    if token in {"USD", "$"}:
        return "USD"
    if token in {"GBP", "£"}:
        return "GBP"
    return token


def _extract_quote_facts(text: str) -> dict:
    """Extract applicant-specific headline facts without asking the LLM to infer them."""
    facts: dict = {}
    if not text:
        return facts

    # Annual premium: carrier quotes often list component premiums as well as the total.
    # The total is normally the largest amount explicitly labelled 'per year'.
    candidates = []
    for m in re.finditer(
        r"(?P<cur>EUR|USD|GBP|€|\$|£)\s*(?P<amt>\d[\d,.]*)\s*(?:indicative\s*)?per\s+year",
        text,
        flags=re.IGNORECASE,
    ):
        candidates.append((_amount_number(m.group("amt")), m.group("cur"), m.group("amt")))
    if candidates:
        _, cur, amt = max(candidates, key=lambda x: x[0])
        facts["premium"] = {
            "amount": amt.replace(",", ""),
            "currency": _currency_symbol(cur),
            "frequency": "Annual",
        }
        facts["quote_currency"] = _currency_symbol(cur)

    # Cigna-style / modular quotes: deductible + cost-share are applicant-specific.
    d = re.search(
        r"(?P<cur>EUR|USD|GBP|€|\$|£)\s*(?P<ded>\d[\d,.]*)\s*deductible.{0,90}?(?P<share>\d{1,3})%\s*cost\s*share",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if d:
        sym = {"EUR": "€", "USD": "$", "GBP": "£", "€": "€", "$": "$", "£": "£"}.get(d.group("cur").upper(), d.group("cur"))
        phrase = f"{sym}{d.group('ded')} deductible; {d.group('share')}% cost share"
        oop = re.search(
            r"(?P<cur>EUR|USD|GBP|€|\$|£)\s*(?P<oop>\d[\d,.]*)\s*out\s+of\s+pocket\s+maximum",
            text,
            flags=re.IGNORECASE,
        )
        if oop:
            osym = {"EUR": "€", "USD": "$", "GBP": "£", "€": "€", "$": "$", "£": "£"}.get(oop.group("cur").upper(), oop.group("cur"))
            phrase += f"; {osym}{oop.group('oop')} out-of-pocket maximum"
        facts["deductible_or_excess"] = phrase

    # If the quote explicitly says USA cover was not selected, the applicant chose ex-USA area.
    if re.search(r"USA\s*Cover\s*:?\s*Not\s+selected", text, flags=re.IGNORECASE | re.DOTALL):
        facts["area_of_cover"] = "Worldwide excluding USA"
    else:
        ex = re.search(r"Worldwide\s+excluding\s+USA", text, flags=re.IGNORECASE)
        inc = re.search(r"Worldwide\s+including\s+USA", text, flags=re.IGNORECASE)
        if ex and not inc:
            facts["area_of_cover"] = "Worldwide excluding USA"
        elif inc and not ex:
            facts["area_of_cover"] = "Worldwide including USA"

    selected_modules = set()
    module_patterns = {
        "outpatient": r"International\s+Outpatient\s*:?\s*(?:\n|\r|.){0,160}?(?:EUR|USD|GBP|€|\$|£)\s*\d",
        "evacuation": r"International\s+Medical\s+Evacuation\s*:?\s*(?:\n|\r|.){0,80}?(?:EUR|USD|GBP|€|\$|£)\s*\d",
        "wellbeing": r"International\s+Health\s+(?:&|and)\s+Wellbeing\s*:?\s*(?:\n|\r|.){0,80}?(?:EUR|USD|GBP|€|\$|£)\s*\d",
        "vision_dental": r"International\s+Vision\s+(?:&|and)\s+Dental\s*:?\s*(?:\n|\r|.){0,80}?(?:EUR|USD|GBP|€|\$|£)\s*\d",
    }
    for name, pattern in module_patterns.items():
        if re.search(pattern, text, flags=re.IGNORECASE | re.DOTALL):
            selected_modules.add(name)
    facts["selected_modules"] = selected_modules
    return facts


def _focused_rows(context: str) -> list[tuple[int | None, str, str]]:
    rows: list[tuple[int | None, str, str]] = []
    for line in (context or "").splitlines():
        m = re.match(r"\[Page\s+(\d+)\]\s+(.+?)\s*=>\s*(.*)$", line.strip())
        if m:
            rows.append((int(m.group(1)), m.group(2).strip(), m.group(3).strip()))
    return rows


def _find_row(rows: list[tuple[int | None, str, str]], *needles: str) -> tuple[int | None, str, str] | None:
    for row in rows:
        label = row[1].casefold()
        if all(n.casefold() in label for n in needles):
            return row
    return None


def _pick_currency_value(value: str, currency: str = "EUR") -> str:
    if not value:
        return ""
    currency = (currency or "EUR").upper()
    patterns = {
        "EUR": r"€\s*[\d,.]+|EUR\s*[\d,.]+",
        "USD": r"\$\s*[\d,.]+|USD\s*[\d,.]+",
        "GBP": r"£\s*[\d,.]+|GBP\s*[\d,.]+",
    }
    m = re.search(patterns.get(currency, patterns["EUR"]), value, flags=re.IGNORECASE)
    return m.group(0).replace("EUR", "€").replace("USD", "$").replace("GBP", "£") if m else value


def _is_covered(value: str) -> bool:
    key = (value or "").casefold()
    return "covered (table checkmark)" in key or key.strip() in {"covered", "paid in full"}


def _apply_deterministic_facts(result: dict, provider_label: str, quotation_text: str, focused_context: str) -> dict:
    """Lock material facts to quotation/table evidence so an LLM omission cannot blank the UI.

    Applicant-specific headline facts come from a carrier adapter. This keeps a Cigna
    modular quote, a Bupa schedule and a NOW Health quote from being treated as if
    they were the same document layout.
    """
    adapter = get_carrier_adapter(provider_label, quotation_text)
    quote = adapter.extract_quote_facts(quotation_text)
    result["carrier_adapter"] = carrier_metadata(provider_label, quotation_text)
    rows = _focused_rows(focused_context)
    currency = quote.get("quote_currency", "EUR")

    if quote.get("premium"):
        result["premium"] = quote["premium"]
    if quote.get("deductible_or_excess"):
        result["deductible_or_excess"] = quote["deductible_or_excess"]
    if quote.get("area_of_cover"):
        result["area_of_cover"] = quote["area_of_cover"]
    if quote.get("annual_limit"):
        result["annual_limit"] = quote["annual_limit"]

    underwriting = result.setdefault("underwriting", {})
    if quote.get("underwriting_basis"):
        underwriting["basis"] = quote["underwriting_basis"]

    annual = _find_row(rows, "annual overall benefit maximum")
    if annual and not quote.get("annual_limit"):
        result["annual_limit"] = _pick_currency_value(annual[2], currency)

    benefits = result.setdefault("benefits", {})
    selected = quote.get("selected_modules", set())
    for key, value in (quote.get("benefit_hints") or {}).items():
        if value and _missing(benefits.get(key)):
            benefits[key] = value

    if quote.get("fact_warnings"):
        result.setdefault("extraction_warnings", []).extend(quote["fact_warnings"])

    if _missing(benefits.get("inpatient")) and annual:
        benefits["inpatient"] = f"Selected core cover; annual overall benefit maximum {_pick_currency_value(annual[2], currency)}."

    outpatient = _find_row(rows, "annual international outpatient benefit maximum")
    if "outpatient" in selected and outpatient and _missing(benefits.get("outpatient")):
        benefits["outpatient"] = (
            f"International Outpatient selected; annual benefit maximum {_pick_currency_value(outpatient[2], currency)}. "
            f"Applicant quote: {result.get('deductible_or_excess', 'deductible/cost share as quoted')}."
        )

    cancer = _find_row(rows, "extensive cancer care")
    if cancer and _missing(benefits.get("cancer")):
        if _is_covered(cancer[2]):
            benefits["cancer"] = "Extensive Cancer Care is shown as covered for the selected plan, subject to governing terms."
        else:
            benefits["cancer"] = cancer[2]

    mental = _find_row(rows, "mental and behavioural health care")
    if mental and _missing(benefits.get("mental_health")):
        benefits["mental_health"] = f"{_pick_currency_value(mental[2], currency)} ({mental[2]})"

    evac = _find_row(rows, "medical evacuation")
    if "evacuation" in selected and evac and _missing(benefits.get("evacuation_repatriation")):
        benefits["evacuation_repatriation"] = "International Medical Evacuation selected; target-plan table shows medical evacuation/repatriation cover."

    dental = _find_row(rows, "annual dental benefit maximum")
    if "vision_dental" in selected and dental and _missing(benefits.get("dental")):
        benefits["dental"] = f"International Vision & Dental selected; annual dental benefit maximum {_pick_currency_value(dental[2], currency)}."

    eye = _find_row(rows, "eye test")
    if "vision_dental" in selected and eye and _missing(benefits.get("optical")):
        benefits["optical"] = f"International Vision & Dental selected; eye-test benefit {_pick_currency_value(eye[2], currency)} per period of cover."

    # Advanced diagnostic imaging is its own material benefit. Do not fold MRI/CT/PET
    # into preventive/wellness just because a carrier table places it near health benefits.
    advanced_imaging = _find_row(rows, "advanced medical imaging")
    ct_pet_mri = _find_row(rows, "ct", "pet", "mri")
    outpatient_diagnostic = next((r for r in rows if r[1].strip().casefold() == "diagnostic"), None)
    if _missing(benefits.get("diagnostics_imaging")):
        if advanced_imaging:
            benefits["diagnostics_imaging"] = (
                f"Advanced Medical Imaging (MRI/CT/PET): {_pick_currency_value(advanced_imaging[2], currency)}."
            )
        elif ct_pet_mri:
            detail = "CT/PET/MRI are covered for in-patient/day-patient treatment"
            if outpatient_diagnostic and "out-patient limit" in outpatient_diagnostic[2].casefold():
                detail += "; outpatient diagnostic treatment is covered within the overall outpatient limit"
            benefits["diagnostics_imaging"] = detail + "."

    routine_exam = _find_row(rows, "routine adult physical examination")
    if "wellbeing" in selected and routine_exam and _missing(benefits.get("preventive")):
        benefits["preventive"] = f"International Health & Wellbeing selected; routine adult physical examination {_pick_currency_value(routine_exam[2], currency)}."

    # Add deterministic source-map entries without duplicating model evidence.
    evidence = result.setdefault("source_evidence", [])
    existing_fields = {str(x.get("field", "")) for x in evidence if isinstance(x, dict)}
    if quote.get("premium") and "premium" not in existing_fields:
        evidence.append({"field": "premium", "value": result["premium"], "document": "Applicant quotation", "page": None, "evidence": "Applicant-specific annual premium"})
    if quote.get("annual_limit") and "annual_limit" not in existing_fields:
        evidence.append({"field": "annual_limit", "value": result.get("annual_limit"), "document": "Applicant quotation", "page": None, "evidence": "Applicant-specific annual/overall plan limit"})
    elif annual and "annual_limit" not in existing_fields:
        evidence.append({"field": "annual_limit", "value": result.get("annual_limit"), "document": "Target-plan table evidence", "page": annual[0], "evidence": annual[1]})
    if outpatient and "outpatient" not in existing_fields:
        evidence.append({"field": "outpatient", "value": _pick_currency_value(outpatient[2], currency), "document": "Target-plan table evidence", "page": outpatient[0], "evidence": outpatient[1]})

    return result


def _merge_missing(base: dict, repair: dict) -> dict:
    """Fill only missing values in base from a compact second-pass extraction."""
    for key, value in (repair or {}).items():
        if key not in base or _missing(base.get(key)):
            base[key] = value
        elif isinstance(base.get(key), dict) and isinstance(value, dict):
            _merge_missing(base[key], value)
        elif isinstance(base.get(key), list) and not base.get(key) and isinstance(value, list):
            base[key] = value
    return base


def _needs_repair(result: dict) -> bool:
    missing_headlines = 0
    premium = result.get("premium") or {}
    if _missing(premium.get("amount")):
        missing_headlines += 1
    for key in ("annual_limit", "deductible_or_excess", "area_of_cover"):
        if _missing(result.get(key)):
            missing_headlines += 1
    benefits = result.get("benefits") or {}
    missing_benefits = sum(_missing(benefits.get(k)) for k in ("inpatient", "outpatient", "cancer", "mental_health", "dental", "evacuation_repatriation"))
    return missing_headlines >= 2 or missing_benefits >= 5


def _call_model(client, model: str, payload: str) -> tuple[dict | None, str, str | None]:
    response = client.messages.create(
        model=model,
        max_tokens=7000,
        messages=[{"role": "user", "content": payload}],
    )
    raw = "".join(
        block.text for block in response.content
        if getattr(block, "type", None) == "text"
    ).strip()
    try:
        return parse_first_json_object(raw), raw, None
    except json.JSONDecodeError as exc:
        return None, raw, str(exc)


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

    # When deterministic target-plan rows exist, keep the generic brochure context
    # smaller. This reduces model distraction from neighbouring tiers.
    brochure_cap = 35000 if focused_table_context else 90000
    payload = f"""{SCHEMA_PROMPT}

=== TARGET PLAN LOCK ===
Provider label: {provider_label}
TARGET PLAN: {target_lock}

=== DETERMINISTIC TARGET PLAN TABLE EVIDENCE ===
{focused_table_context[:60000] or "No deterministic multi-plan table extraction was available."}

=== APPLICANT-SPECIFIC QUOTATION / CERTIFICATE ===
{quotation_text[:50000] or "Not supplied"}

=== BROCHURE / TABLE OF BENEFITS ===
{brochure_text[:brochure_cap] or "Not supplied"}

=== POLICY WORDING / SUPPORTING TERMS ===
{wording_text[:70000] or "Not supplied"}
"""

    import anthropic
    client = anthropic.Anthropic(api_key=api_key)
    result, raw, parse_error = _call_model(client, model, payload)
    if result is None:
        return {
            "provider": provider_label,
            "plan_name": target_plan or None,
            "target_plan_found": bool(focused_table_context),
            "error": "AI analysis returned malformed JSON",
            "error_detail": parse_error,
            "raw_response_excerpt": raw[:2500],
            "confidence": "low",
        }

    # If the first response omitted material fields, run one compact recovery pass
    # using only the applicant quote + already isolated target-plan evidence.
    if _needs_repair(result) and (quotation_text or focused_table_context):
        repair_payload = f"""{SCHEMA_PROMPT}

The prior extraction omitted material fields. Re-extract the target plan from the compact evidence below.
Do not return null where the evidence explicitly states a value.

TARGET PLAN: {target_lock}
PROVIDER: {provider_label}

=== APPLICANT QUOTATION ===
{quotation_text[:35000] or "Not supplied"}

=== TARGET-PLAN TABLE EVIDENCE ===
{focused_table_context[:55000] or "Not supplied"}

=== SUPPORTING TERMS ===
{wording_text[:25000] or "Not supplied"}
"""
        repair, _, _ = _call_model(client, model, repair_payload)
        if repair:
            result = _merge_missing(result, repair)

    # Deterministic quote/table facts have final authority over model omissions or
    # conflicting headline values.
    result = _apply_deterministic_facts(result, provider_label, quotation_text, focused_table_context)

    result.setdefault("provider", provider_label)
    result.setdefault("plan_name", target_plan or None)
    result.setdefault("target_plan_found", bool(target_plan or focused_table_context))
    result.setdefault("confidence", "medium")
    return result
