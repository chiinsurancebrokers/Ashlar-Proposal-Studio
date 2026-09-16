"""Robust helpers for parsing JSON returned by LLMs.

LLMs occasionally wrap otherwise-valid JSON in markdown, add a short preamble,
or append a second object / explanatory sentence. ``json.loads`` rejects all of
those with ``JSONDecodeError: Extra data``.  Proposal Studio only needs the
first complete JSON object, so this module decodes exactly that object and
ignores harmless trailing text.
"""
from __future__ import annotations

import json
import re
from typing import Any, Iterable


_FENCE_RE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$", re.IGNORECASE)


def parse_first_json_object(raw: str) -> dict[str, Any]:
    """Return the first complete JSON object found in *raw*.

    Handles:
    - ```json fenced output
    - a short prose preamble before the JSON
    - trailing prose after a valid JSON object
    - multiple JSON objects accidentally emitted back-to-back

    Raises ``json.JSONDecodeError`` when no complete JSON object can be found.
    """
    if raw is None:
        raise json.JSONDecodeError("Empty model response", "", 0)

    text = str(raw).strip()
    if not text:
        raise json.JSONDecodeError("Empty model response", text, 0)

    # Remove only outer markdown fences. Internal backticks are left untouched.
    text = _FENCE_RE.sub("", text).strip()

    decoder = json.JSONDecoder()
    last_error: json.JSONDecodeError | None = None

    # Try every object opener. This is safer than slicing first/last braces,
    # because braces may also occur in trailing prose or in a second object.
    for match in re.finditer(r"\{", text):
        start = match.start()
        try:
            value, _end = decoder.raw_decode(text, idx=start)
        except json.JSONDecodeError as exc:
            last_error = exc
            continue
        if isinstance(value, dict):
            return value

    if last_error is not None:
        raise last_error
    raise json.JSONDecodeError("No JSON object found in model response", text, 0)


def parse_json_objects(raw: str) -> list[dict[str, Any]]:
    """Return every complete top-level-ish JSON object that can be decoded from *raw*.

    This is intentionally tolerant of prose, markdown fences and multiple objects.
    Duplicate objects (same start position / content) are collapsed.
    """
    if raw is None:
        return []
    text = str(raw).strip()
    if not text:
        return []
    text = _FENCE_RE.sub("", text).strip()
    decoder = json.JSONDecoder()
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for match in re.finditer(r"\{", text):
        try:
            value, _end = decoder.raw_decode(text, idx=match.start())
        except json.JSONDecodeError:
            continue
        if not isinstance(value, dict):
            continue
        try:
            key = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
        except Exception:
            key = repr(value)
        if key in seen:
            continue
        seen.add(key)
        out.append(value)
    return out


def parse_best_json_object(raw: str, *, required_keys: Iterable[str] = ()) -> dict[str, Any]:
    """Return the decoded object most likely to be the requested schema.

    LLMs sometimes emit a small example/input object before the actual report.
    The legacy parser returned the first valid object, which could therefore select
    the wrong object.  This helper scores every decoded object by required-key
    coverage and by structural richness.
    """
    candidates = parse_json_objects(raw)
    if not candidates:
        # Preserve the legacy JSONDecodeError behaviour/message.
        return parse_first_json_object(raw)

    required = tuple(str(k) for k in required_keys)

    def score(obj: dict[str, Any]) -> tuple[int, int, int]:
        key_hits = sum(1 for k in required if k in obj)
        nonempty_hits = sum(1 for k in required if obj.get(k) not in (None, "", [], {}))
        richness = len(obj)
        return (key_hits, nonempty_hits, richness)

    return max(candidates, key=score)
