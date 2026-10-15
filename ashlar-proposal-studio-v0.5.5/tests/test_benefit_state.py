"""The four-state vocabulary, and the two rules it exists to enforce.

Rule one: a benefit that is not covered reads "Not covered" and nothing
else. A report that writes "not covered at this tier, complications
€10,000 after 10 months" beside a cross tells the reader two things at
once and leaves them unsure which half to believe.

Rule two: a comparison warns when the plans are not written for the same
territory, before it shows any price. A Europe-only premium set against
two worldwide premiums reads as a bargain when it is a different product.
"""
from __future__ import annotations

import pytest

from core.benefit_state import (
    classify, display_text, mark, coverage_areas, scope_differs,
    COVERED, ACTION, SUB_LIMIT, NOT_COVERED, UNKNOWN,
)


@pytest.mark.parametrize("text", [
    "Full refund", "Paid in full", "Covered in full", "100%",
    "Unlimited", "No limit", "No overall limit",
    "Πλήρης κάλυψη",
])
def test_uncapped_benefits_read_as_covered(text):
    assert classify(text) == COVERED


@pytest.mark.parametrize("text", [
    "Not covered", "No cover", "Excluded", "Not included", "Declined",
    "Δεν καλύπτεται", "Εξαιρείται",
])
def test_absent_benefits_read_as_not_covered(text):
    assert classify(text) == NOT_COVERED


@pytest.mark.parametrize("text", ["—", "–", "-", "None", "nil", "n/a", "0"])
def test_an_empty_cell_reads_as_not_covered(text):
    assert classify(text) == NOT_COVERED


@pytest.mark.parametrize("text", [
    "Full refund – max 5 visits",
    "Full refund - Maximum 15 nights",
    "Emergency treatment up to 30 days — paid in full",
])
def test_a_dash_inside_a_sentence_is_punctuation_not_an_empty_cell(text):
    """Regression. A standalone dash means "nothing here", but a dash in
    the middle of a benefit is a hyphen. Reading it as "nothing" told a
    client they had no cover where they had cover with a cap on it."""
    assert classify(text) == SUB_LIMIT
    assert display_text(text) == text.strip()


@pytest.mark.parametrize("text", [
    "Pre-authorisation is required", "Prior approval needed",
    "Subject to approval", "Reimbursed on claim", "Προέγκριση",
])
def test_conditions_read_as_action_needed(text):
    assert classify(text) == ACTION


@pytest.mark.parametrize("text", [
    "Combined limit 2,500", "€9,400 annual maximum", "Up to 30 days travel only",
    "€500, 7 sessions", "Within combined out-patient limit", "2,500",
    "750 per year", "Maximum 15 specialist visits",
])
def test_capped_benefits_read_as_sub_limit(text):
    assert classify(text) == SUB_LIMIT


def test_a_countable_allowance_caps_even_when_the_money_is_paid_in_full():
    """"15 consultations, paid in full" runs out at fifteen. The cap is the
    part the reader needs, so it outranks the "in full" wording."""
    assert classify("15 consultations, paid in full") == SUB_LIMIT
    assert classify("Full refund, maximum 10 visits") == SUB_LIMIT


@pytest.mark.parametrize("text", ["", "   ", "Not specified", "Unknown"])
def test_missing_values_are_marked_unknown_not_guessed(text):
    assert classify(text) == UNKNOWN
    assert display_text(text) == "Not specified"


# ---------------------------------------------------------------------------
# Rule one: no specification beside a cross
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("text", [
    "Not covered at this tier, complications €10,000 after 10 months",
    "Not covered. Emergency dental after an accident is paid in full",
    "Excluded — see the policy wording for the alternative benefit",
])
def test_a_not_covered_cell_says_only_that(text):
    assert classify(text) == NOT_COVERED
    assert display_text(text) == "Not covered"


def test_mark_tells_the_renderer_when_detail_is_allowed():
    absent = mark("Not covered at this tier, complications €10,000")
    assert absent["state"] == NOT_COVERED
    assert absent["text"] == "Not covered"
    assert absent["allows_detail"] is False
    # The original is kept so a broker can still see what was extracted.
    assert "complications" in absent["original"]

    capped = mark("Combined limit 2,500")
    assert capped["allows_detail"] is True
    assert capped["text"] == "Combined limit 2,500"


# ---------------------------------------------------------------------------
# Rule two: scope before price
# ---------------------------------------------------------------------------

def _plan(provider: str, plan: str, area: str) -> dict:
    """plan_display_name renders "<provider> - <plan>", so the fixture has to
    carry both for the returned keys to be the names a reader would see."""
    return {"analysis": {"provider": provider, "plan_name": plan, "area_of_cover": area}}


