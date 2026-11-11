from core.report_html import build_html
from core.report_pdf import build_pdf_bytes


def _opt(provider, plan, amount, freq, deductible):
    return {"provider": provider, "target_plan": plan,
            "analysis": {"provider": provider, "plan_name": plan, "premium": {"amount": amount, "currency": "EUR", "frequency": freq},
                         "deductible_or_excess": deductible, "area_of_cover": "Europe", "annual_limit": "€1,000,000"}}


RESULTS = [
    _opt("VUMI", "Priority", "3878.95", "Annual", "€2,500 deductible"),
    _opt("IMG", "Bronze Plus", "456.72", "Monthly", "€300 deductible"),
]


def test_html_shows_the_section_with_totals_and_the_ranking_change():
    html = build_html(client_analysis={}, results=RESULTS)
    assert "id='claim-cost'" in html
    assert "€6,378.95" in html and "€5,780.64" in html
    assert "On premium alone, VUMI" in html and "IMG" in html


def test_greek_report_uses_greek_labels():
    html = build_html(client_analysis={}, results=RESULTS, language="Greek")
    assert "Πόσο κοστίζει ένα έτος με αποζημίωση" in html


def test_section_is_left_out_when_there_is_nothing_to_add():
    one_missing = [_opt("A", "x", "100", "Monthly", "Not specified"), _opt("B", "y", "100", "Monthly", "Not specified")]
    assert "claim-cost" not in build_html(client_analysis={}, results=one_missing)


def test_pdf_builds_with_the_section():
    data = build_pdf_bytes(client_analysis={}, results=RESULTS)
    assert data[:4] == b"%PDF" and len(data) > 5000
