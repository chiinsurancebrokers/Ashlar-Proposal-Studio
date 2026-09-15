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
from typing import Any


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
