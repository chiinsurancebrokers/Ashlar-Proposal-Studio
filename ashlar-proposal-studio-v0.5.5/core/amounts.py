"""Locale-aware money parsing shared by every deterministic extractor.

Carrier documents mix two number conventions:

* English: ``1,500,000`` and ``6,840.91`` (comma = thousands, dot = decimal)
* Continental European (APRIL, Allianz, Henner, ...): ``1.500.000`` and
  ``6840,91`` / ``6.840,91`` (dot = thousands, comma = decimal)

Stripping every comma, as the extractors used to do, turned APRIL's
``€6840,91`` into ``684091``. The rule used here:

1. If both separators appear, the right-most one is the decimal separator.
2. If only one kind appears more than once, it is a thousands separator.
3. A single separator followed by exactly three digits is a thousands separator
   (``1,500`` / ``1.500``), unless the integer part is ``0`` (``0,500``).
4. Otherwise a single separator is the decimal separator (``6840,91``).
"""
from __future__ import annotations

import re

_TOKEN = re.compile(r"\d[\d.,]*")


def _normalised_token(raw) -> str | None:
    """First number in ``raw`` rewritten with no grouping and a dot decimal."""
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        return str(raw)
    text = str(raw).replace("\u00a0", "").replace("'", "").replace("\u2019", "")
    m = _TOKEN.search(text)
    if not m:
        return None
    s = m.group(0).rstrip(".,")
    if not s:
        return None

    has_comma, has_dot = "," in s, "." in s
    if has_comma and has_dot:
        dec = "," if s.rfind(",") > s.rfind(".") else "."
        thousands = "." if dec == "," else ","
        s = s.replace(thousands, "").replace(dec, ".")
    elif has_comma or has_dot:
        sep = "," if has_comma else "."
        whole, _, tail = s.rpartition(sep)
        if s.count(sep) > 1:
            s = s.replace(sep, "")
        elif len(tail) == 3 and whole.strip("0") != "":
            s = s.replace(sep, "")
        else:
            s = f"{whole}.{tail}"
    try:
        float(s)
    except ValueError:
        return None
    return s


def parse_amount(raw) -> float | None:
    """Return the first number in ``raw`` as a float, or ``None``."""
    token = _normalised_token(raw)
    return None if token is None else float(token)


def canonical_amount(raw) -> str:
    """Normalise an amount string to ``6840.91`` / ``1500000`` form.

    Decimal places are kept as written (``4,250.00`` -> ``4250.00``). Falls back
    to the stripped input when nothing numeric can be read, so a caller never
    loses the original text.
    """
    token = _normalised_token(raw)
    return str(raw or "").strip() if token is None else token


def annual_factor(frequency) -> int | None:
    """How many payments of this frequency make one year.

    Empty frequency is treated as annual (the extractors' default). An
    unrecognised frequency returns ``None`` so callers can skip comparisons
    rather than rank a monthly figure against an annual one.
    """
    key = str(frequency or "").strip().casefold()
    if not key:
        return 1
    if "semi" in key or "half" in key or "six-month" in key or "6-month" in key:
        return 2
    if "quarter" in key:
        return 4
    if "month" in key:
        return 12
    if "annual" in key or "year" in key or "annum" in key or key in {"pa", "p.a.", "yearly"}:
        return 1
    return None


def annual_premium(premium) -> tuple[str, float, float, int] | None:
    """``(currency, annual_total, quoted_amount, factor)`` for a premium dict."""
    if not isinstance(premium, dict):
        return None
    amount = parse_amount(premium.get("amount"))
    factor = annual_factor(premium.get("frequency"))
    if amount is None or factor is None:
        return None
    currency = str(premium.get("currency") or "").strip().upper()
    return currency, round(amount * factor, 2), amount, factor


def annual_premium_display(premium) -> str:
    """Comparable yearly figure, e.g. ``EUR 7,176.00 (598 × 12)`` for a monthly quote."""
    value = annual_premium(premium)
    if value is None:
        return "—"
    currency, total, amount, factor = value
    text = f"{currency} {total:,.2f}".strip()
    if factor > 1:
        quoted = f"{amount:,.0f}" if amount == int(amount) else f"{amount:,.2f}"
        text += f" ({quoted} × {factor})"
    return text
