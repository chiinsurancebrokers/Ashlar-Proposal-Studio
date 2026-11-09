"""Broker-only wording that must not reach a client document.

The analysis writes some lines for the broker ("check the governing figure",
"Unclear", "Not specified", "No policy wording was supplied"). Those are working
notes. In a client report they read as the adviser not knowing, and a client
cannot act on them. This module finds them before the report is generated, so
the broker resolves them or rewrites them, rather than discovering them in the
PDF. It reports; it never edits.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# Phrases that address the broker, or admit a gap, rather than tell the client
# something. Matched case-insensitively against benefit and limitation text.
BROKER_ONLY_PATTERNS = (
    r"\bcheck the governing\b",
    r"\bverify in the\b",
    r"\bplease verify\b",
    r"\bto be verified\b",
    r"\bno policy wording was supplied\b",
    r"\btable extraction\b",
    r"\bsymbols? (?:in|for|conflict)\b",
    r"\blikely ['\"]?not covered\b",
    r"^\s*unclear\b",
    r"^\s*not specified\b",
    r"\bnot specified in the quote\b",
)
_COMPILED = [re.compile(p, re.IGNORECASE | re.MULTILINE) for p in BROKER_ONLY_PATTERNS]


@dataclass(frozen=True)
class Leak:
    plan: str
    field: str
    phrase: str


def _plan_name(result: dict) -> str:
    analysis = result.get("analysis") or {}
    return str(analysis.get("plan_name") or result.get("target_plan") or result.get("label") or "plan")


def find_broker_leaks(results: list[dict]) -> list[Leak]:
    """Broker-only phrases inside each plan's benefit lines and limitations."""
    leaks: list[Leak] = []
    for result in results or []:
        analysis = result.get("analysis") or {}
        name = _plan_name(result)
        texts: list[tuple[str, str]] = []
        for key, value in (analysis.get("benefits") or {}).items():
            texts.append((f"benefit:{key}", str(value or "")))
        for item in analysis.get("critical_limitations") or []:
            if isinstance(item, dict):
                texts.append((f"limitation:{item.get('topic') or ''}", str(item.get("detail") or "")))
            else:
                texts.append(("limitation", str(item or "")))
        for field, text in texts:
            for pattern in _COMPILED:
                match = pattern.search(text)
                if match:
                    leaks.append(Leak(plan=name, field=field, phrase=match.group(0).strip()))
                    break
    return leaks
