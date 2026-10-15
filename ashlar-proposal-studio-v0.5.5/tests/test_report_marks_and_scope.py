"""The comparison data carries its own state, so no renderer can lose it.

Two guarantees live here rather than in each of the three renderers:

  1. Every benefit cell arrives with a four-state mark, and a cell that is not
     covered arrives already reduced to "Not covered". A renderer that simply
     prints `values` cannot reintroduce "not covered at this tier,
     complications EUR 10,000 after 10 months" beside a cross.

  2. A comparison of plans written for different territories arrives with the
     scope warning already composed. A Europe-only premium beside a worldwide
     premium reads as a bargain when it is a different product, and the warning
     is derived from the documents rather than left to whoever writes the prose.
"""
from __future__ import annotations

from core.benefit_state import ACTION, COVERED, NOT_COVERED, SUB_LIMIT, UNKNOWN
from core.client_analysis import apply_client_report_rules, build_comparison_matrix


def _plan(provider, plan, area, benefits, premium="6,841.27"):
    return {"analysis": {
        "provider": provider, "plan_name": plan, "area_of_cover": area,
        "annual_limit": "EUR 1,000,000",
        "premium": {"currency": "EUR", "amount": premium, "frequency": "annual"},
        "benefits": benefits,
    }}


MP = _plan("Morgan Price", "Comprehensive", "Europe", {
    "inpatient": "Paid in full",
    "outpatient": "Within EUR 5,000 combined",
    "dental": "Not covered on this quotation.",
    "mental_health": "Pre-authorisation required, 30 days",
})
APRIL = _plan("APRIL", "MyHealth Essential", "Worldwide excluding USA", {
    "inpatient": "Unlimited",
    "outpatient": "Full refund - max 15 visits",
    "dental": "Excluded",
    "mental_health": "Covered in full",
}, premium="6,840.91")


def _row(rows, topic):
    return next(r for r in rows if r["topic"] == topic)


# ---------------------------------------------------------------------------
# Marks
# ---------------------------------------------------------------------------

def test_every_benefit_cell_carries_a_mark():
    rows = build_comparison_matrix([MP, APRIL])
    benefit_rows = [r for r in rows if r["category"] == "Benefits"]
    assert benefit_rows, "the matrix has no benefit rows to mark"
    for row in benefit_rows:
        assert set(row["marks"]) == set(row["values"]), row["topic"]
        for name, m in row["marks"].items():
            assert m["state"] in {COVERED, ACTION, SUB_LIMIT, NOT_COVERED, UNKNOWN}


def test_the_states_match_what_the_documents_say():
    rows = build_comparison_matrix([MP, APRIL])
    states = {
        row["topic"]: {name: m["state"] for name, m in row["marks"].items()}
        for row in rows if row["category"] == "Benefits"
    }
    mp, april = "Morgan Price - Comprehensive", "APRIL - MyHealth Essential"
    assert states["In-patient treatment"] == {mp: COVERED, april: COVERED}
    assert states["Out-patient treatment"] == {mp: SUB_LIMIT, april: SUB_LIMIT}
    assert states["Dental"] == {mp: NOT_COVERED, april: NOT_COVERED}
    assert states["Mental health"] == {mp: ACTION, april: COVERED}
    # A benefit the extraction never found is unknown, not "not covered".
    assert states["Cancer / oncology"][mp] == UNKNOWN


def test_a_not_covered_benefit_loses_its_specification_in_the_value():
    """Chris's editorial rule, enforced in the data rather than the renderer:
    "when something is not covered you will not write specification - just not
    covered". The original stays on the mark for the broker.

    It applies where the benefit pays nothing. Where part of it pays, the cell
    keeps what it pays -- see the companion test below, which exists because
    the earlier reading of this rule told a client they had no mental health
    cover when they had EUR 500 and seven sessions.
    """
    row = _row(build_comparison_matrix([MP, APRIL]), "Dental")
    mp = "Morgan Price - Comprehensive"
    assert row["values"][mp] == "Not covered"
    assert "quotation" not in row["values"][mp]
    assert "quotation" in row["marks"][mp]["original"]
    assert row["marks"][mp]["allows_detail"] is False


def test_a_partly_covered_benefit_keeps_its_figures_in_the_value():
    """The companion rule, from the case that went to a client."""
    mixed = dict(MP)
    mixed["analysis"] = dict(MP["analysis"])
    mixed["analysis"]["benefits"] = dict(MP["analysis"]["benefits"])
    mixed["analysis"]["benefits"]["mental_health"] = (
        "Inpatient psychiatric care is not covered. Outpatient treatment is "
        "limited to EUR 500, max 7 sessions."
    )
    row = _row(build_comparison_matrix([mixed, APRIL]), "Mental health")
    value = row["values"]["Morgan Price - Comprehensive"]
    assert "EUR 500" in value and "7 sessions" in value
    assert value != "Not covered"


def test_financial_and_scope_rows_are_not_marked():
    """A premium is a fact, not a state. Running "EUR 6,841.27 annual" through
    the benefit classifier would print an amber sub-limit triangle beside a
    price, which says nothing true."""
    rows = build_comparison_matrix([MP, APRIL])
    for topic in ("Premium", "Annual policy limit", "Area of cover", "Deductible / excess"):
        assert "marks" not in _row(rows, topic), topic
    assert _row(rows, "Premium")["values"]["APRIL - MyHealth Essential"] == "EUR 6,840.91 annual"


