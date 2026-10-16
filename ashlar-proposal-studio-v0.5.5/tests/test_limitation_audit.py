"""The second reader for coverage-limiting clauses.

The limitations are the lines a client misses, so a check on them is only worth
having if it cannot pass quietly. These tests are mostly about the failure
modes: a check that did not run, an answer it was not offered, a figure that is
nowhere in the document, and a "missed" clause nobody can point to.
"""
from __future__ import annotations

import json

from core.limitation_audit import (
    AGREES, DISAGREES, NOT_FOUND,
    LimitationAuditResult, audit_case, audit_plan,
    extract_figures, limitation_excerpt, limitation_lines,
    missing_figures, quote_in_document,
)

ANALYSIS = {"critical_limitations": [
    {"topic": "Mechanical ventilation", "detail": "90 days maximum for mechanical ventilation or life support.", "source_page": 41},
    {"topic": "Psychiatric inpatient", "detail": "Up to 30 days per year, then EUR 5,000 annual cap.", "source_page": 44},
    {"topic": "Physiotherapy", "detail": "Maximum 10 sessions per year.", "source_page": None},
]}
DOCUMENT = (
    "--- PAGE 41 ---\nMechanical ventilation or life support is covered for a maximum of 90 consecutive days.\n"
    "--- PAGE 44 ---\nPsychiatric inpatient treatment is paid for up to 30 days per policy year. "
    "The annual maximum for this benefit is EUR 5,000.\n"
    "--- PAGE 45 ---\nPhysiotherapy: 10 sessions per year when referred by a specialist.\n"
    "--- PAGE 90 ---\nWe do not pay for treatment of an injury sustained while taking part in any "
    "professional sport.\n"
)


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


def _answer(findings=None, missed=None):
    return {
        "findings": [{"key": k, "verdict": v, "note": ""} for k, v in (findings or {}).items()],
        "possibly_missed": missed or [],
    }


def _run(client, analysis=ANALYSIS, document=DOCUMENT):
    return audit_plan(plan_name="APRIL - Essential", analysis=analysis,
                      document_text=document, model="test", client=client)


ALL_AGREE = {"L1": AGREES, "L2": AGREES, "L3": AGREES}

# ---------------------------------------------------------------------------
# It must not pass quietly
# ---------------------------------------------------------------------------


def test_a_check_that_did_not_run_is_not_a_clean_check():
    out = LimitationAuditResult(ran=False, error="no key")
    assert out.is_clean is False


def test_an_unreachable_checker_reports_rather_than_approving():
    out = _run(_Stub(raises=RuntimeError("OPENAI_API_KEY is not set in Railway.")))
    assert out.ran is False and out.is_clean is False
    assert "OPENAI_API_KEY" in out.error


def test_a_malformed_answer_is_a_failure_not_an_approval():
    class _Bad(_Stub):
        def create(self, **kwargs):
            return type("R", (), {"choices": [type("C", (), {
                "message": type("M", (), {"content": "not json at all"})()})()]})()

    out = _run(_Bad())
    assert out.ran is False and out.is_clean is False


def test_a_plan_with_no_stored_document_cannot_be_checked():
    out = _run(_Stub(_answer(ALL_AGREE)), document="")
    assert out.ran is False
    assert "could not be checked" in out.error


def test_a_verdict_outside_the_three_offered_is_not_read_as_approval():
    out = _run(_Stub({"findings": [{"key": "L1", "verdict": "looks fine to me"}]}))
    assert out.ran is True
    assert {f.verdict for f in out.findings} == {NOT_FOUND}
    assert len(out.unverified) == 3


def test_a_limitation_the_checker_ignored_stays_unverified():
    out = _run(_Stub(_answer({"L1": AGREES})))
    assert {f.key: f.verdict for f in out.findings} == {"L1": AGREES, "L2": NOT_FOUND, "L3": NOT_FOUND}


# ---------------------------------------------------------------------------
# A figure that is nowhere in the document cannot be agreed
# ---------------------------------------------------------------------------


def test_agreement_is_withdrawn_when_the_figure_is_not_in_the_document():
    analysis = {"critical_limitations": [
        {"topic": "Physiotherapy", "detail": "Maximum 25 sessions per year."},
    ]}
    out = _run(_Stub(_answer({"L1": AGREES})), analysis=analysis)
    finding = out.findings[0]
    assert finding.verdict == NOT_FOUND
    assert finding.figures_missing
    assert "could not be found" in finding.note


def test_a_disagreement_is_kept_as_a_disagreement():
    analysis = {"critical_limitations": [{"topic": "Physiotherapy", "detail": "Maximum 25 sessions per year."}]}
    stub = _Stub({"findings": [{"key": "L1", "verdict": "disagrees", "note": "10 sessions per year"}]})
    out = _run(stub, analysis=analysis)
    assert out.findings[0].verdict == DISAGREES
    assert out.disagreements and out.is_clean is False


def test_figures_are_matched_across_formatting():
    doc = "Annual maximum EUR 5,000.00 and 90 consecutive days of cover; EUREUR 125125 for transport."
    assert missing_figures("EUR 5,000 cap", doc) == []
    assert missing_figures("90 days maximum", doc) == []
    assert missing_figures("EUR 125,125 for transport", doc) == []
    assert missing_figures("EUR 7,000 cap", doc) != []
    assert missing_figures("60 days maximum", doc) != []


def test_euro_sign_after_the_amount_is_read_as_money():
    assert [f.value for f in extract_figures("Limit is 1,000 € per claim")] == ["1000"]


