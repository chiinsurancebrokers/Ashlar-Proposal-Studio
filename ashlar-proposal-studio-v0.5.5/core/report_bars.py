"""Bar widths for the comparison table: yearly premium and out-patient amount.

Both read what the extraction already holds. Nothing is typed in here. A bar is
drawn only when a plan has a figure that can be compared with the others; a
plan with no usable figure simply has no bar, never a zero-length one.
"""
from __future__ import annotations

import re

from core.amounts import annual_premium, parse_amount

_AMT = re.compile(
    r"(?:€|EUR|USD|US\$|\$|£|GBP)\s*(?P<a>\d[\d.,]*)|(?P<b>\d[\d.,]*)\s*(?:EUR|USD|GBP|€|\$|£)",
    re.I,
)
PREMIUM_TOPIC = "premium"
OUTPATIENT_TOPIC = "out-patient treatment"


def _pct(value: float, top: float) -> int:
    return max(4, min(100, round(value / top * 100))) if top > 0 else 0


def premium_bars(results: list[dict], names: list[str]) -> dict[str, dict]:
    """name -> {pct, annual, currency}, only for plans whose premium can be made yearly."""
    found = {}
    for name, result in zip(names, results):
        prem = annual_premium((result.get("analysis") or {}).get("premium"))
        if prem and prem[1] > 0:
            found[name] = {"annual": prem[1], "currency": prem[0] or "EUR", "factor": prem[3]}
    # Different currencies cannot share a scale.
    if len({v["currency"] for v in found.values()}) > 1 or len(found) < 2:
        return {}
    top = max(v["annual"] for v in found.values())
    return {n: {**v, "pct": _pct(v["annual"], top)} for n, v in found.items()}


def outpatient_bars(values: dict, states: dict) -> dict[str, dict]:
    """name -> {pct, amount}, for plans whose out-patient text states exactly one amount."""
    found = {}
    for name, raw in (values or {}).items():
        text = re.sub(r"\s+", " ", str(raw or ""))
        if (states.get(name) or "") == "not_covered":
            continue
        amounts = [m.group("a") or m.group("b") for m in _AMT.finditer(text)]
        if len(amounts) != 1:
            continue
        amount = parse_amount(amounts[0])
        if amount and amount > 0:
            found[name] = amount
    if len(found) < 2:
        return {}
    top = max(found.values())
    return {n: {"amount": a, "pct": _pct(a, top)} for n, a in found.items()}
