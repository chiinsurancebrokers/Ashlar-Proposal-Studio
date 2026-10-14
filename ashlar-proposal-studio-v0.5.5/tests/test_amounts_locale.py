"""Decimal-comma regression: APRIL quotes print €6840,91, which used to become 684091."""
import pytest

from core.amounts import annual_factor, canonical_amount, parse_amount
from core.carriers import generic_quote_facts
from core.client_analysis import _derived_decision_facts, _number_from_text


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("6840,91", 6840.91),
        ("€6840,91 Incl Tax", 6840.91),
        ("570,08", 570.08),
        ("6,840.91", 6840.91),
        ("6.840,91", 6840.91),
        ("1,500,000", 1500000.0),
        ("1.500.000", 1500000.0),
        ("1,500", 1500.0),
        ("8727.32", 8727.32),
        ("598", 598.0),
        ("0,50", 0.5),
        ("1'234.50", 1234.5),
        ("1,500,000.", 1500000.0),
        (2400, 2400.0),
        ("Not specified", None),
        (None, None),
    ],
)
def test_parse_amount(raw, expected):
    assert parse_amount(raw) == expected


def test_canonical_amount_keeps_decimals():
    assert canonical_amount("6840,91") == "6840.91"
    assert canonical_amount("1,500,000") == "1500000"
    assert canonical_amount("8727.32") == "8727.32"


# Layout as PyMuPDF extracts it from the APRIL MyHealth International quote
# (personal details removed).
APRIL_TEXT = """Your Quote MyHealth International
Cover zone: Worldwide excluding USA
Summary of your selection
Essential
Explore
Monthly Premium*
€570,08 Incl Tax
€414,68 Incl Tax
Annual Premium*
€6840,91 Incl Tax
€4976,17 Incl Tax
€3 membership fee to « l'Association des Assurés April » are included.
Upper limit per year and per insured
€1,500,000
€500,000
Annual premium
€6840,91 Incl Tax
€4976,17 Incl Tax
Annual deductible
€0
€0
"""


def test_april_annual_premium_keeps_decimal_comma():
    facts = generic_quote_facts(APRIL_TEXT)
    assert facts["premium"] == {"amount": "6840.91", "currency": "EUR", "frequency": "Annual"}


def test_number_from_text_reads_decimal_comma():
    assert _number_from_text("6840,91") == 6840.91
    assert _number_from_text("€1,500,000 per insured per insurance year") == 1500000.0
    assert _number_from_text("€1.234,56") == 1234.56


@pytest.mark.parametrize(
    "freq, factor",
    [("Annual", 1), ("annually", 1), ("", 1), (None, 1), ("monthly", 12), ("per month", 12),
     ("Quarterly", 4), ("Semi-annual", 2), ("half-yearly", 2), ("weekly-ish", None)],
)
def test_annual_factor(freq, factor):
    assert annual_factor(freq) == factor


def test_premium_ranking_annualises_monthly_quotes():
    payload = {
        "plans": [
            {"provider": "Bupa Global", "plan_name": "Select",
             "premium": {"amount": "598", "currency": "EUR", "frequency": "monthly"}},
            {"provider": "APRIL International Care France", "plan_name": "MyHealth International Essential",
             "premium": {"amount": "6840.91", "currency": "EUR", "frequency": "Annual"}},
        ]
    }
    facts = _derived_decision_facts(payload)
    # €598 x 12 = €7,176 per year, so APRIL Essential is the cheaper annual premium.
    assert facts["lowest_premium"]["plan"].startswith("APRIL")
    assert facts["highest_premium"] == {"plan": "Bupa Global - Select", "amount": 7176.0}


def test_annual_premium_column_values():
    from core.amounts import annual_premium_display

    assert annual_premium_display({"amount": "598", "currency": "EUR", "frequency": "monthly"}) == "EUR 7,176.00 (598 × 12)"
    assert annual_premium_display({"amount": "570.08", "currency": "EUR", "frequency": "Monthly"}) == "EUR 6,840.96 (570.08 × 12)"
    assert annual_premium_display({"amount": "6840.91", "currency": "EUR", "frequency": "Annual"}) == "EUR 6,840.91"
    assert annual_premium_display({"amount": "Not specified", "currency": "EUR", "frequency": "Annual"}) == "—"
    assert annual_premium_display({"amount": "100", "currency": "EUR", "frequency": "fortnightly"}) == "—"
    assert annual_premium_display(None) == "—"
