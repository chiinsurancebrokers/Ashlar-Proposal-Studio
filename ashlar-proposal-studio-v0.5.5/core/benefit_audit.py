"""A second reader for the benefit lines, from a different model family.

WHY THIS EXISTS
---------------
A client pack went out saying a plan covered no maternity, no dental, no
optical and no cancer. The extraction was right and the document was wrong,
and nothing between the two was in a position to notice: the same reasoning
that wrote the benefit line also decided it was fine.

This module puts a reader that did not write the line in front of the
insurer's own document and asks one question per benefit: does the document
say what we wrote? It is a check, not an author. It never edits a benefit, it
reports, and the broker decides.

WHAT IT WILL NOT DO
-------------------
It will not pass quietly. A missing key, an unreachable provider or a
malformed answer leaves `ran` False, and the caller is expected to keep the
gate shut rather than treat silence as agreement. An audit that fails open is
worse than no audit, because it is believed.

It also does not accept a verdict it did not offer: anything outside the
three allowed values is recorded as "not found", so an inventive answer
cannot be read as approval.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field

from .excerpt import benefit_focused_excerpt
from .model_errors import explain as explain_model_error

AGREES = "agrees"
DISAGREES = "disagrees"
NOT_FOUND = "not_found"
_ALLOWED = {AGREES, DISAGREES, NOT_FOUND}

# The wordings run to a hundred pages; the excerpt keeps the highest-signal
# part of them inside a budget the second reader can actually attend to.
DOCUMENT_CHARS = 60000


@dataclass(frozen=True)
class BenefitFinding:
    plan: str
    benefit_key: str
    benefit_label: str
    verdict: str
    extracted: str
    note: str = ""

    @property
    def needs_attention(self) -> bool:
        return self.verdict != AGREES


@dataclass(frozen=True)
class AuditResult:
    findings: list[BenefitFinding] = field(default_factory=list)
    ran: bool = False
    error: str = ""
    model: str = ""

    @property
    def disagreements(self) -> list[BenefitFinding]:
        return [f for f in self.findings if f.verdict == DISAGREES]

    @property
    def unverified(self) -> list[BenefitFinding]:
        return [f for f in self.findings if f.verdict == NOT_FOUND]

    @property
    def is_clean(self) -> bool:
        """True only when the check ran and found nothing to dispute.

        A check that did not run is not clean. The distinction is the whole
        point of the gate.
        """
        return self.ran and not self.disagreements


PROMPT = """You are checking another analyst's work against an insurer's own document.

For EACH benefit line below, decide only this: does the DOCUMENT support what the analyst wrote?

Return JSON: {"findings": [{"key": "<benefit key>", "verdict": "agrees|disagrees|not_found", "note": "<the document's own words, when you disagree>"}]}

Rules:
- "agrees": the document supports the line, including its limits and conditions.
- "disagrees": the document says something materially different. Quote the document in `note`.
- "not_found": the document does not address this benefit. This is not a criticism.
- Judge the substance, not the wording. A line that says the same thing in different words agrees.
- A line that describes an included benefit and also names what sits outside it (for example "Orthodontics are not covered" inside a dental benefit) is describing cover, not an absence.
- Use ONLY the document. If it is silent, say not_found rather than reasoning from what is usual.

PLAN: {plan}

DOCUMENT:
{document}

BENEFIT LINES:
{lines}
"""


def _client():
    """The second reader. A different family from the one that wrote the lines."""
    try:
        from openai import OpenAI
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("The openai package is not installed.") from exc
    key = os.getenv("OPENAI_API_KEY", "").strip()
    if not key:
        raise RuntimeError(
            "The second-opinion check could not run: OPENAI_API_KEY is not set in Railway."
        )
    return OpenAI(api_key=key)


def _lines_for(analysis: dict, benefit_order) -> list[tuple[str, str, str]]:
    benefits = analysis.get("benefits") or {}
    out = []
    for key, label in benefit_order:
        value = str(benefits.get(key) or "").strip()
        if value:
            out.append((key, label, value))
    return out


def audit_plan(*, plan_name: str, analysis: dict, document_text: str, benefit_order,
               model: str = "", client=None) -> AuditResult:
    """Check one plan's benefit lines against one document."""
    lines = _lines_for(analysis, benefit_order)
    if not lines:
        return AuditResult(ran=True, model=model, findings=[])
    if not (document_text or "").strip():
        return AuditResult(
            ran=False,
            error=f"No document text is stored for {plan_name}, so the benefit lines could not be checked.",
        )

    model = model or os.getenv("OPENAI_CHAT_MODEL", "gpt-4o")
    try:
        client = client or _client()
        prompt = (
            PROMPT.replace("{plan}", plan_name)
            .replace("{document}", benefit_focused_excerpt(document_text, DOCUMENT_CHARS))
            .replace("{lines}", "\n".join(f"- {key} ({label}): {value}" for key, label, value in lines))
        )
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
        )
        payload = json.loads(response.choices[0].message.content or "{}")
    except RuntimeError as exc:
        return AuditResult(ran=False, error=str(exc), model=model)
    except json.JSONDecodeError:
        return AuditResult(
            ran=False, model=model,
            error="The second-opinion check returned something that was not valid JSON.",
        )
    except Exception as exc:
        return AuditResult(
            ran=False, model=model,
            error=explain_model_error(exc, model=model, subject="The second-opinion check"),
        )

    by_key = {str(item.get("key") or ""): item for item in (payload.get("findings") or [])
              if isinstance(item, dict)}
    findings = []
    for key, label, value in lines:
        item = by_key.get(key) or {}
        verdict = str(item.get("verdict") or "").strip().lower()
        if verdict not in _ALLOWED:
            # An answer outside the three offered is not approval. A benefit
            # the checker did not rule on stays unverified.
            verdict = NOT_FOUND
        findings.append(BenefitFinding(
            plan=plan_name, benefit_key=key, benefit_label=label, verdict=verdict,
            extracted=value, note=str(item.get("note") or "").strip(),
        ))
    return AuditResult(findings=findings, ran=True, model=model)


def audit_case(*, results: list[dict], documents: dict[str, str], benefit_order,
               model: str = "", client=None) -> AuditResult:
    """Check every plan in the case. `documents` maps plan name to its text."""
    from .client_analysis import plan_display_name

    findings: list[BenefitFinding] = []
    errors: list[str] = []
    ran_any = False
    for result in results or []:
        name = plan_display_name(result)
        outcome = audit_plan(
            plan_name=name,
            analysis=result.get("analysis") or {},
            document_text=documents.get(name, ""),
            benefit_order=benefit_order,
            model=model,
            client=client,
        )
        findings.extend(outcome.findings)
        if outcome.ran:
            ran_any = True
        elif outcome.error:
            errors.append(outcome.error)

    # Every plan has to be checked. One plan that could not be read leaves the
    # case unchecked, because the unread plan is exactly where the error would
    # be hiding.
    return AuditResult(
        findings=findings,
        ran=ran_any and not errors,
        error=" ".join(errors),
        model=model or os.getenv("OPENAI_CHAT_MODEL", "gpt-4o"),
    )
