"""Fit long plan documents into the model's budget without losing the benefit table.

Plain truncation kept only the first pages of each document. A membership guide
puts its Table of Benefits around page 10, so a 70,000-character cut sent the
model the introduction and none of the limits. Here every page is scored for
benefit content and the best pages are kept, in their original order.
"""
from __future__ import annotations

import re

_MARKER = re.compile(r"(?=^--- (?:PAGE \d+|LIBRARY DOCUMENT: [^\n]*|DOCUMENT: [^\n]*) ---)", re.M)
_DOC_HEADER = re.compile(r"^--- (?:LIBRARY DOCUMENT|DOCUMENT): ")

_SIGNALS = (
    (r"table of benefits|benefit and explanation|benefits schedule|schedule of benefits", 25),
    (r"paid in full", 6),
    (r"not covered|excluded|exclusion", 3),
    (r"waiting period", 4),
    (r"pre-?authori[sz]ation|pre-?approval|prior approval", 4),
    (r"co-?payment|co-?insurance|deductible|excess", 3),
    (r"(?:annual|overall|policy) (?:maximum|limit)|up to|per (?:policy |insurance )?year|per pregnancy|lifetime", 3),
    (r"(?:€|eur|usd|us\$|\$|£|gbp)\s?\d", 2),
    (r"\b\d{1,3}\s?%", 2),
)


def _score(chunk: str) -> float:
    low = chunk.casefold()
    hits = sum(weight * len(re.findall(pattern, low)) for pattern, weight in _SIGNALS)
    return hits * 1000 / max(len(chunk), 400)


def benefit_focused_excerpt(text: str, cap: int) -> str:
    """Return ``text`` if it fits; otherwise the highest-signal pages within ``cap``."""
    text = text or ""
    if len(text) <= cap:
        return text
    chunks = [c for c in _MARKER.split(text) if c]
    if len(chunks) < 3:
        return text[:cap]

    keep: set[int] = set()
    used = 0
    # Always keep document headers and each document's first page (title, plan name).
    for i, chunk in enumerate(chunks):
        if _DOC_HEADER.match(chunk) or (i > 0 and _DOC_HEADER.match(chunks[i - 1])) or i == 0:
            if used + len(chunk) <= cap:
                keep.add(i)
                used += len(chunk)
    ranked = sorted((i for i in range(len(chunks)) if i not in keep), key=lambda i: -_score(chunks[i]))
    for i in ranked:
        if used + len(chunks[i]) <= cap:
            keep.add(i)
            used += len(chunks[i])

    out, gap = [], False
    for i, chunk in enumerate(chunks):
        if i in keep:
            if gap:
                out.append("[… pages with less benefit detail omitted …]\n")
            out.append(chunk)
            gap = False
        else:
            gap = True
    return "".join(out)[:cap]
