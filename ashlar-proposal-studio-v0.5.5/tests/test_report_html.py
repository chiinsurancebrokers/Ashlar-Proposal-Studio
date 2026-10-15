"""The HTML report, checked for the things a reader would be harmed by.

Not the styling -- the guarantees: the scope warning appears above the first
premium, a benefit that is not covered carries no specification, every mark is
readable without colour, the page is one self-contained file, and nothing a
client or an insurer wrote can inject markup into it.
"""
from __future__ import annotations

import re

import pytest

from core.client_analysis import apply_client_report_rules, build_comparison_matrix
from core.report_html import build_html, build_html_bytes


def _plan(provider, plan, area, benefits, premium="6,841.27"):
    return {"analysis": {
        "provider": provider, "plan_name": plan, "area_of_cover": area,
        "annual_limit": "EUR 1,000,000",
        "premium": {"currency": "EUR", "amount": premium, "frequency": "per year"},
        "benefits": benefits,
    }}


EUROPE = _plan("Morgan Price", "Comprehensive", "Europe", {
    "inpatient": "Paid in full",
    "outpatient": "Within EUR 5,000 combined",
    "dental": "Not covered on this quotation.",
    "mental_health": "Pre-authorisation required",
    "optical": "",
})
WORLDWIDE = _plan("APRIL", "MyHealth Essential", "Worldwide excluding USA", {
    "inpatient": "Unlimited", "outpatient": "Paid in full",
    "dental": "Excluded", "mental_health": "Covered in full", "optical": "EUR 150 per year",
}, premium="6,840.91")


def _report(results, **overrides):
    report = {
        "report_title": "Cover for a family relocating to France",
        "client_name": "The Polat family",
        "executive_summary": "Three plans were compared on the same household.",
        "client_needs_summary": "Cover the consulate will accept.",
        "plans": [], "key_differences": [],
        "ashlar_assessment": {"headline": "Morgan Price is the closest fit",
                              "recommended_provider": "Morgan Price",
                              "recommended_plan": "Comprehensive",
                              "reasoning": ["Outpatient paid in full"]},
        "important_considerations": ["Out-patient treatment is capped on one plan."],
        "next_steps": ["Return the medical questionnaires."],
        "disclaimer": "The policy wording prevails.",
    }
    report.update(overrides)
    report["comparison_matrix"] = build_comparison_matrix(results)
    return apply_client_report_rules(report, results=results)


def _html(results, **kwargs):
    return build_html(client_analysis=_report(results), results=results, **kwargs)


# ---------------------------------------------------------------------------
# Scope before price
# ---------------------------------------------------------------------------

def test_the_scope_warning_comes_before_the_first_premium():
    """Not merely present: above. A reader who meets EUR 6,840.91 before being
    told the two plans cover different territories has already compared them."""
    page = _html([EUROPE, WORLDWIDE])
    warning = page.index("not written for the same territory")
    first_premium = page.index("6,840.91")
    assert warning < first_premium


def test_matching_scopes_produce_no_warning_strip():
    twin = _plan("Bupa Global", "Select", "Worldwide excluding USA", {"inpatient": "Paid in full"})
    assert "not written for the same territory" not in _html([WORLDWIDE, twin])


def test_the_warning_is_recovered_when_a_stored_report_predates_it():
    """An older saved case has no note on it. The renderer recomputes rather
    than letting the warning go missing."""
    report = _report([EUROPE, WORLDWIDE])
    report.pop("coverage_scope_note")
    page = build_html(client_analysis=report, results=[EUROPE, WORLDWIDE])
    assert "not written for the same territory" in page


# ---------------------------------------------------------------------------
# The editorial rule
# ---------------------------------------------------------------------------

def test_a_benefit_that_is_not_covered_carries_no_specification():
    page = _html([EUROPE, WORLDWIDE])
    assert "Not covered" in page
    assert "complications" not in page
    assert "EUR 10,000" not in page


def test_an_unspecified_benefit_is_not_reported_as_not_covered():
    """A benefit the documents never mention is unknown. Printing it as a
    cross would tell a client they lack cover the insurer may well provide."""
    page = _html([EUROPE, WORLDWIDE])
    assert "Not specified in the documents supplied" in page


# ---------------------------------------------------------------------------
# Marks
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("symbol", ["●", "○", "▲", "✕"])
def test_each_state_carries_a_symbol_not_only_a_colour(symbol):
    """So the states still read in a black-and-white printout and for a
    colour-blind client."""
    assert symbol in _html([EUROPE, WORLDWIDE])


def test_the_page_explains_its_own_marks():
    page = _html([EUROPE, WORLDWIDE])
    for label in ("Covered", "Action needed first", "Covered with a limit", "Not covered"):
        assert label in page


def test_a_premium_never_wears_a_benefit_mark():
    """"EUR 6,841.27 per year" is a fact, not a state. An amber sub-limit
    triangle beside a price says nothing true."""
    page = _html([EUROPE, WORLDWIDE])
    row = re.search(r"<tr><th scope=\"row\">Premium</th>(.*?)</tr>", page, re.S)
    assert row, "the premium row is missing from the comparison"
    assert "mark-sym" not in row.group(1)


# ---------------------------------------------------------------------------
# The file itself
# ---------------------------------------------------------------------------

def test_the_page_is_one_self_contained_file():
    """It is emailed, saved and opened offline. Only the font stylesheet may
    be fetched, and the font stack falls back without it."""
    page = _html([EUROPE, WORLDWIDE])
    assert page.startswith("<!doctype html>")
    assert "<style>" in page and "<script" not in page
    external = re.findall(r'(?:src|href)="(https?://[^"]+)"', page)
    assert all("fonts.googleapis.com" in u or "fonts.gstatic.com" in u for u in external), external