def test_scope_difference_is_detected():
    """The comparison that prompted this: two worldwide plans against one
    Europe-only plan, where the Europe premium looked like a bargain."""
    results = [
        _plan("APRIL", "MyHealth Essential", "Worldwide excluding USA"),
        _plan("Bupa Global", "Select", "Worldwide excluding USA"),
        _plan("Morgan Price", "Comprehensive", "Europe"),
    ]
    assert scope_differs(results) is True
    assert coverage_areas(results)["Morgan Price - Comprehensive"] == "Europe"


def test_matching_scopes_raise_no_warning():
    results = [
        _plan("APRIL", "MyHealth Essential", "Worldwide excluding USA"),
        _plan("Bupa Global", "Select", "Worldwide excluding USA"),
    ]
    assert scope_differs(results) is False


def test_scope_comparison_ignores_casing_and_spacing():
    results = [
        _plan("A", "Plan", "Worldwide excluding USA"),
        _plan("B", "Plan", "  worldwide   excluding usa "),
    ]
    assert scope_differs(results) is False


def test_a_missing_area_does_not_fake_a_difference():
    """An extraction that failed to find the area must not be reported to
    the client as a scope mismatch."""
    results = [_plan("A", "Plan", "Europe"), _plan("B", "Plan", "")]
    assert scope_differs(results) is False


def test_a_single_plan_has_nothing_to_compare():
    assert scope_differs([_plan("A", "Plan", "Europe")]) is False
    assert scope_differs([]) is False


# ---------------------------------------------------------------------------
# The verdict is the opening clause, not any clause
# ---------------------------------------------------------------------------
#
# These strings are the extraction's own words from the France relocation
# case. Every one of them describes a benefit the client HAS, and every one
# of them was printed to the client as "Not covered", because the classifier
# scanned the whole cell for an absence and found one in a subordinate clause.
#
# The earlier tests in this file did not catch it: each of their negative
# fixtures begins with the negative, so they tested the assumption rather than
# probing it. A real cell names what sits outside a benefit as part of
# describing the benefit.

APRIL_DENTAL = (
    "Included per the quote's Essential benefit overview; the selection icon did not "
    "extract as text, so confirm on the certificate (quote p.4). Annual limit EUR 1,000. "
    "Routine dental is 80% after 3 months; major dental is 80% after 6 months. "
    "Orthodontics are not covered."
)
APRIL_OPTICAL = (
    "Included per the quote Essential overview, subject to certificate confirmation. "
    "Eye examination and visual aids up to EUR 200, with one frame every two years, "
    "after a 6-month waiting period. Laser vision correction is not covered."
)
APRIL_CANCER = (
    "Included at 100% for consultations, diagnostics and treatment as an inpatient, "
    "day-patient or outpatient. Cancer-related appliances and counselling are not covered. "
    "Cancer preventive surgery is not covered."
)


@pytest.mark.parametrize("text", [APRIL_DENTAL, APRIL_OPTICAL, APRIL_CANCER])
def test_a_covered_benefit_is_not_erased_by_an_exclusion_inside_it(text):
    """The regression that reached a client.

    "Orthodontics are not covered" is a detail of a dental benefit the client
    has. Reading it as the verdict told them they had no dental cover at all,
    and the display rule then deleted the EUR 1,000 limit along with it.
    """
    assert classify(text) != NOT_COVERED
    # The cover itself has to survive to the page.
    assert display_text(text) == text
    assert mark(text)["allows_detail"] is True


def test_the_opening_clause_still_decides_a_real_absence():
    assert classify("Not covered on this quotation.") == NOT_COVERED
    assert display_text("Not covered on this quotation.") == "Not covered"
    assert classify("Excluded. The wording lists this under general exclusions.") == NOT_COVERED


def test_an_unresolved_benefit_asks_rather_than_guessing():
    """"Unclear ... may be covered, depending on underwriting" is a question
    for the insurer, not an absence and not a cap. The reader needs the
    sentence, so the state has to be one that keeps it."""
    text = ("Unclear. The guide says treatment for chronic, congenital and hereditary "
            "conditions 'may be covered, depending on underwriting'. No separate chronic "
            "benefit limit is stated.")
    assert classify(text) == ACTION
    assert display_text(text) == text


def test_the_benefit_keeps_its_figures():
    """What the client is actually buying is in the numbers, and the whole
    failure was that the numbers were thrown away."""
    assert "EUR 1,000" in display_text(APRIL_DENTAL)
    assert "EUR 200" in display_text(APRIL_OPTICAL)
    assert "100%" in display_text(APRIL_CANCER)
