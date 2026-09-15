"""Determine the applicant's selected plan/tier from the quotation only."""
from __future__ import annotations

import json
import os
import re

from .json_utils import parse_first_json_object

try:
    import anthropic
except ImportError:  # pragma: no cover
    anthropic = None


_COMMON_TIERS = (
    "Bronze Plus", "Bronze", "Silver", "Gold", "Platinum",
    "Standard Plus", "Standard", "Comprehensive", "Premium",
    "Classic", "Executive Plus", "Executive", "Foundation",
)

_PROMPT = """You are an insurance broker reviewing an applicant-specific quotation or
certificate. Identify the SINGLE plan/tier actually being quoted for this applicant.

Rules:
- The file may mention many plan names as marketing, examples or alternatives.
- Do not select a plan merely because it appears.
- Prefer a plan tied to a premium, selected plan, cover level, schedule, certificate,
  quotation breakdown, or explicit applicant selection.
- If no single plan is unambiguous, return null rather than guessing.

Return ONLY JSON:
{
  "provider": "<provider or null>",
  "plan_name": "<selected plan/tier or null>",
  "confidence": "high|medium|low",
  "evidence": "<short reason>",
  "other_plans_mentioned": []
}
"""


def _fallback(text: str, provider_label: str = "") -> dict:
    compact = " ".join((text or "").split())
    cue_re = re.compile(
        r"(?:selected\s+plan|plan\s+option|cover\s+level|plan\s+name|"
        r"quotation\s+for|product\s*[:\-]|tier\s*[:\-]).{0,80}",
        re.IGNORECASE,
    )
    spans = [m.group(0) for m in cue_re.finditer(compact)]
    matches = []
    for tier in _COMMON_TIERS:
        if any(re.search(rf"\b{re.escape(tier)}\b", s, re.IGNORECASE) for s in spans):
            matches.append(tier)
    matches = sorted(set(matches), key=len, reverse=True)
    if len(matches) == 1:
        return {
            "provider": provider_label or None,
            "plan_name": matches[0],
            "confidence": "medium",
            "evidence": "Detected next to a selected-plan/cover-level cue.",
            "other_plans_mentioned": [],
            "method": "rule-based",
        }
    return {
        "provider": provider_label or None,
        "plan_name": None,
        "confidence": "low",
        "evidence": "No single selected plan could be identified safely.",
        "other_plans_mentioned": [
            t for t in _COMMON_TIERS
            if re.search(rf"\b{re.escape(t)}\b", compact, re.IGNORECASE)
        ],
        "method": "rule-based",
    }


def identify_selected_plan(
    quotation_text: str,
    provider_label: str = "",
    manual_override: str = "",
) -> dict:
    if manual_override.strip():
        return {
            "provider": provider_label or None,
            "plan_name": manual_override.strip(),
            "confidence": "high",
            "evidence": "Broker supplied target-plan override.",
            "other_plans_mentioned": [],
            "method": "broker_override",
        }

    text = (quotation_text or "").strip()
    if not text:
        return _fallback("", provider_label)

    api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    if not api_key or anthropic is None:
        return _fallback(text, provider_label)

    model = os.getenv("CLAUDE_MODEL", "claude-haiku-4-5-20251001")
    try:
        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model=model,
            max_tokens=900,
            messages=[{
                "role": "user",
                "content": (
                    f"{_PROMPT}\n\nBroker label: {provider_label or 'Not supplied'}\n\n"
                    f"--- QUOTATION / CERTIFICATE ---\n{text[:40000]}"
                ),
            }],
        )
        raw = "".join(
            block.text for block in response.content
            if getattr(block, "type", None) == "text"
        ).strip()
        result = parse_first_json_object(raw)
        result["method"] = "claude"
        return result
    except Exception:
        return _fallback(text, provider_label)
