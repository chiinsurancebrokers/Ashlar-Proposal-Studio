from core.amounts import annual_premium_display
from core.carriers import now_health_quote_facts

# PDF text order: every label first, then every value.
QUOTE = """Plan Selected:
In/Day-Patient Annual
Deductible:
Area of Coverage Selected:
SimpleCare 100
11/11/2026
Full Medical Underwriting
Greece
Europe
SimpleCare Europe
EUR 400
No Out-Patient Options
Payment frequency: Month
Final Total Premium: EUR 202.08
Standard Deductible
USD 500/EUR 400/GBP 310
Regional Cover: Europe
Region of Cover: Worldwide Excluding USA
"""


def test_monthly_quote_is_not_read_as_annual():
    f = now_health_quote_facts(QUOTE)
    assert f["premium"] == {"amount": "202.08", "currency": "EUR", "frequency": "Monthly"}
    assert annual_premium_display(f["premium"]).startswith("EUR 2,424.96")


def test_deductible_is_the_quoted_euro_amount_and_scoped_to_inpatient():
    f = now_health_quote_facts(QUOTE)
    assert "€400" in f["deductible_or_excess"]
    assert "$500" not in f["deductible_or_excess"]
    assert "in-patient and day-patient" in f["deductible_or_excess"]


def test_selected_area_is_not_taken_from_the_options_table():
    f = now_health_quote_facts(QUOTE)
    assert f["area_of_cover"] == "Europe"
    assert not f.get("fact_warnings")


def test_missing_frequency_is_flagged():
    f = now_health_quote_facts(QUOTE.replace("Payment frequency: Month\n", ""))
    assert f["premium"]["frequency"] == "Annual"
    assert any("frequency" in w.lower() for w in f["fact_warnings"])
