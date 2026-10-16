"""The second reader, and the one property that makes it worth having.

A client pack went out saying a plan covered no maternity, no dental, no
optical and no cancer. The extraction was right; the document built from it
was wrong, and nothing between the two was positioned to notice, because the
same reasoning that wrote the line also judged it.

These tests are mostly about the failure modes. A check that quietly passes
when it did not run is worse than no check, because the tick box next to it
is believed.
"""
from __future__ import annotations

import json

import pytest

from core.benefit_audit import (
    AGREES, DISAGREES, NOT_FOUND, AuditResult, audit_case, audit_plan,
)

ORDER = [("dental", "Dental"), ("cancer", "Cancer / oncology"), ("maternity", "Maternity")]

ANALYSIS = {"benefits": {
    "dental": "Included. Annual limit EUR 1,000, 80% after 3 months. Orthodontics are not covered.",
    "cancer": "Included at 100% as an inpatient, day-patient or outpatient.",
    "maternity": "Included. Routine pregnancy and childbirth EUR 4,000 after 12 months.",
}}
DOCUMENT = "Dental: EUR 1,000 a year at 80%. Cancer: paid in full. Maternity: EUR 4,000 after 12 months."


class _Stub:
    """Stands in for the second reader."""

    def __init__(self, payload=None, raises=None):
        self._payload, self._raises = payload, raises
        self.prompts: list[str] = []
        self.chat = self

    @property
    def completions(self):
        return self

    def create(self, **kwargs):
        self.prompts.append(kwargs["messages"][0]["content"])
        if self._raises:
            raise self._raises
        body = json.dumps(self._payload)
        return type("R", (), {"choices": [type("C", (), {
            "message": type("M", (), {"content": body})()})()]})()


def _findings(**verdicts):
    return {"findings": [{"key": k, "verdict": v, "note": ""} for k, v in verdicts.items()]}


def _run(client, analysis=ANALYSIS, document=DOCUMENT):
    return audit_plan(plan_name="APRIL - Essential", analysis=analysis,
                      document_text=document, benefit_order=ORDER, model="test", client=client)


# ---------------------------------------------------------------------------
# It must not pass quietly
# ---------------------------------------------------------------------------

def test_a_check_that_did_not_run_is_not_a_clean_check():
    """The distinction the gate depends on. Silence is not agreement."""
    out = AuditResult(ran=False, error="no key")
    assert out.is_clean is False
    assert out.ran is False


def test_an_unreachable_checker_reports_rather_than_approving():
    out = _run(_Stub(raises=RuntimeError("OPENAI_API_KEY is not set in Railway.")))
    assert out.ran is False
    assert out.is_clean is False
    assert "OPENAI_API_KEY" in out.error


def test_a_malformed_answer_is_a_failure_not_an_approval():
    class _Bad(_Stub):
        def create(self, **kwargs):
            return type("R", (), {"choices": [type("C", (), {
                "message": type("M", (), {"content": "not json at all"})()})()]})()

    out = _run(_Bad())
    assert out.ran is False
    assert out.is_clean is False


def test_a_plan_with_no_stored_document_cannot_be_checked():
    out = _run(_Stub(_findings(dental=AGREES)), document="")
    assert out.ran is False
    assert "could not be checked" in out.error


def test_a_verdict_outside_the_three_offered_is_not_read_as_approval():
    """An inventive answer must not be able to open the gate."""
    out = _run(_Stub({"findings": [{"key": "dental", "verdict": "looks fine to me"}]}))
    assert out.ran is True
    assert {f.verdict for f in out.findings} == {NOT_FOUND}
    assert out.is_clean is True  # nothing is disputed, but nothing is confirmed either
    assert len(out.unverified) == 3


def test_a_benefit_the_checker_ignored_stays_unverified():
    out = _run(_Stub(_findings(dental=AGREES)))
    verdicts = {f.benefit_key: f.verdict for f in out.findings}
    assert verdicts == {"dental": AGREES, "cancer": NOT_FOUND, "maternity": NOT_FOUND}


# ---------------------------------------------------------------------------
# What it reports when it does run
# ---------------------------------------------------------------------------

def test_agreement_on_every_line_is_clean():
    out = _run(_Stub(_findings(dental=AGREES, cancer=AGREES, maternity=AGREES)))
    assert out.ran is True and out.is_clean is True
    assert out.disagreements == []
    assert all(f.needs_attention is False for f in out.findings)


def test_one_disagreement_stops_the_case_being_clean():
    out = _run(_Stub({"findings": [
        {"key": "dental", "verdict": DISAGREES, "note": "The table of benefits shows EUR 750, not EUR 1,000."},
        {"key": "cancer", "verdict": AGREES},
        {"key": "maternity", "verdict": AGREES},
    ]}))
    assert out.is_clean is False
    assert len(out.disagreements) == 1
    # The document's own words travel with the finding, so the broker can act.
    assert "EUR 750" in out.disagreements[0].note
    assert out.disagreements[0].extracted.startswith("Included.")


