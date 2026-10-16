"""A second reader for the coverage-limiting clauses.

WHY THIS EXISTS
---------------
A critical limitation is the clause a client misses: a 90-day cap on life
support under an otherwise unlimited inpatient benefit, a visit limit hiding
behind "paid in full". Those are the lines where a wrong number or a missing
clause costs the client money, and they are written by the same reasoning that
would also have to notice they were wrong.

This module puts a reader from a different model family in front of the
insurer's own document and asks two questions:

1. PRECISION. Does the document support each limitation the analyst wrote,
   with the figure the analyst wrote?
2. RECALL. Is there a clause in the document that caps, conditions or excludes
   cover and is missing from the analyst's list?

It is a check, not an author. It never edits a limitation and never adds one.
A clause the second reader says was missed is shown to the broker with the
document's own words, and the broker decides.

WHAT IT WILL NOT DO
-------------------
It will not pass quietly. A missing key, an unreachable provider, a malformed
answer or a plan with no stored document leaves `ran` False, and the caller is
expected to keep the gate shut. An audit that fails open is worse than none,
because it is believed.

It does not accept a verdict it did not offer: anything outside the three
allowed values is recorded as "not found". It does not trust a figure it
cannot find in the document either: a limitation whose number appears nowhere
in the text cannot be "agreed", whatever the second reader said. And a clause
reported as missed is discarded unless its quotation really occurs in the
document, so the second reader cannot invent a limitation any more than the
first can.

The check is deliberately a separate call from the benefit-line check. The
benefit excerpt is chosen around the Table of Benefits; limitations sit deep
in the general exclusions, so this module builds its own excerpt around the
figures and topics of the limitations being checked.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field

from .benefit_audit import AGREES, DISAGREES, NOT_FOUND, _ALLOWED, _client
from .excerpt import _DOC_HEADER, _MARKER
from .model_errors import explain as explain_model_error

DOCUMENT_CHARS = 60000
MAX_MISSED = 8
_WINDOW = 3000  # used when a document has no PAGE markers

# ---------------------------------------------------------------------------
# Figures: the numbers a limitation stands on
# ---------------------------------------------------------------------------

_MONEY = re.compile(
    r"(?:€|eur(?:o)?|usd|us\$|\$|£|gbp)\s?(\d[\d,.]*\d|\d)|(\d[\d,.]*\d|\d)\s?(?:€|eur(?:o)?s?|usd|gbp|£)(?!\w)",
    re.I,
)
_COUNT = re.compile(
    r"\b(\d{1,4})\s?(?:-\s?)?(days?|nights?|weeks?|months?|years?|visits?|sessions?|"
    r"consultations?|treatments?|cycles?|%|percent)",
    re.I,
)
_UNIT_STEM = {
    "day": "day", "night": "night", "week": "week", "month": "month", "year": "year",
    "visit": "visit", "session": "session", "consultation": "consult",
    "treatment": "treat", "cycle": "cycle", "%": r"%|percent", "percent": r"%|percent",
}


@dataclass(frozen=True)
class Figure:
    kind: str       # "money" or "count"
    value: str      # digits only, separators removed
    unit: str = ""  # unit stem for counts
    shown: str = ""  # as written, for messages


def _digits(token: str) -> str:
    """Digits only. "5,000.00" and "5000" are the same amount."""
    token = re.sub(r"[.,]00$", "", token.strip(".,"))
    return re.sub(r"[,.]", "", token)


def extract_figures(text: str) -> list[Figure]:
    """The amounts and counts a limitation states."""
    out: list[Figure] = []
    seen: set[tuple[str, str, str]] = set()
    for m in _MONEY.finditer(text or ""):
        raw = m.group(1) or m.group(2)
        fig = Figure("money", _digits(raw), "", m.group(0).strip())
        key = (fig.kind, fig.value, fig.unit)
        if fig.value and key not in seen:
            seen.add(key)
            out.append(fig)
    for m in _COUNT.finditer(text or ""):
        unit = m.group(2).lower().rstrip("s") if m.group(2).lower() not in ("%",) else "%"
        stem = _UNIT_STEM.get(unit, unit)
        fig = Figure("count", m.group(1), stem, m.group(0).strip())
        key = (fig.kind, fig.value, fig.unit)
        if key not in seen:
            seen.add(key)
            out.append(fig)
    return out


def _doc_numbers(text: str) -> set[str]:
    return {_digits(t) for t in re.findall(r"\d[\d,.]*", text or "")}


def missing_figures(detail: str, document_text: str) -> list[str]:
    """Figures a limitation states that the document text does not contain.

    Money must appear as the same digits somewhere in the document. A count must
    appear next to its own unit, with up to two words between ("90 consecutive
    days"). Some PDFs extract every glyph twice ("EUREUR 125125"); that form is
    accepted too. An empty document proves nothing, so it returns nothing: the
    caller handles a missing document separately.
    """
    if not (document_text or "").strip():
        return []
    low = document_text.casefold()
    numbers = _doc_numbers(document_text)
    absent: list[str] = []
    for fig in extract_figures(detail):
        if fig.kind == "money":
            if fig.value in numbers or fig.value * 2 in numbers:
                continue
        else:
            pattern = rf"\b{re.escape(fig.value)}\s?(?:-\s?)?(?:\w+\s+){{0,2}}(?:{fig.unit})"
            if re.search(pattern, low):
                continue
        absent.append(fig.shown or fig.value)
    return absent


# ---------------------------------------------------------------------------
# The excerpt: pages that can contain a limitation
# ---------------------------------------------------------------------------

_SIGNALS = (
    (r"general exclusions?|what is not covered|exclusions? (?:and|&) limitations?", 8),
    (r"not covered|excluded|exclusion|we (?:do not|will not|don.t) (?:pay|cover)", 4),
    (r"sub-?limit|limited to|maximum|capped|\bcap\b|up to|per (?:policy |insurance )?year|lifetime", 3),
    (r"\b\d{1,3}\s?(?:days?|nights?|weeks?|months?|visits?|sessions?|consultations?)\b", 3),
    (r"waiting period|pre-?existing|pre-?authori[sz]ation|pre-?approval|co-?payment|co-?insurance", 3),
    (r"(?:€|eur|usd|us\$|\$|£|gbp)\s?\d", 2),
)
_FIGURE_BONUS = 40   # a page that states a figure the analyst wrote
_TOPIC_BONUS = 12    # a page that names the limitation's topic


def _topic_words(topic: str) -> list[str]:
    return [w for w in re.findall(r"[a-z]{5,}", (topic or "").casefold())
            if w not in {"limit", "limits", "maximum", "benefit", "benefits", "cover", "covered"}]


def _score(chunk: str, limitations: list[tuple[str, str]]) -> float:
    low = chunk.casefold()
    density = sum(w * len(re.findall(p, low)) for p, w in _SIGNALS) * 1000 / max(len(chunk), 400)
    numbers = _doc_numbers(chunk)
    bonus = 0.0
    for topic, detail in limitations:
        for fig in extract_figures(detail):
            if fig.kind == "money" and fig.value in numbers:
                bonus += _FIGURE_BONUS
            elif fig.kind == "count" and re.search(
                rf"\b{re.escape(fig.value)}\s?(?:-\s?)?(?:\w+\s+){{0,2}}(?:{fig.unit})", low
            ):
                bonus += _FIGURE_BONUS
        if any(w in low for w in _topic_words(topic)):
            bonus += _TOPIC_BONUS
    return density + bonus


def _windows(text: str) -> list[str]:
    return [text[i:i + _WINDOW] for i in range(0, len(text), _WINDOW)]


def limitation_excerpt(text: str, limitations: list[tuple[str, str]], cap: int = DOCUMENT_CHARS) -> str:
    """The highest-signal pages for limitation checking, within ``cap``.

    Pages are scored for exclusion and limit language, and strongly for stating
    a figure or naming a topic of the limitations being checked. Document
    headers and each document's first page are always kept. Pages are returned
    in their original order.
    """
    text = text or ""
    if len(text) <= cap:
        return text
    chunks = [c for c in _MARKER.split(text) if c]
    if len(chunks) < 3:
        chunks = _windows(text)

    keep: set[int] = set()
    used = 0
    for i, chunk in enumerate(chunks):
        if _DOC_HEADER.match(chunk) or (i > 0 and _DOC_HEADER.match(chunks[i - 1])) or i == 0:
            if used + len(chunk) <= cap:
                keep.add(i)
                used += len(chunk)
    ranked = sorted((i for i in range(len(chunks)) if i not in keep),
                    key=lambda i: -_score(chunks[i], limitations))
    for i in ranked:
        if used + len(chunks[i]) <= cap:
            keep.add(i)
            used += len(chunks[i])

    out, gap = [], False
    for i, chunk in enumerate(chunks):
        if i in keep:
            if gap:
                out.append("[… pages with less limitation detail omitted …]\n")
            out.append(chunk)
            gap = False
        else:
            gap = True
    return "".join(out)[:cap]


# ---------------------------------------------------------------------------
# Results
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class LimitationFinding:
    plan: str
    key: str
    topic: str
    detail: str
    verdict: str
    note: str = ""
    source_page: str = ""
    figures_missing: tuple[str, ...] = ()

    @property
    def needs_attention(self) -> bool:
        return self.verdict != AGREES


@dataclass(frozen=True)
class MissedLimitation:
    plan: str
    topic: str
    quote: str


@dataclass(frozen=True)
class LimitationAuditResult:
    findings: list[LimitationFinding] = field(default_factory=list)
    missed: list[MissedLimitation] = field(default_factory=list)
    ran: bool = False
    error: str = ""
    model: str = ""

    @property
    def disagreements(self) -> list[LimitationFinding]:
        return [f for f in self.findings if f.verdict == DISAGREES]

    @property
    def unverified(self) -> list[LimitationFinding]:
        return [f for f in self.findings if f.verdict == NOT_FOUND]

    @property
    def is_clean(self) -> bool:
        """True only when the check ran, nothing is disputed and nothing was missed.

        A check that did not run is not clean. The distinction is the whole
        point of the gate.
        """
        return self.ran and not self.disagreements and not self.missed


PROMPT = """You are checking another analyst's work against an insurer's own document.
The analyst listed the clauses of one plan that limit or condition cover, the ones a client could easily miss.

PART 1. For EACH limitation line below, decide only this: does the DOCUMENT support what the analyst wrote, including the figure?

PART 2. Look in the DOCUMENT for clauses that cap, condition or exclude cover in a way a client could easily miss (day or visit caps, sub-limits, co-payments, waiting periods, pre-authorisation duties, exclusions of common treatments) and that are NOT covered by any analyst line.

Return JSON: {"findings": [{"key": "<limitation key>", "verdict": "agrees|disagrees|not_found", "note": "<the document's own words, when you disagree>"}], "possibly_missed": [{"topic": "<short label>", "quote": "<words copied exactly from the document>"}]}

Rules:
- "agrees": the document supports the line, with the same figure and the same conditions.
- "disagrees": the document says something materially different (another figure, another unit, another scope). Quote the document in `note`.
- "not_found": the document does not address this limitation. This is not a criticism.
- Judge the substance, not the wording. The same limit in different words agrees.
- The document may show several plans or tiers side by side. Judge against the plan named below and no other column.
- Use ONLY the document. If it is silent, say not_found rather than reasoning from what is usual.
- For possibly_missed: at most {max_missed} items, only clauses that materially change what a claim pays, each with a `quote` of at most 40 words copied exactly from the document. If you cannot quote it, do not list it. If there are none, return [].

PLAN: {plan}

DOCUMENT:
{document}

LIMITATION LINES:
{lines}
"""


def limitation_lines(analysis: dict) -> list[tuple[str, str, str, str]]:
    """(key, topic, detail, source_page) for each limitation, keyed L1, L2, ..."""
    out = []
    for i, item in enumerate((analysis or {}).get("critical_limitations") or [], start=1):
        if isinstance(item, dict):
            topic = str(item.get("topic") or "").strip()
            detail = str(item.get("detail") or "").strip()
            page = str(item.get("source_page") or "").strip()
        else:
            topic, detail, page = "", str(item or "").strip(), ""
        if detail or topic:
            out.append((f"L{i}", topic, detail or topic, page))
    return out


def case_fingerprint(results: list[dict]) -> str:
    """Identifies the limitations a check was run on.

    A stored check only counts while the plans and their limitations are exactly
    what it was run on. Re-analysing a plan, or opening another case, changes the
    fingerprint, and the old result stops applying.
    """
    import hashlib

    from .client_analysis import plan_display_name

    payload = [[plan_display_name(r), limitation_lines(r.get("analysis") or {})] for r in results or []]
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode("utf-8")).hexdigest()


def _norm(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip().casefold()


def quote_in_document(quote: str, document_text: str) -> bool:
    """True when every stretch of a quotation really occurs in the document.

    A quotation may be elided with "…" or "..."; each stretch of three words or
    more has to be found, in the document's own words. Nothing shorter counts as
    a quotation.
    """
    doc = _norm(document_text)
    parts = [p.strip(" \"'“”‘’") for p in re.split(r"…|\.\.\.", str(quote or ""))]
    parts = [_norm(p) for p in parts if len(p.split()) >= 3]
    return bool(parts) and all(p in doc for p in parts)


def audit_plan(*, plan_name: str, analysis: dict, document_text: str,
               model: str = "", client=None) -> LimitationAuditResult:
    """Check one plan's limitations, and look for ones it is missing."""
    if not (document_text or "").strip():
        return LimitationAuditResult(
            ran=False,
            error=f"No document text is stored for {plan_name}, so the limitations could not be checked.",
        )
    lines = limitation_lines(analysis)

    model = model or os.getenv("OPENAI_CHAT_MODEL", "gpt-4o")
    try:
        client = client or _client()
        excerpt = limitation_excerpt(document_text, [(t, d) for _, t, d, _ in lines])
        listing = "\n".join(f"- {key} ({topic or 'limitation'}): {detail}" for key, topic, detail, _ in lines) \
            or "(the analyst listed no limitations)"
        prompt = (
            PROMPT.replace("{max_missed}", str(MAX_MISSED))
            .replace("{plan}", plan_name)
            .replace("{document}", excerpt)
            .replace("{lines}", listing)
        )
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
        )
        payload = json.loads(response.choices[0].message.content or "{}")
    except RuntimeError as exc:
        return LimitationAuditResult(ran=False, error=str(exc), model=model)
    except json.JSONDecodeError:
        return LimitationAuditResult(
            ran=False, model=model,
            error="The second-opinion check on the limitations returned something that was not valid JSON.",
        )
    except Exception as exc:
        return LimitationAuditResult(
            ran=False, model=model,
            error=explain_model_error(exc, model=model, subject="The second-opinion check on the limitations"),
        )

    by_key = {str(item.get("key") or ""): item for item in (payload.get("findings") or [])
              if isinstance(item, dict)}
    findings: list[LimitationFinding] = []
    for key, topic, detail, page in lines:
        item = by_key.get(key) or {}
        verdict = str(item.get("verdict") or "").strip().lower()
        note = str(item.get("note") or "").strip()
        if verdict not in _ALLOWED:
            # An answer outside the three offered is not approval.
            verdict = NOT_FOUND
        absent = missing_figures(detail, document_text)
        if absent and verdict == AGREES:
            # The second reader agreed, but a figure the line stands on appears
            # nowhere in the document text. That is not an agreement.
            verdict = NOT_FOUND
            note = (note + " " if note else "") + (
                "Not confirmed: " + ", ".join(absent) + " could not be found in the document text."
            )
        findings.append(LimitationFinding(
            plan=plan_name, key=key, topic=topic, detail=detail, verdict=verdict,
            note=note, source_page=page, figures_missing=tuple(absent),
        ))

    missed: list[MissedLimitation] = []
    for item in (payload.get("possibly_missed") or [])[:MAX_MISSED]:
        if not isinstance(item, dict):
            continue
        quote = str(item.get("quote") or "").strip()
        # A clause nobody can point to in the document is not reported.
        if quote_in_document(quote, document_text):
            missed.append(MissedLimitation(
                plan=plan_name, topic=str(item.get("topic") or "").strip(), quote=quote,
            ))
    return LimitationAuditResult(findings=findings, missed=missed, ran=True, model=model)


def audit_case(*, results: list[dict], documents: dict[str, str],
               model: str = "", client=None) -> LimitationAuditResult:
    """Check every plan in the case. `documents` maps plan name to its text."""
    from .client_analysis import plan_display_name

    findings: list[LimitationFinding] = []
    missed: list[MissedLimitation] = []
    errors: list[str] = []
    ran_any = False
    for result in results or []:
        name = plan_display_name(result)
        outcome = audit_plan(
            plan_name=name,
            analysis=result.get("analysis") or {},
            document_text=documents.get(name, ""),
            model=model,
            client=client,
        )
        findings.extend(outcome.findings)
        missed.extend(outcome.missed)
        if outcome.ran:
            ran_any = True
        elif outcome.error:
            errors.append(outcome.error)

    # Every plan has to be checked. One plan that could not be read leaves the
    # case unchecked, because the unread plan is exactly where the error would
    # be hiding.
    return LimitationAuditResult(
        findings=findings,
        missed=missed,
        ran=ran_any and not errors,
        error=" ".join(errors),
        model=model or os.getenv("OPENAI_CHAT_MODEL", "gpt-4o"),
    )
