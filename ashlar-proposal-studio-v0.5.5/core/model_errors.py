"""Turn a model-provider exception into a sentence the reader can act on.

WHY
---
When the Anthropic key on the worker service was rejected, the broker saw
this in the Proposal Studio:

    Client decision synthesis failed: Error code: 401 - {'type': 'error',
    'error': {'type': 'authentication_error', 'message': 'invalid x-api-key'},
    'request_id': 'req_011Cg4K8h9PWh7t3kabic7iB'}

Everything needed to fix it is absent from that sentence: which key, set
where, and what to do. The request id is the only part addressed to a reader,
and it is addressed to the wrong one. HAL's chat had already solved this for
itself with a short list of `except` branches; this module is that list, in
one place, so every surface says the same thing.

The messages name the environment variable to check, because the person
reading is the person who can change it.
"""
from __future__ import annotations

try:  # the SDK is absent in some tooling environments
    import anthropic
except ImportError:  # pragma: no cover
    anthropic = None  # type: ignore[assignment]

# Where the key actually lives, which is the part that cost an evening: the
# variable is set per service, so rotating it in one place fixes one service.
KEY_HINT = (
    "Anthropic rejected the API key. Check ANTHROPIC_API_KEY in Railway — it is set "
    "separately on each service, so a rotated key has to be updated on every one of them."
)


def explain(exc: BaseException, *, model: str = "", subject: str = "The request") -> str:
    """One sentence saying what failed and what to do about it.

    `subject` names the thing that did not happen, so the sentence reads as a
    report rather than a stack trace: "The client report could not be
    generated: ...".
    """
    if anthropic is None:  # pragma: no cover
        return f"{subject} could not be completed: {type(exc).__name__}."

    if isinstance(exc, anthropic.AuthenticationError):
        return f"{subject} could not be generated. {KEY_HINT}"

    if isinstance(exc, anthropic.PermissionDeniedError):
        return (
            f"{subject} could not be generated: the API key is valid but is not permitted to "
            "use this model. Check the key's workspace in the Anthropic Console."
        )

    if isinstance(exc, anthropic.NotFoundError):
        named = f" '{model}'" if model else ""
        return (
            f"{subject} could not be generated: the configured model{named} is not available "
            "on this key. Check CLIENT_ANALYSIS_MODEL, ANALYSIS_MODEL and CLAUDE_MODEL in Railway."
        )

    if isinstance(exc, anthropic.RateLimitError):
        return f"{subject} was rate-limited by the model provider. Try again in a minute."

    if isinstance(exc, anthropic.APIConnectionError):
        return f"{subject} could not be generated: the model provider could not be reached."

    if isinstance(exc, anthropic.APIStatusError):
        # Status and the provider's own message, without the request id, which
        # means nothing to the person reading the screen.
        detail = ""
        try:
            body = exc.body if isinstance(exc.body, dict) else {}
            detail = str(((body.get("error") or {}).get("message")) or "").strip()
        except Exception:  # pragma: no cover - defensive only
            detail = ""
        tail = f": {detail}" if detail else ""
        return f"{subject} could not be generated: the model provider returned {exc.status_code}{tail}."

    if isinstance(exc, anthropic.APIError):
        return f"{subject} could not be generated: {exc}"

    return f"{subject} could not be completed: {type(exc).__name__}."


def is_configuration_error(exc: BaseException) -> bool:
    """True when a person has to change a setting, rather than retry.

    A caller that retries on failure should not retry these: the key or the
    model name is wrong and will still be wrong on the second attempt.
    """
    if anthropic is None:  # pragma: no cover
        return False
    return isinstance(
        exc,
        (anthropic.AuthenticationError, anthropic.PermissionDeniedError, anthropic.NotFoundError),
    )