def test_the_checker_is_shown_the_document_and_the_lines():
    stub = _Stub(_findings(dental=AGREES))
    _run(stub)
    prompt = stub.prompts[0]
    assert "Dental: EUR 1,000 a year at 80%" in prompt
    assert "Orthodontics are not covered" in prompt
    assert "APRIL - Essential" in prompt


def test_the_audit_never_rewrites_a_benefit():
    """It reports; the broker decides. A checker that edits the line is just
    a second author, and the disagreement disappears."""
    out = _run(_Stub({"findings": [
        {"key": "dental", "verdict": DISAGREES, "note": "EUR 750"},
    ]}))
    assert out.findings[0].extracted == ANALYSIS["benefits"]["dental"]


# ---------------------------------------------------------------------------
# A case is every plan, or it is not checked
# ---------------------------------------------------------------------------

def _plan(provider, plan, benefits):
    return {"analysis": {"provider": provider, "plan_name": plan, "benefits": benefits}}


def test_one_unreadable_plan_leaves_the_whole_case_unchecked():
    """The unread plan is exactly where the error would be hiding."""
    results = [
        _plan("APRIL", "Essential", ANALYSIS["benefits"]),
        _plan("Bupa Global", "Select", ANALYSIS["benefits"]),
    ]
    out = audit_case(
        results=results,
        documents={"APRIL - Essential": DOCUMENT},  # Bupa has no stored text
        benefit_order=ORDER, model="test",
        client=_Stub(_findings(dental=AGREES, cancer=AGREES, maternity=AGREES)),
    )
    assert out.ran is False
    assert out.is_clean is False
    assert "Bupa Global - Select" in out.error


def test_a_case_with_every_plan_read_can_be_clean():
    results = [_plan("APRIL", "Essential", ANALYSIS["benefits"])]
    out = audit_case(
        results=results, documents={"APRIL - Essential": DOCUMENT},
        benefit_order=ORDER, model="test",
        client=_Stub(_findings(dental=AGREES, cancer=AGREES, maternity=AGREES)),
    )
    assert out.ran is True and out.is_clean is True


# ---------------------------------------------------------------------------
# The gate itself
# ---------------------------------------------------------------------------

def test_the_generate_button_is_locked_behind_the_check():
    """Chris's requirement, asserted against the app rather than trusted.

    The documents are generated only after a second opinion has run and the
    broker has ticked to say they read it.
    """
    import pathlib, re
    app = pathlib.Path(__file__).resolve().parents[1].joinpath("app.py").read_text(encoding="utf-8")

    # The gate is computed before the button and feeds its disabled state.
    # It needs the benefit-line check AND the limitations check: both sections
    # are rendered, then both have to be confirmed.
    assert "benefits_confirmed = _render_benefit_second_opinion(results)" in app
    assert "limitations_confirmed = _render_limitation_second_opinion(results)" in app
    assert "audit_confirmed = benefits_confirmed and limitations_confirmed" in app
    # Anchored on the button itself: the file has several disabled= expressions
    # and matching the wrong one would make this test pass for free.
    button = app.index("\"Generate Client Analysis")
    disabled = re.search(r"disabled=\(\s*(.*?)\s*\),", app[button:], re.S)
    assert disabled, "the generate button has no disabled expression"
    assert "not audit_confirmed" in disabled.group(1)
    assert "not reviewed" in disabled.group(1)


def test_the_section_refuses_to_confirm_before_it_has_run():
    """Reading the function rather than driving Streamlit: every path that
    has not got a completed audit returns False."""
    import inspect, pathlib, re
    app = pathlib.Path(__file__).resolve().parents[1].joinpath("app.py").read_text(encoding="utf-8")
    start = app.index("def _render_benefit_second_opinion")
    body = app[start:app.index("\ndef render_client_deliverable")]
    # Not run yet, and could-not-run, both return False before any checkbox.
    assert body.index("if audit is None:") < body.index("st.checkbox")
    assert body.index("if not audit.ran:") < body.index("st.checkbox")
    assert body.count("return False") >= 2


def test_the_limitations_section_refuses_to_confirm_before_it_has_run():
    """Same guarantee for the limitations check: no completed audit, no tick box,
    and the section hands back False so the gate stays shut."""
    import pathlib
    app = pathlib.Path(__file__).resolve().parents[1].joinpath("app.py").read_text(encoding="utf-8")
    start = app.index("def _render_limitation_second_opinion")
    body = app[start:app.index("\ndef render_client_deliverable")]
    assert body.index("if audit is None:") < body.index("st.checkbox")
    assert body.index("if not audit.ran:") < body.index("st.checkbox")
    assert body.count("return False") >= 2


def test_both_checks_must_pass_and_both_always_render():
    """The gate is an AND of two sections that are each rendered unconditionally,
    so a broker can never be shown only one of them (short-circuiting would hide
    the second section whenever the first is unconfirmed)."""
    import pathlib
    app = pathlib.Path(__file__).resolve().parents[1].joinpath("app.py").read_text(encoding="utf-8")
    first = app.index("benefits_confirmed = _render_benefit_second_opinion(results)")
    second = app.index("limitations_confirmed = _render_limitation_second_opinion(results)")
    gate = app.index("audit_confirmed = benefits_confirmed and limitations_confirmed")
    assert first < second < gate
