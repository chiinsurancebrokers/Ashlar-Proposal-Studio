"""What a year costs the family when it claims: the premium plus the deductible.

A low premium with a large deductible can cost more, in a year with a claim, than
a higher premium with a small one. The comparison table shows both figures but
leaves the addition to the reader. This module does the addition from facts the
analysis already holds, and says plainly when it cannot.

Rules, so the page never claims more than the quotes say:

* The total is the yearly premium plus ONE deductible: the plan's main
  (in-patient) deductible. It is the cost of a year in which one insured person
  has one claim. It is not a worst case.
* A separate out-patient deductible is shown as an addition, never merged in.
* A per-person deductible with a stated family maximum gets a second figure for
  a year in which several members claim. Without a stated maximum there is no
  second figure.
* If the premium and the deductible are in different currencies, or either is
  missing or cannot be read as one amount, there is no total. The parts that
  could be read are still shown.
"""
from __future__ import annotations

import re

from core.amounts import annual_premium, parse_amount

_MONEY = r"(?:€|EUR|USD|US\$|\$|£|GBP)"
_NUMBER = r"\d[\d.,]*"
_AMOUNT = re.compile(rf"(?P<pre>{_MONEY})\s*(?P<a>{_NUMBER})|(?P<b>{_NUMBER})\s*(?P<post>EUR|USD|GBP|€|\$|£)", re.I)
_NO_DEDUCTIBLE = re.compile(r"\b(?:no|nil|zero|without)\b[^.;]{0,40}\b(?:deductible|excess)\b|\b(?:deductible|excess)\b[^.;]{0,20}\b(?:nil|zero|none|n/a)\b", re.I)
_OUTPATIENT = re.compile(
    rf"out[\s-]?patient\s+(?:annual\s+)?(?:deductible|excess)\s*(?:of|:)?\s*(?P<amt>{_MONEY}\s*{_NUMBER}|{_NUMBER}\s*{_MONEY})"
    rf"|(?P<amt2>{_MONEY}\s*{_NUMBER}|{_NUMBER}\s*{_MONEY})\s+out[\s-]?patient\s+(?:deductible|excess)",
    re.I,
)
_WORDS = {"two": 2, "three": 3, "four": 4, "five": 5, "2": 2, "3": 3, "4": 4, "5": 5}
_FAMILY_MAX = re.compile(r"(?:max(?:imum)?\s+(?:of\s+)?|up\s+to\s+)(two|three|four|five|[2-5])\s+deductibles?", re.I)
_CURRENCY = {"€": "EUR", "EUR": "EUR", "$": "USD", "US$": "USD", "USD": "USD", "£": "GBP", "GBP": "GBP"}


def _cur(token: str) -> str:
    return _CURRENCY.get(str(token or "").strip().upper().replace("US$", "US$"), "")


def _amount_and_currency(text: str) -> tuple[float | None, str]:
    m = _AMOUNT.search(text or "")
    if not m:
        return None, ""
    number = m.group("a") or m.group("b")
    currency = _cur(m.group("pre") or m.group("post"))
    return parse_amount(number), currency


def parse_deductible(value) -> dict:
    """Read a ``deductible_or_excess`` string into numbers.

    Returns ``main`` (the in-patient deductible, or ``None`` when no single
    amount can be read), ``currency``, ``outpatient`` (a separate out-patient
    deductible or ``None``), ``per_person`` and ``family_max``.
    """
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    out = {"main": None, "currency": "", "outpatient": None, "per_person": None, "family_max": None}
    if not text or text.casefold() in {"not specified", "—", "-", "n/a"}:
        return out

    rest = text
    op = _OUTPATIENT.search(text)
    if op:
        amt, _ = _amount_and_currency(op.group("amt") or op.group("amt2"))
        out["outpatient"] = amt
        rest = (text[: op.start()] + " " + text[op.end():]).strip()

    amount, currency = _amount_and_currency(rest)
    # "Choice of €500, €1,000 or €2,500": the plan has not been settled on one deductible,
    # so adding the first figure to the premium would invent a total.
    if len(_AMOUNT.findall(rest)) > 1 and re.search(r"\b(?:choice|options?|or|either|select(?:ed)?)\b", rest, re.I) and not _FAMILY_MAX.search(rest):
        amount = None
    if amount is not None:
        out["main"], out["currency"] = amount, currency
    elif _NO_DEDUCTIBLE.search(rest):
        out["main"] = 0.0

    if re.search(r"per\s+(?:insured\s+)?(?:person|member)|each\s+(?:insured\s+)?(?:person|member)", rest, re.I):
        out["per_person"] = True
    elif re.search(r"per\s+family|family\s+(?:deductible|excess)|per\s+policy\b", rest, re.I):
        out["per_person"] = False
    fm = _FAMILY_MAX.search(rest)
    if fm:
        out["family_max"] = _WORDS.get(fm.group(1).casefold())
    return out


