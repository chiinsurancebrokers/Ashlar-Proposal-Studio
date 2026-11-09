"""The second reader must see the applicant's quote.

A brochure lists optional modules and deductibles as options. Only the quote
says which were chosen. Without it every selection reads as a contradiction,
which buries the real errors and trains the broker to tick the box unread.
"""
from __future__ import annotations

import json

from core.benefit_audit import AGREES, DISAGREES, PER_QUOTE, audit_plan
from core.limitation_audit import audit_plan as audit_limitations_plan
from core.report_leaks import find_broker_leaks

ORDER = [("dental", "Dental"), ("outpatient", "Out-patient")]
ANALYSIS = {"benefits": {
    "dental": "Optional - not selected (Quote p.1).",
    "outpatient": "Included (selected on the quote).",
}}
QUOTE = "Dental/Optical Not selected. Outpatient selected, 100%. Annual deductible EUR 1000."
DOC = "Dental (Optional) EUR 1,000. Outpatient - Optional. Deductible options EUR 500, 1,000, 2,500."


class _Stub:
    def __init__(self, payload):
        self._payload = payload
        self.prompts: list[str] = []
        self.chat = self

    @property
    def completions(self):
        return self

    def create(self, **kwargs):
        self.prompts.append(kwargs["messages"][0]["content"])
        body = json.dumps(self._payload)
        return type("R", (), {"choices": [type("C", (), {
            "message": type("M", (), {"content": body})()})()]})()


def test_benefit_prompt_contains_quote_and_applicant():
    stub = _Stub({"findings": []})
    audit_plan(plan_name="APRIL", analysis=ANALYSIS, document_text=DOC, benefit_order=ORDER,
               quote_text=QUOTE, applicant="age 61, male", model="t", client=stub)
    prompt = stub.prompts[0]
    assert "Annual deductible EUR 1000" in prompt
    assert "age 61, male" in prompt
    assert "per_quote" in prompt


def test_per_quote_is_accepted_and_is_not_a_dispute():
    stub = _Stub({"findings": [
        {"key": "dental", "verdict": "per_quote", "note": ""},
        {"key": "outpatient", "verdict": "per_quote", "note": ""},
    ]})
    result = audit_plan(plan_name="APRIL", analysis=ANALYSIS, document_text=DOC, benefit_order=ORDER,
                        quote_text=QUOTE, model="t", client=stub)
    assert result.ran and result.is_clean
    assert len(result.per_quote) == 2
    assert not result.disagreements
    assert not any(f.needs_attention for f in result.findings)


def test_real_disagreement_still_blocks():
    stub = _Stub({"findings": [{"key": "dental", "verdict": "disagrees", "note": "x"}]})
    result = audit_plan(plan_name="APRIL", analysis=ANALYSIS, document_text=DOC, benefit_order=ORDER,
                        quote_text=QUOTE, model="t", client=stub)
    assert not result.is_clean and result.disagreements[0].verdict == DISAGREES


def test_unknown_verdict_is_still_not_approval():
    stub = _Stub({"findings": [{"key": "dental", "verdict": "probably fine", "note": ""}]})
    result = audit_plan(plan_name="APRIL", analysis=ANALYSIS, document_text=DOC, benefit_order=ORDER,
                        quote_text=QUOTE, model="t", client=stub)
    assert result.findings[0].verdict != AGREES and result.findings[0].verdict != PER_QUOTE


def test_missing_quote_is_stated_not_hidden():
    stub = _Stub({"findings": []})
    audit_plan(plan_name="APRIL", analysis=ANALYSIS, document_text=DOC, benefit_order=ORDER,
               quote_text="", model="t", client=stub)
    assert "no quote text is stored" in stub.prompts[0]


def test_limitation_figure_from_quote_is_not_downgraded():
    analysis = {"critical_limitations": [
        {"topic": "Annual deductible", "detail": "The client pays the first EUR 1,000 each year.", "source_page": "p.2"},
    ]}
    stub = _Stub({"findings": [{"key": "L1", "verdict": "per_quote", "note": ""}], "possibly_missed": []})
    doc = "Deductible options: EUR 500, EUR 2,500 or EUR 5,000."
    result = audit_limitations_plan(plan_name="APRIL", analysis=analysis, document_text=doc,
                                    quote_text="Annual deductible EUR 1,000", model="t", client=stub)
    assert result.findings[0].verdict == PER_QUOTE
    assert result.per_quote and not result.disagreements


def test_limitation_figure_absent_everywhere_is_still_downgraded():
    analysis = {"critical_limitations": [
        {"topic": "Cap", "detail": "Capped at EUR 77,777.", "source_page": "p.1"},
    ]}
    stub = _Stub({"findings": [{"key": "L1", "verdict": "agrees", "note": ""}], "possibly_missed": []})
    result = audit_limitations_plan(plan_name="APRIL", analysis=analysis, document_text="Cap EUR 5,000.",
                                    quote_text="Premium EUR 100", model="t", client=stub)
    assert result.findings[0].verdict == "not_found"


def test_broker_notes_are_found():
    results = [{"analysis": {
        "plan_name": "Essential",
        "benefits": {"evacuation": "Transport coffin: EUR 1,500 per TOB; the wording states EUR 2,000, so check the governing figure.",
                     "optical": "Not specified", "dental": "Included. EUR 1,000."},
        "critical_limitations": [{"topic": "x", "detail": "Unclear. See guide."}],
    }}]
    leaks = find_broker_leaks(results)
    fields = {l.field for l in leaks}
    assert "benefit:evacuation" in fields and "benefit:optical" in fields
    assert "benefit:dental" not in fields
    assert any(f.startswith("limitation") for f in fields)


def test_clean_text_has_no_leaks():
    assert find_broker_leaks([{"analysis": {"benefits": {"dental": "Included at 80%."}}}]) == []


def test_unnamed_case_placeholder_is_not_shown_as_a_reference():
    from core.report_html import _masthead
    from core.report_labels import _with_extras as labels

    lab = labels("Greek")
    shown = _masthead({"client_name": "Thomas Barkamis", "case_reference": "Unnamed case"}, [], lab, "Greek")
    assert "Unnamed case" not in shown
    real = _masthead({"client_name": "Thomas Barkamis", "case_reference": "Barkamis 2026"}, [], lab, "Greek")
    assert "Barkamis 2026" in real