# ---------------------------------------------------------------------------
# Scope
# ---------------------------------------------------------------------------

def _report(results, **kwargs):
    return apply_client_report_rules({"plans": [], "next_steps": []}, results=results, **kwargs)


def test_a_mismatched_scope_produces_the_warning_and_names_the_areas():
    report = _report([MP, APRIL])
    note = report["coverage_scope_note"]
    assert "not written for the same territory" in note
    assert "not directly comparable" in note
    assert "Morgan Price - Comprehensive: Europe" in note
    assert report["coverage_areas"]["APRIL - MyHealth Essential"] == "Worldwide excluding USA"


def test_matching_scopes_produce_no_warning():
    twin = _plan("Bupa Global", "Select", "Worldwide excluding USA", {"inpatient": "Paid in full"})
    assert _report([APRIL, twin])["coverage_scope_note"] == ""


def test_the_warning_is_written_in_greek_for_a_greek_report():
    note = _report([MP, APRIL], language="Greek")["coverage_scope_note"]
    assert "γεωγραφική κάλυψη" in note
    assert "δεν είναι άμεσα συγκρίσιμα" in note


def test_a_single_plan_is_never_warned_about_its_own_scope():
    assert _report([MP])["coverage_scope_note"] == ""


# ---------------------------------------------------------------------------
# Considerations survive unless there is a reason to remove them
# ---------------------------------------------------------------------------

def test_a_client_facing_caveat_is_not_dropped_for_missing_a_keyword():
    """Regression, and the reason this file exists in the shape it does.

    A consideration used to be kept only if it mentioned a waiting period or
    one of five words. On the France relocation case that silently deleted the
    three caveats the client most needed: premium quoted before tax, the
    insurer's unconfirmed position on nationality, and the fee for paying
    monthly. A report removes a consideration because it is broker
    housekeeping or because it is ungrounded -- never because it failed to use
    an expected word.
    """
    report = apply_client_report_rules({
        "plans": [], "next_steps": [],
        "important_considerations": [
            "The Morgan Price premium is quoted before the 14% French insurance premium tax.",
            "Bupa has not yet confirmed its position on Russian nationality in writing.",
            "Paying by instalments carries an administration fee of 8% monthly.",
        ],
    }, results=[MP, APRIL])
    kept = report["important_considerations"]
    assert len(kept) == 3, kept
    assert any("premium tax" in x for x in kept)
    assert any("administration fee" in x for x in kept)


def test_broker_housekeeping_is_still_removed():
    report = apply_client_report_rules({
        "plans": [], "next_steps": [],
        "important_considerations": [
            "The broker must clarify the insurer's underwriting basis.",
            "The client should verify visa type and residency status.",
            "Out-patient treatment is capped at EUR 2,500 a year.",
        ],
    }, results=[MP, APRIL])
    assert report["important_considerations"] == ["Out-patient treatment is capped at EUR 2,500 a year."]


def test_an_ungrounded_waiting_period_claim_is_still_removed():
    """The documents in this fixture say nothing about a 24-month wait."""
    report = apply_client_report_rules({
        "plans": [], "next_steps": [],
        "important_considerations": ["Elective surgery carries a 24-month waiting period."],
    }, results=[MP, APRIL])
    assert report["important_considerations"] == []


# ---------------------------------------------------------------------------
# The marks have to survive the font the container actually has
# ---------------------------------------------------------------------------

def test_the_pdf_never_prints_a_mark_the_font_cannot_draw():
    """The regression that reached a client's PDF.

    The body font is picked for reading and is not obliged to carry Geometric
    Shapes. The container ships Noto Sans, which does not, so every mark came
    out as .notdef -- the text layer of the delivered PDF reads
    "\\x00 Not covered" -- and the four states were left distinguishable only
    by colour. The local machine had DejaVu and rendered them, which is why it
    passed inspection.

    Either a font that can draw them is registered, or letters every font has
    are used instead. What must never happen is an invisible mark.
    """
    from core import report_pdf

    if report_pdf.MARK_FONT:
        from reportlab.pdfbase import pdfmetrics
        face = pdfmetrics.getFont(report_pdf.MARK_FONT).face
        drawable = set(getattr(face, "charToGlyph", {}))
        for state, symbol in report_pdf.MARK_SYMBOL.items():
            assert ord(symbol) in drawable, f"{state} would print as .notdef"
    else:
        # No symbol font available: the fallback must be plain ASCII, which
        # every text font can draw.
        for state, ch in report_pdf.MARK_FALLBACK.items():
            assert ch.isascii() and ch.isprintable(), state


def test_every_state_has_a_fallback_distinct_from_the_others():
    """Colour is never the only difference between two states."""
    from core import report_pdf
    assert set(report_pdf.MARK_FALLBACK) == set(report_pdf.MARK_SYMBOL)
    assert len(set(report_pdf.MARK_FALLBACK.values())) == len(report_pdf.MARK_FALLBACK)
