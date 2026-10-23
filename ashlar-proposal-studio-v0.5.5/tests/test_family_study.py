import re
from datetime import date

from core.benefit_state import COVERED, NOT_COVERED, SUB_LIMIT
from core.family_bridge import offers_from_assignments, profile
from core.family_optimizer import optimise
from core.family_study import render_family_study


def _outcome():
    people = [profile("katja", "Katja", "Greece", {"inpatient": "Must have", "outpatient": "Medium", "dental": "Low"}, "High"),
              profile("d1", "Daughter <1>", "Germany", {"inpatient": "Must have", "outpatient": "High"}, "Normal")]
    def r(p, plan, amt, freq="annual", **b):
        return {"provider": p, "target_plan": plan, "analysis": {"provider": p, "plan_name": plan,
                "premium": {"amount": amt, "currency": "EUR", "frequency": freq}, "benefits": b}}
    results = [r("Generali", "Life On", "180.82", "monthly", inpatient="Covered", outpatient="EUR 20 per visit"),
               r("IMG", "Bronze Plus", "1338.61", inpatient="Covered")]
    offers, _ = offers_from_assignments(results, {0: ["katja"], 1: ["d1"]})
    return optimise(people, offers), people


def test_english_study_has_totals_reasons_and_fairness_lines():
    outcome, people = _outcome()
    html = render_family_study(outcome, people, lang="en", client_name="Totikidis family", on=date(2026, 10, 21))
    assert "€3,508.45" in html and "€2,169.84" in html and "€1,338.61" in html
    assert "A licensed Ashlar broker reviews every recommendation" in html
    assert "the policy wording prevails" in html
    assert "Not shown in the quote" in html           # IMG shows no outpatient benefit
    assert "21 October 2026" in html


def test_greek_study_uses_greek_numbers_dates_and_terms():
    outcome, people = _outcome()
    html = render_family_study(outcome, people, lang="el", on=date(2026, 10, 21))
    assert "€3.508,45" in html and "€2.169,84" in html
    assert "21/10/2026" in html and 'lang="el"' in html
    assert "Εξωνοσοκομειακές επισκέψεις" in html and "Δεν φαίνεται στην προσφορά" in html
    assert "αδειοδοτημένο ασφαλιστικό διαμεσολαβητή" in html
    assert "ανάληψη κινδύνου" in html


def test_names_are_escaped_and_no_winner_language():
    outcome, people = _outcome()
    html = render_family_study(outcome, people, lang="en")
    assert "Daughter &lt;1&gt;" in html and "Daughter <1>" not in html
    body = re.sub(r"<style>.*?</style>", "", html, flags=re.S).lower()
    for word in ("winner", "best plan", "#1", "★"):
        assert word not in body


def test_open_points_name_what_the_quote_does_not_show():
    outcome, people = _outcome()
    html = render_family_study(outcome, people, lang="en")
    assert "does not show" in html and "IMG Bronze Plus" in html


def test_generali_gets_hospital_waiting_table_and_rider_adds_second():
    outcome, people = _outcome()
    html = render_family_study(outcome, people, lang="en")
    assert "Hospital Premium Flexi (Article 5)" in html and "Spinal conditions" in html
    assert "Doctors &amp; Exams" not in html
    html2 = render_family_study(outcome, people, lang="en", riders={"Generali Life On": ["doctors_exams_premium"]})
    assert "Doctors &amp; Exams Premium (Article 3)" in html2 and "Knee conditions" in html2
    el = render_family_study(outcome, people, lang="el")
    assert "Παθήσεις σπονδυλικής στήλης" in el and "Περίοδοι αναμονής" in el


def test_mix_record_is_plain_data_without_amount_guesses():
    import json
    from core.family_study import mix_record
    outcome, people = _outcome()
    rec = mix_record(outcome, people, lang="el", budget_cap=4000)
    json.dumps(rec)
    assert rec["total_yearly"] == "3508.45" and rec["broker_reviewed"] is False
    assert {o["plan"] for o in rec["offers"]} == {"Generali Life On", "IMG Bronze Plus"}


def test_save_family_mix_needs_a_case(monkeypatch):
    import pytest
    from core.case_archive import CaseArchiveError, save_family_mix
    with pytest.raises(CaseArchiveError):
        save_family_mix("", {})


def _two_katja_options():
    people = [profile("katja", "Katja", "Greece", {"inpatient": "Must have", "outpatient": "Medium"}, "High")]
    def r(p, plan, amt, freq, disp=None, **b):
        return {"provider": p, "target_plan": plan, "analysis": {"provider": p, "plan_name": plan,
                "premium": {"amount": amt, "currency": "EUR", "frequency": freq}, "benefits": b, "benefit_display": disp or {}}}
    results = [r("Εθνική", "Προνομιακή Προστασία", "83.48", "monthly", {"inpatient": "Έως €1.000.000"},
                 inpatient="Up to EUR 1,000,000 per year", outpatient="Unlimited visits at EUR 10"),
               r("Generali", "Life On Standard", "116.87", "monthly", {"inpatient": "Έως €50.000"},
                 inpatient="Up to EUR 50,000 per year", outpatient="Unlimited visits at EUR 20")]
    offers, _ = offers_from_assignments(results, {0: ["katja"], 1: ["katja"]})
    return optimise(people, offers), people


def test_compare_section_shows_each_option_with_its_quoted_text():
    outcome, people = _two_katja_options()
    html = render_family_study(outcome, people, lang="el")
    assert "Σύγκριση επιλογών για Katja" in html
    assert "Έως €1.000.000" in html and "Έως €50.000" in html
    assert "€1.402,44" in html and "€1.001,76" in html


def test_combination_labels_use_names_not_keys_and_fit_uses_greek_decimals():
    outcome, people = _outcome()
    html = render_family_study(outcome, people, lang="el")
    assert "(katja)" not in html and "(d1)" not in html
    import re
    assert re.search(r"\b0,\d\d\b", html) and not re.search(r"<td class=\"num\">0\.\d\d<", html)


def test_waiting_table_follows_plan_name_and_covers_alternatives():
    outcome, people = _two_katja_options()
    html = render_family_study(outcome, people, lang="en", riders={"Generali Life On Standard": ["doctors_exams_premium"]})
    assert "Hospital Standard (Article 5)" in html and "Hospital Premium Flexi" not in html
    assert "Doctors &amp; Exams Premium (Article 3)" in html
    assert "Εθνική Προνομιακή Προστασία (offer" in html


def test_reasons_are_a_ticked_list_with_text_beside_every_mark():
    outcome, people = _outcome()
    html = render_family_study(outcome, people, lang="el")
    assert 'class="checks"' in html and "✓" in html and "–" in html
    assert 'aria-hidden="true">✓</span>Νοσοκομειακά (απαραίτητη): ' in html
    assert "Δεν φαίνεται στην προσφορά" in html and 'class="legend"' in html


def test_benefit_grid_states_the_quoted_limits():
    outcome, people = _two_katja_options()
    html = render_family_study(outcome, people, lang="el")
    grid = html.split("Τι καλύπτει κάθε πρόγραμμα")[1].split("Σύγκριση επιλογών")[0]
    assert "Έως €1.000.000" in grid
