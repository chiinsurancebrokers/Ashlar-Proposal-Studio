"""The plan reader: an agent that reads a plan's documents and returns evidence-backed data.

What it does
------------
The broker attaches the documents for one plan (quote, table of benefits, policy wording). The model
reads them and fills a fixed form: premium, deductible, annual limit, area, a cell for each benefit and
the waiting-period rows. Every item carries a verbatim quote from the documents.

What it does not do
-------------------
It never writes a number that the study then trusts on its own say-so. ``verify`` checks each item
against the document text with plain string and number matching. An item whose quote is not in the
documents, or whose figure is not in its quote, is marked unverified and is left out of the study
until the broker approves it by hand. The study stays deterministic: it only ever receives data that
passed ``verify`` or that the broker approved.

A licensed broker reviews every reading before anything is placed.
"""
from __future__ import annotations

import os
import re
import unicodedata
from dataclasses import dataclass, field, replace
from typing import Any, Mapping, Sequence

from core import plan_quality, waiting_periods
from core.amounts import parse_amount
from core.family_bridge import BENEFITS, benefit_state
from core.json_utils import parse_first_json_object
from core.model_errors import explain as explain_model_error

VERIFIED, UNVERIFIED, MISSING = "verified", "unverified", "missing"
AREAS = tuple(plan_quality.AREA)
FREQUENCIES = ("monthly", "quarterly", "semiannual", "annual")

_AMOUNT = re.compile(r"\d[\d.,']*\d|\d")


# ---------------------------------------------------------------- data

@dataclass(frozen=True)
class Item:
    """One value read from the documents, with the sentence that backs it."""
    value: Any = None
    quote: str = ""
    source: str = ""                  # document name
    status: str = MISSING
    approved: bool = False            # broker override of an unverified item
    problem: str = ""

    @property
    def usable(self) -> bool:
        return self.value not in (None, "") and (self.status == VERIFIED or self.approved)


@dataclass(frozen=True)
class WaitingRow:
    condition_en: str
    condition_el: str
    period_en: str
    period_el: str
    quote: str = ""
    source: str = ""
    status: str = MISSING
    approved: bool = False
    problem: str = ""

    @property
    def usable(self) -> bool:
        return self.status == VERIFIED or self.approved


@dataclass(frozen=True)
class BenefitCell:
    key: str
    text_en: str                      # drives the state classification
    text_el: str = ""                 # shown to a Greek client
    quote: str = ""
    source: str = ""
    status: str = MISSING
    approved: bool = False
    problem: str = ""

    @property
    def usable(self) -> bool:
        return bool(self.text_en) and (self.status == VERIFIED or self.approved)


@dataclass(frozen=True)
class PlanReading:
    provider: str = ""
    plan_name: str = ""
    currency: str = "EUR"
    premium: Item = Item()
    frequency: str = ""
    premium_includes_tax: bool | None = None
    deductible: Item = Item()
    limit: Item = Item()
    area: Item = Item()               # one of AREAS
    benefits: tuple[BenefitCell, ...] = ()
    waiting: tuple[WaitingRow, ...] = ()
    extras: tuple[str, ...] = ()      # covers the benefit list has no slot for
    flags: tuple[str, ...] = ()       # things the broker should look at
    documents: tuple[str, ...] = ()

    @property
    def label(self) -> str:
        return f"{self.provider} {self.plan_name}".strip() or "Unnamed plan"

    def problems(self) -> list[str]:
        """Everything that is unverified or missing and not yet approved, in plain words."""
        out = list(self.flags)
        for name, item in (("premium", self.premium), ("deductible", self.deductible),
                           ("limit", self.limit), ("area", self.area)):
            if item.status == UNVERIFIED and not item.approved:
                out.append(f"{name}: {item.problem}")
            elif item.status == MISSING:
                out.append(f"{name}: not found in the documents")
        out += [f"{b.key}: {b.problem}" for b in self.benefits if b.status == UNVERIFIED and not b.approved]
        out += [f"waiting period “{w.condition_en}”: {w.problem}" for w in self.waiting
                if w.status == UNVERIFIED and not w.approved]
        return out


