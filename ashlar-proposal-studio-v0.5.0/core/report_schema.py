"""Validation for client-facing report narratives.

A syntactically valid JSON object is not enough: the report must contain all
expected plan narratives and a usable Ashlar assessment before it can replace a
previous client report.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, ValidationError, field_validator


class PlanNarrative(BaseModel):
    provider: str = Field(min_length=1)
    plan_name: str = Field(min_length=1)
    positioning: str = ""
    summary: str = Field(min_length=1)
    strengths: list[str] = Field(default_factory=list)
    considerations: list[str] = Field(default_factory=list)
    best_suited_when: str = ""
    source_notes: list[str] = Field(default_factory=list)


class KeyDifference(BaseModel):
    title: str = Field(min_length=1)
    analysis: str = Field(min_length=1)
    client_impact: str = ""


class AshlarAssessment(BaseModel):
    recommended_provider: str = ""
    recommended_plan: str = ""
    headline: str = Field(min_length=1)
    reasoning: list[str] = Field(default_factory=list)
    alternative_provider: str = ""
    alternative_plan: str = ""
    alternative_reason: str = ""
    when_the_alternative_may_be_better: str = ""

    @field_validator("reasoning")
    @classmethod
    def reasoning_has_content(cls, value: list[str]) -> list[str]:
        if not any(str(x).strip() for x in value):
            raise ValueError("Ashlar assessment reasoning is empty")
        return value


class ClientReport(BaseModel):
    report_title: str = Field(min_length=1)
    executive_summary: str = Field(min_length=1)
    client_needs_summary: str = ""
    plans: list[PlanNarrative] = Field(min_length=1)
    key_differences: list[KeyDifference] = Field(default_factory=list)
    ashlar_assessment: AshlarAssessment
    important_considerations: list[str] = Field(default_factory=list)
    next_steps: list[str] = Field(min_length=1)
    disclaimer: str = Field(min_length=1)


class ClientReportValidationError(ValueError):
    pass


def _norm(value: Any) -> str:
    import re
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").casefold()).strip()


def validate_client_report(report: dict, results: list[dict]) -> dict:
    """Validate structure and ensure every analyzed plan has a narrative.

    Returns the original dict when valid. Raises ClientReportValidationError on
    incomplete/partial model output so callers can preserve the previous report.
    """
    try:
        ClientReport.model_validate(report)
    except ValidationError as exc:
        raise ClientReportValidationError(f"Client report failed schema validation: {exc}") from exc

    expected: list[tuple[str, str]] = []
    for result in results or []:
        analysis = result.get("analysis") or {}
        expected.append((
            _norm(analysis.get("provider") or result.get("provider")),
            _norm(analysis.get("plan_name") or result.get("target_plan")),
        ))

    received = [(_norm(p.get("provider")), _norm(p.get("plan_name"))) for p in report.get("plans") or []]
    missing = []
    for ep, en in expected:
        matched = False
        for rp, rn in received:
            provider_ok = bool(ep and rp and (ep == rp or ep in rp or rp in ep))
            plan_ok = bool(en and rn and (en == rn or en in rn or rn in en))
            if provider_ok and plan_ok:
                matched = True
                break
        if not matched:
            missing.append(f"{ep or 'provider'} / {en or 'plan'}")

    if missing:
        raise ClientReportValidationError(
            "Client report is incomplete. Missing plan narrative(s): " + ", ".join(missing)
        )

    if len(expected) > 1 and not (report.get("key_differences") or []):
        raise ClientReportValidationError("Comparative report contains no key differences.")

    return report