def test_an_empty_document_proves_nothing_about_figures():
    assert missing_figures("EUR 5,000", "") == []


# ---------------------------------------------------------------------------
# The second reader cannot invent a limitation
# ---------------------------------------------------------------------------


def test_a_missed_clause_is_reported_with_the_documents_own_words():
    missed = [{"topic": "Professional sport", "quote": "We do not pay for treatment of an injury sustained while taking part in any professional sport."}]
    out = _run(_Stub(_answer(ALL_AGREE, missed)))
    assert [m.topic for m in out.missed] == ["Professional sport"]
    assert out.is_clean is False  # the broker has something to decide


def test_a_missed_clause_that_is_not_in_the_document_is_discarded():
    missed = [{"topic": "Invented", "quote": "Cover ends on the client's seventieth birthday in every case."}]
    out = _run(_Stub(_answer(ALL_AGREE, missed)))
    assert out.missed == []


def test_a_quote_may_be_elided_but_each_stretch_must_exist():
    assert quote_in_document("We do not pay for treatment … any professional sport.", DOCUMENT)
    assert not quote_in_document("We do not pay for treatment … any amateur sport.", DOCUMENT)
    assert not quote_in_document("too short", DOCUMENT)


def test_missed_clauses_are_capped():
    quote = "Physiotherapy: 10 sessions per year when referred by a specialist."
    missed = [{"topic": f"t{i}", "quote": quote} for i in range(20)]
    out = _run(_Stub(_answer(ALL_AGREE, missed)))
    assert len(out.missed) == 8


def test_a_plan_with_no_listed_limitations_is_still_checked_for_missing_ones():
    stub = _Stub(_answer(missed=[{"topic": "Sport", "quote": "any professional sport"}]))
    out = _run(stub, analysis={"critical_limitations": []})
    assert out.ran is True
    assert "(the analyst listed no limitations)" in stub.prompts[0]
    assert len(out.missed) == 1


def test_the_prompt_names_the_plan_so_a_multi_tier_table_is_read_in_the_right_column():
    stub = _Stub(_answer(ALL_AGREE))
    _run(stub)
    assert "PLAN: APRIL - Essential" in stub.prompts[0]
    assert "Judge against the plan named below" in stub.prompts[0]


# ---------------------------------------------------------------------------
# The excerpt must reach limitations that sit deep in the wording
# ---------------------------------------------------------------------------


def _long_wording(deep_clause: str, pages: int = 120) -> str:
    filler = "General introduction to the plan and how to contact us. " * 12
    parts = [f"--- PAGE {n} ---\n{filler}\n" for n in range(1, pages)]
    parts.insert(100, f"--- PAGE 101 ---\nGeneral exclusions. {deep_clause}\n")
    return "".join(parts)


def test_the_excerpt_keeps_a_deep_page_that_states_the_figure():
    doc = _long_wording("Long-term ventilation is limited to 90 days in total.")
    assert len(doc) > 60000
    excerpt = limitation_excerpt(doc, [("Mechanical ventilation", "90 days maximum for life support")], 60000)
    assert "Long-term ventilation is limited to 90 days" in excerpt
    assert len(excerpt) <= 60000


def test_the_excerpt_keeps_a_deep_exclusions_page_even_with_no_listed_limitations():
    doc = _long_wording("We do not pay for treatment of any professional sport injury.")
    excerpt = limitation_excerpt(doc, [], 60000)
    assert "professional sport injury" in excerpt


def test_a_short_document_is_sent_whole():
    assert limitation_excerpt(DOCUMENT, [], 60000) == DOCUMENT


def test_a_document_without_page_markers_is_still_searched_beyond_the_opening():
    doc = ("Introduction. " * 8000) + "Mechanical ventilation is capped at 90 days in total. " + ("More text. " * 4000)
    excerpt = limitation_excerpt(doc, [("Ventilation", "90 days")], 60000)
    assert "capped at 90 days" in excerpt


# ---------------------------------------------------------------------------
# Whole-case behaviour
# ---------------------------------------------------------------------------


def _result(provider, plan, limitations):
    return {"provider": provider, "target_plan": plan,
            "analysis": {"provider": provider, "plan_name": plan, "critical_limitations": limitations}}


def test_every_plan_has_to_be_checked_for_the_case_to_count_as_checked():
    results = [_result("APRIL", "Essential", ANALYSIS["critical_limitations"]),
               _result("Bupa", "Select", [{"topic": "x", "detail": "10 days"}])]
    out = audit_case(results=results, documents={"APRIL - Essential": DOCUMENT},
                     model="test", client=_Stub(_answer(ALL_AGREE)))
    assert out.ran is False
    assert "Bupa - Select" in out.error


def test_a_case_with_every_plan_checked_and_nothing_disputed_is_clean():
    results = [_result("APRIL", "Essential", ANALYSIS["critical_limitations"])]
    out = audit_case(results=results, documents={"APRIL - Essential": DOCUMENT},
                     model="test", client=_Stub(_answer(ALL_AGREE)))
    assert out.ran is True and out.is_clean is True
    assert len(out.findings) == 3


def test_limitation_lines_accept_plain_strings_and_skip_empty_items():
    lines = limitation_lines({"critical_limitations": ["Plain text limit of 5 days", {"topic": "", "detail": ""}, {"topic": "A", "detail": "B"}]})
    assert [(k, d) for k, _, d, _ in lines] == [("L1", "Plain text limit of 5 days"), ("L3", "B")]