# ---------------------------------------------------------------- text matching

def _norm(text: str) -> str:
    """Casefolded, accent-free, single-spaced text, so a quote survives line breaks and PDF spacing."""
    text = unicodedata.normalize("NFD", str(text or ""))
    text = "".join(c for c in text if unicodedata.category(c) != "Mn").casefold()
    text = re.sub(r"[‘’“”\"'`´]", "", text)
    return re.sub(r"[\s \-–—]+", " ", text).strip()


def in_source(quote: str, source: str) -> bool:
    q = _norm(quote)
    return len(q) >= 8 and q in _norm(source)


def amounts_in(text: str) -> set[float]:
    out: set[float] = set()
    for token in _AMOUNT.findall(str(text or "")):
        value = parse_amount(token)
        if value is not None:
            out.add(round(float(value), 2))
    return out


def figure_in_quote(value, quote: str) -> bool:
    number = parse_amount(value)
    return number is not None and round(float(number), 2) in amounts_in(quote)


def _digits(text: str) -> set[str]:
    return set(re.findall(r"\d+", str(text or "")))


# ---------------------------------------------------------------- prompt

_SCHEMA = f"""Return ONE JSON object and nothing else:
{{
  "provider": "", "plan_name": "", "currency": "EUR",
  "premium": {{"amount": 0, "frequency": "monthly|quarterly|semiannual|annual", "includes_tax": true, "quote": "", "source": ""}},
  "deductible": {{"amount": 0, "quote": "", "source": ""}},
  "limit": {{"amount": 0, "quote": "", "source": ""}},
  "area": {{"value": "greece|eu|abroad|world", "quote": "", "source": ""}},
  "benefits": {{ "<key>": {{"en": "", "el": "", "quote": "", "source": ""}} }},
  "waiting": [{{"condition_en": "", "condition_el": "", "period_en": "", "period_el": "", "quote": "", "source": ""}}],
  "extras": ["covers worth telling the client that the benefit list has no key for"],
  "flags": ["anything unclear, contradictory between documents, or that needs the insurer to confirm"]
}}
Benefit keys: {", ".join(BENEFITS)}.
"""

_RULES = """You read insurance documents for a broker. Rules:
- Use only the documents below. Never use outside knowledge about the insurer or the plan.
- Every item needs "quote": a sentence copied EXACTLY, character for character, from the documents, and "source": the document name it is in. The quote must contain the figure you report.
- If a figure or benefit is not in the documents, leave it out. Do not estimate, round or infer.
- "en" is the cover as the document words it, in English: keep "up to", "limit", "not covered", "N/A" exactly where the document says so. "el" is the same in plain Greek.
- Waiting periods: one row per condition, period as the document words it ("3 months", "first insurance year", "30 days"), in English and Greek.
- If two documents disagree, report the one that is the policy wording and add a flag.
- The yearly limit is the annual overall or hospital limit, not a sub-limit.
"""


def build_prompt(docs: Mapping[str, str]) -> str:
    body = "\n\n".join(f"=== DOCUMENT: {name} ===\n{text}" for name, text in docs.items())
    return f"{_RULES}\n{_SCHEMA}\n{body}"


# ---------------------------------------------------------------- reading

def _item(raw: Any, docs: Mapping[str, str], *, kind: str, value_key: str = "amount") -> Item:
    if not isinstance(raw, Mapping) or raw.get(value_key) in (None, ""):
        return Item()
    value, quote = raw.get(value_key), str(raw.get("quote") or "")
    source_name = str(raw.get("source") or "")
    text = docs.get(source_name) if source_name in docs else "\n".join(docs.values())
    if not in_source(quote, text):
        return Item(value, quote, source_name, UNVERIFIED, problem="the quote is not in the documents")
    if kind == "amount":
        if parse_amount(value) is None:
            return Item(value, quote, source_name, UNVERIFIED, problem="not a readable amount")
        if not figure_in_quote(value, quote):
            return Item(value, quote, source_name, UNVERIFIED, problem=f"{value} is not in the quote")
        value = float(parse_amount(value))
    elif kind == "area" and str(value) not in AREAS:
        return Item(value, quote, source_name, UNVERIFIED, problem=f"unknown area {value!r}")
    return Item(value, quote, source_name, VERIFIED)