def claim_cost_rows(results: list[dict]) -> list[dict]:
    """One row per option, in the order given, with whatever can be computed."""
    rows = []
    for result in results or []:
        a = result.get("analysis") or {}
        name = " ".join(str(x).strip() for x in (a.get("provider") or result.get("provider"), a.get("plan_name") or result.get("target_plan")) if x).strip()
        prem = annual_premium(a.get("premium"))
        ded = parse_deductible(a.get("deductible_or_excess"))
        row = {
            "name": name or "—",
            "currency": prem[0] if prem else "",
            "premium": prem[1] if prem else None,
            "deductible": ded["main"],
            "outpatient": ded["outpatient"],
            "per_person": ded["per_person"],
            "total": None, "total_with_outpatient": None, "total_family_max": None,
        }
        same_currency = prem and ded["main"] is not None and (not ded["currency"] or not prem[0] or ded["currency"] == prem[0])
        if same_currency:
            row["total"] = round(prem[1] + ded["main"], 2)
            if ded["outpatient"]:
                row["total_with_outpatient"] = round(row["total"] + ded["outpatient"], 2)
            if ded["per_person"] and ded["family_max"] and ded["family_max"] > 1:
                row["total_family_max"] = round(prem[1] + ded["main"] * ded["family_max"], 2)
        rows.append(row)
    return rows


def has_claim_costs(rows: list[dict]) -> bool:
    return sum(1 for r in rows if r["total"] is not None) >= 2


def money(amount: float | None, currency: str = "EUR") -> str:
    if amount is None:
        return "—"
    sym = {"EUR": "€", "USD": "$", "GBP": "£"}.get(currency, f"{currency} " if currency else "")
    return f"{sym}{amount:,.2f}"


def ranking_note(rows: list[dict]) -> dict | None:
    """Which plan is cheapest on premium alone, and which once the deductible is added."""
    usable = [r for r in rows if r["total"] is not None and r["premium"] is not None]
    if len(usable) < 2:
        return None
    by_premium = min(usable, key=lambda r: r["premium"])
    by_total = min(usable, key=lambda r: r["total"])
    return {"by_premium": by_premium["name"], "by_total": by_total["name"],
            "changed": by_premium["name"] != by_total["name"],
            "total": by_total["total"], "currency": by_total["currency"]}


def claim_cost_view(results: list[dict], lab: dict) -> dict | None:
    """Everything a renderer needs, already in words, or ``None`` when the section has no value.

    Both the HTML and the PDF read this, so the two documents cannot disagree.
    """
    rows = claim_cost_rows(results)
    if not has_claim_costs(rows):
        return None
    top = max((r["total_with_outpatient"] or r["total"]) for r in rows if r["total"] is not None) or 1
    view_rows = []
    for r in rows:
        cur = r["currency"] or "EUR"
        notes = []
        if r["total"] is None:
            notes.append(lab["cost_unknown"])
        if r["total_with_outpatient"] is not None:
            notes.append(lab["cost_outpatient"].format(x=money(r["outpatient"], cur), t=money(r["total_with_outpatient"], cur)))
        if r["total_family_max"] is not None:
            n = round((r["total_family_max"] - r["premium"]) / r["deductible"])
            notes.append(lab["cost_family"].format(t=money(r["total_family_max"], cur), n=n))
        view_rows.append({
            "name": r["name"],
            "premium": money(r["premium"], cur) if r["premium"] is not None else "—",
            "deductible": ("+ " + money(r["deductible"], cur)) if r["deductible"] is not None else "—",
            "total": money(r["total"], cur) if r["total"] is not None else "—",
            "note": " ".join(notes),
            "w_prem": round((r["premium"] or 0) / top * 100, 1),
            "w_ded": round((r["deductible"] or 0) / top * 100, 1),
        })
    rank = ranking_note(rows)
    sentence = ""
    if rank:
        total = money(rank["total"], rank["currency"] or "EUR")
        key = "cost_rank_changed" if rank["changed"] else "cost_rank_same"
        sentence = lab[key].format(a=rank["by_premium"], b=rank["by_total"], t=total)
    return {"rows": view_rows, "ranking": sentence}