def test_the_page_declares_its_language():
    assert '<html lang="en">' in _html([EUROPE])
    assert '<html lang="el">' in _html([EUROPE], language="Greek")


def test_greek_renders_greek_chrome():
    page = _html([EUROPE, WORLDWIDE], language="Greek")
    assert "Συγκριτικός πίνακας" in page
    assert "Δεν καλύπτεται" in page


def test_markup_in_a_document_value_cannot_escape_into_the_page():
    """Plan names and benefit text come out of insurer documents and client
    forms. Neither is trusted to contain HTML."""
    hostile = _plan("<script>alert(1)</script>", "Plan\"onload=\"x", "Europe",
                    {"inpatient": "<b>Paid in full</b>"})
    page = build_html(client_analysis=_report([hostile]), results=[hostile])
    assert "<script>alert" not in page
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in page
    assert "<b>Paid in full</b>" not in page


def test_bytes_are_utf8():
    data = build_html_bytes(client_analysis=_report([EUROPE]), results=[EUROPE], language="Greek")
    assert isinstance(data, bytes)
    assert "Συγκριτικός πίνακας" in data.decode("utf-8")


def test_an_empty_section_is_left_out_rather_than_rendered_hollow():
    """A heading standing over an empty list reads as a document that failed
    to load."""
    report = _report([EUROPE])
    report["important_considerations"] = []
    report["key_differences"] = []
    page = build_html(client_analysis=report, results=[EUROPE])
    assert "id='differences'" not in page
    assert "<h3>Important considerations</h3>" not in page
    # The surviving block gives the section its title, rather than the page
    # announcing "considerations & next steps" above only one of them.
    assert "<h2>Next steps</h2>" in page
    assert "Important considerations &amp; next steps" not in page


def test_a_report_with_almost_nothing_in_it_still_renders():
    page = build_html(client_analysis={}, results=[])
    assert page.startswith("<!doctype html>")
    assert page.rstrip().endswith("</html>")


# ---------------------------------------------------------------------------
# A Greek report is Greek all the way down
# ---------------------------------------------------------------------------

def test_a_greek_report_has_greek_row_labels_and_bands():
    """The matrix is built once, in English, because it is structured data.
    A Greek client should still not be reading "Out-patient treatment" and
    "Underwriting" down the side and middle of their only table."""
    page = _html([EUROPE, WORLDWIDE], language="Greek")
    for greek in ("Εξωνοσοκομειακά", "Οδοντιατρικά", "Ασφάλιστρο", "Παροχές", "Ανάληψη κινδύνου"):
        assert greek in page, greek
    for english in (">Out-patient treatment<", ">Premium<", ">Benefits<", ">Underwriting<"):
        assert english not in page, english


def test_the_insurers_own_words_are_never_translated():
    """A benefit value is a quotation from the insurer's document. Translating
    it would make the report say something the document does not."""
    page = _html([EUROPE, WORLDWIDE], language="Greek")
    assert "Within EUR 5,000 combined" in page
    assert "Worldwide excluding USA" in page


# ---------------------------------------------------------------------------
# Dark mode, and the print rule that dark mode is allowed to exist under
# ---------------------------------------------------------------------------

def test_the_page_has_a_dark_ground_and_keeps_the_meaning_of_each_colour():
    """A client opens this on a phone in the evening. The ground inverts; the
    roles do not -- verdigris still means covered, oxblood still means absent."""
    page = _html([EUROPE, WORLDWIDE])
    assert "@media (prefers-color-scheme:dark)" in page
    assert ':root[data-theme="dark"]' in page
    assert "--verdigris:#79A8A3" in page and "--oxblood:#C9565A" in page


def test_printing_cannot_be_broken_by_dark_mode():
    """The regression this guards is a real one. The dark rule is written as
    :root:not([data-theme="light"]), which outranks a plain :root, so a print
    block that redefines the tokens without !important loses to it -- and a
    client printing from a dark-mode machine gets near-white ink on white
    paper. That is how the first Polat comparison printed: no title, no marks.

    Every token the dark rule sets must be set again in the print block, and
    each one must carry !important.
    """
    import re
    page = _html([EUROPE])
    print_block = page[page.index("@media print{"):]
    dark = page[page.index("@media (prefers-color-scheme:dark)"):]
    dark_tokens = set(re.findall(r"(--[a-z-]+):", dark[:dark.index("}")  + 1]))
    assert dark_tokens, "the dark rule sets no tokens"
    for token in dark_tokens:
        if token == "--mortar-dark":
            continue
        assert re.search(rf"{token}:[^;]+!important", print_block), f"{token} is not forced for print"


def test_print_keeps_the_table_on_the_sheet_and_the_marks_visible():
    page = _html([EUROPE, WORLDWIDE])
    print_block = page[page.index("@media print{"):]
    # A table with a minimum width wider than the sheet is clipped at its edge.
    assert "min-width:0" in print_block
    assert "overflow:visible" in print_block
    # The header repeats when the table runs over a page.
    assert "table-header-group" in print_block


def test_the_title_is_visible_in_dark_mode():
    """The masthead is light-on-dark by construction. Inverting the tokens
    swaps its ground and its ink, which paints the title dark on a dark
    ground -- the same disappearance the printed version suffered. The dark
    rule must name the masthead's ink explicitly."""
    import re
    page = _html([EUROPE])
    dark_rules = page[:page.index("@media print")]
    rule = re.search(
        r'\.masthead h1,\s*:root:not\(\[data-theme="light"\]\) \.masthead \.client\{([^}]*)\}',
        dark_rules)
    assert rule, "the dark rule never names the masthead's ink"
    assert "color:var(--ink)" in rule.group(1)