def verify(raw: Mapping[str, Any], docs: Mapping[str, str]) -> PlanReading:
    """The model's form, checked line by line against the documents. Nothing is trusted unseen."""
    premium_raw = raw.get("premium") if isinstance(raw.get("premium"), Mapping) else {}
    premium = _item(premium_raw, docs, kind="amount")
    frequency = str(premium_raw.get("frequency") or "").lower()
    flags = [str(f) for f in (raw.get("flags") or []) if str(f).strip()]
    if premium.value is not None and frequency not in FREQUENCIES:
        premium = replace(premium, status=UNVERIFIED, problem="payment frequency is missing or unknown")

    cells = []
    for key, cell in (raw.get("benefits") or {}).items():
        if key not in BENEFITS or not isinstance(cell, Mapping):
            continue
        en, quote = str(cell.get("en") or "").strip(), str(cell.get("quote") or "")
        name = str(cell.get("source") or "")
        text = docs.get(name) if name in docs else "\n".join(docs.values())
        status, problem = VERIFIED, ""
        if not en:
            continue
        if not in_source(quote, text):
            status, problem = UNVERIFIED, "the quote is not in the documents"
        elif not amounts_in(en) <= amounts_in(quote):
            status, problem = UNVERIFIED, "an amount in the summary is not in the quote"
        cells.append(BenefitCell(key, en, str(cell.get("el") or ""), quote, name, status, False, problem))

    rows = []
    for r in raw.get("waiting") or []:
        if not isinstance(r, Mapping) or not str(r.get("period_en") or "").strip():
            continue
        quote, name = str(r.get("quote") or ""), str(r.get("source") or "")
        text = docs.get(name) if name in docs else "\n".join(docs.values())
        status, problem = VERIFIED, ""
        try:
            plan_quality.months(str(r["period_en"]))
        except ValueError:
            status, problem = UNVERIFIED, "the period cannot be read as a length of time"
        if status == VERIFIED and not in_source(quote, text):
            status, problem = UNVERIFIED, "the quote is not in the documents"
        if status == VERIFIED and not (_digits(r["period_en"]) <= _digits(quote)):
            status, problem = UNVERIFIED, "the period's number is not in the quote"
        rows.append(WaitingRow(str(r.get("condition_en") or ""), str(r.get("condition_el") or ""),
                               str(r["period_en"]), str(r.get("period_el") or ""), quote, name, status, False, problem))

    return PlanReading(
        provider=str(raw.get("provider") or "").strip(), plan_name=str(raw.get("plan_name") or "").strip(),
        currency=str(raw.get("currency") or "EUR").upper(), premium=premium, frequency=frequency,
        premium_includes_tax=premium_raw.get("includes_tax") if isinstance(premium_raw.get("includes_tax"), bool) else None,
        deductible=_item(raw.get("deductible"), docs, kind="amount"),
        limit=_item(raw.get("limit"), docs, kind="amount"),
        area=_item(raw.get("area"), docs, kind="area", value_key="value"),
        benefits=tuple(cells), waiting=tuple(rows),
        extras=tuple(str(e) for e in (raw.get("extras") or []) if str(e).strip()),
        flags=tuple(flags), documents=tuple(docs))


def _model_name() -> str:
    return os.getenv("ANALYSIS_MODEL", "").strip() or os.getenv("CLAUDE_MODEL", "claude-haiku-4-5-20251001")


