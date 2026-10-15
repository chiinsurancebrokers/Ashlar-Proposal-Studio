"""What the broker is told when the model call fails.

The failure that prompted this file: the worker's Anthropic key was rejected
and Proposal Studio printed the provider's 401 body, complete with a request
id, into the adviser's screen. Everything needed to fix it -- which key, set
where -- was missing, and the one identifier present was addressed to a
support engineer rather than to the person who could change the setting.

These tests assert the sentence, not the formatting: that it names the
variable, that it does not leak the provider's internals, and that a caller
can tell a wrong setting apart from a bad minute.
"""
from __future__ import annotations

import httpx
import pytest

from core.model_errors import explain, is_configuration_error

anthropic = pytest.importorskip("anthropic")


def _status_error(cls, status: int, message: str):
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    response = httpx.Response(status, request=request)
    return cls(message, response=response, body={"error": {"message": message}})


def _auth_error():
    return _status_error(anthropic.AuthenticationError, 401, "invalid x-api-key")


# ---------------------------------------------------------------------------
# The one that actually happened
# ---------------------------------------------------------------------------

def test_a_rejected_key_names_the_variable_and_where_it_lives():
    message = explain(_auth_error(), subject="The client report")
    assert "ANTHROPIC_API_KEY" in message
    assert "Railway" in message
    # The detail that cost an evening: the key is set per service, so updating
    # it in one place fixes one service.
    assert "each service" in message


def test_the_providers_internals_do_not_reach_the_screen():
    """A request id is addressed to the wrong reader, and the raw body is
    noise to everyone looking at this application."""
    message = explain(_auth_error(), subject="The client report")
    for leak in ("request_id", "req_", "x-api-key", "{'type'", "authentication_error"):
        assert leak not in message, leak


def test_the_sentence_says_what_did_not_happen():
    assert explain(_auth_error(), subject="The client report").startswith("The client report")
    assert explain(_auth_error(), subject="The document analysis").startswith("The document analysis")


# ---------------------------------------------------------------------------
# The other ways a model call fails
# ---------------------------------------------------------------------------

def test_a_missing_model_names_the_model_and_the_settings_that_choose_it():
    exc = _status_error(anthropic.NotFoundError, 404, "model not found")
    message = explain(exc, model="claude-not-a-model", subject="The client report")
    assert "claude-not-a-model" in message
    assert "CLIENT_ANALYSIS_MODEL" in message


def test_a_key_without_access_points_at_the_workspace_not_the_key():
    exc = _status_error(anthropic.PermissionDeniedError, 403, "not permitted")
    message = explain(exc, subject="The client report")
    assert "workspace" in message
    assert "ANTHROPIC_API_KEY" not in message, "the key is valid here; sending them to it wastes their time"


def test_rate_limiting_asks_for_a_retry_rather_than_a_setting():
    exc = _status_error(anthropic.RateLimitError, 429, "slow down")
    message = explain(exc, subject="The client report")
    assert "Try again" in message
    assert "Railway" not in message


def test_an_unreachable_provider_is_not_reported_as_a_bad_key():
    exc = anthropic.APIConnectionError(request=httpx.Request("POST", "https://api.anthropic.com"))
    message = explain(exc, subject="The client report")
    assert "could not be reached" in message
    assert "ANTHROPIC_API_KEY" not in message


def test_an_unexpected_status_keeps_the_code_and_the_providers_message():
    exc = _status_error(anthropic.APIStatusError, 503, "upstream unavailable")
    message = explain(exc, subject="The client report")
    assert "503" in message and "upstream unavailable" in message
    assert "request_id" not in message


def test_something_that_is_not_a_provider_error_still_produces_a_sentence():
    assert "ValueError" in explain(ValueError("boom"), subject="The client report")


# ---------------------------------------------------------------------------
# Retry or not
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("exc", [
    _auth_error(),
    _status_error(anthropic.PermissionDeniedError, 403, "not permitted"),
    _status_error(anthropic.NotFoundError, 404, "model not found"),
])
def test_a_wrong_setting_is_not_worth_retrying(exc):
    assert is_configuration_error(exc) is True


@pytest.mark.parametrize("exc", [
    _status_error(anthropic.RateLimitError, 429, "slow down"),
    _status_error(anthropic.APIStatusError, 503, "upstream unavailable"),
])
def test_a_bad_minute_is_worth_retrying(exc):
    assert is_configuration_error(exc) is False


# ---------------------------------------------------------------------------
# The wiring: the surface that actually showed the 401
# ---------------------------------------------------------------------------

def _plan(provider, plan):
    return {"analysis": {
        "provider": provider, "plan_name": plan, "area_of_cover": "Europe",
        "annual_limit": "EUR 1,000,000",
        "premium": {"currency": "EUR", "amount": "6,841.27", "frequency": "per year"},
        "benefits": {"inpatient": "Paid in full", "outpatient": "Within EUR 5,000 combined"},
    }}


def test_the_studio_reports_a_rejected_key_in_words_the_broker_can_act_on(monkeypatch):
    """End to end through the real generation path, not the helper alone.

    Before this, the screen read: "Client decision synthesis failed: Error code:
    401 - {'type': 'error', 'error': {'type': 'authentication_error',
    'message': 'invalid x-api-key'}, 'request_id': 'req_011Cg4...'}".
    """
    from core import client_analysis
    from core.report_schema import ClientReportValidationError
    # client_analysis imports anthropic lazily inside the function, so the
    # patch goes on the module itself rather than on an attribute of the caller.

    class _Messages:
        def create(self, **kwargs):
            raise _auth_error()

    class _FakeClient:
        def __init__(self, **kwargs):
            self.messages = _Messages()

    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-whatever-this-is-rejected")
    monkeypatch.setattr(anthropic, "Anthropic", _FakeClient)

    with pytest.raises(ClientReportValidationError) as caught:
        client_analysis.generate_client_analysis(
            case_reference="ASH-TEST", client_name="Test", client_profile="",
            client_priorities="", results=[_plan("APRIL", "Essential"), _plan("Morgan Price", "Comprehensive")],
            strict=True,
        )

    message = str(caught.value)
    assert "ANTHROPIC_API_KEY" in message
    assert "each service" in message
    for leak in ("request_id", "req_", "401", "{'type'"):
        assert leak not in message, leak