def read_plan(docs: Mapping[str, str], *, client=None, model: str | None = None) -> tuple[PlanReading | None, str]:
    """Read one plan's documents. Returns ``(reading, "")`` or ``(None, reason)``."""
    docs = {k: v for k, v in docs.items() if str(v or "").strip()}
    if not docs:
        return None, "No document text to read. Attach the quote or the table of benefits first."
    model = model or _model_name()
    try:
        if client is None:
            import anthropic
            client = anthropic.Anthropic()
        response = client.messages.create(model=model, max_tokens=16000,
                                          messages=[{"role": "user", "content": build_prompt(docs)}])
        raw_text = "".join(b.text for b in response.content if getattr(b, "type", None) == "text")
        raw = parse_first_json_object(raw_text)
    except Exception as exc:  # noqa: BLE001 - the reason is shown to the broker
        return None, explain_model_error(exc, model=model, subject="The plan reading")
    return verify(raw, docs), ""


# ---------------------------------------------------------------- hand-off to the study

def approve(reading: PlanReading, approved: Sequence[str]) -> PlanReading:
    """Mark the named items as approved by the broker: 'premium', 'deductible', 'limit', 'area',
    'benefit:<key>' or 'waiting:<n>'."""
    ok = set(approved)
    return replace(
        reading,
        premium=replace(reading.premium, approved="premium" in ok),
        deductible=replace(reading.deductible, approved="deductible" in ok),
        limit=replace(reading.limit, approved="limit" in ok),
        area=replace(reading.area, approved="area" in ok),
        benefits=tuple(replace(b, approved=f"benefit:{b.key}" in ok) for b in reading.benefits),
        waiting=tuple(replace(w, approved=f"waiting:{i}" in ok) for i, w in enumerate(reading.waiting)))


def to_result(reading: PlanReading) -> dict:
    """A result row in the shape the Case Studio produces, holding only usable items.

    The premium is left out when it is not usable, so the plan cannot be priced and the bridge says so.
    """
    analysis: dict[str, Any] = {"provider": reading.provider, "plan_name": reading.plan_name,
                                "benefits": {}, "benefit_display": {}}
    if reading.premium.usable:
        analysis["premium"] = {"amount": reading.premium.value, "currency": reading.currency,
                               "frequency": reading.frequency}
    for cell in reading.benefits:
        if cell.usable:
            analysis["benefits"][cell.key] = cell.text_en
            if cell.text_el:
                analysis["benefit_display"][cell.key] = cell.text_el
    return {"provider": reading.provider, "target_plan": reading.plan_name, "analysis": analysis}


def to_quality(reading: PlanReading, *, key: str, network: int | None = None,
               exclusions: int | None = None) -> plan_quality.PlanQuality:
    """The merit facts for a plan. Waiting rows become a run-time table; network and exclusions stay the
    broker's own ratings and are never filled in by the reader."""
    usable = [w for w in reading.waiting if w.usable]
    tables = None
    if usable:
        tables = (waiting_periods.register_table(
            f"read_{key}",
            {"en": f"{reading.label} (waiting periods)", "el": f"{reading.label} (περίοδοι αναμονής)"},
            {"en": "These conditions are covered only after the period shown.",
             "el": "Οι παρακάτω παθήσεις καλύπτονται μόνο μετά το διάστημα που αναγράφεται."},
            [(w.condition_en, w.condition_el or w.condition_en, w.period_en, w.period_el or w.period_en)
             for w in usable]),)
    notes = {n: i.source for n, i in (("limit", reading.limit), ("deductible", reading.deductible),
                                       ("area", reading.area)) if i.usable and i.source}
    return plan_quality.PlanQuality(
        limit=float(reading.limit.value) if reading.limit.usable else None,
        deductible=float(reading.deductible.value) if reading.deductible.usable else None,
        waiting_tables=tables, area=str(reading.area.value) if reading.area.usable else None,
        network=network, exclusions=exclusions, notes=notes)


def text_from_upload(name: str, data: bytes) -> str:
    """Plain text of an uploaded PDF or text file. A scanned PDF with no text layer returns ''."""
    if name.lower().endswith(".pdf"):
        import fitz
        with fitz.open(stream=data, filetype="pdf") as doc:
            return "\n".join(page.get_text() for page in doc)
    return data.decode("utf-8", errors="replace")
