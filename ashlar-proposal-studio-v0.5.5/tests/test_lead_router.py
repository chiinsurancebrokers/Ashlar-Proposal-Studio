from core.lead_router import GENERALI, INTERNATIONAL, MIXED, draft_reply, route

LEAD_FAMILY = """Hello,
We are a family living in Vouliagmeni, with two adults and two children under 18, and we currently have no health insurance policy.
We would like comprehensive coverage for private hospitals, private doctors, specialists, diagnostic tests and emergency visits, including cases where hospital admission is not required.
Our priority is freedom to choose our doctors and private hospitals, with direct payment wherever possible and no requirement to use public hospitals or rely on EOPYY.
Please send us suitable options with low or zero deductibles, the participating hospital list, and details of reimbursement for doctors outside your network. Please also explain any waiting periods, exclusions and annual coverage limits.
Let me know what information you need to prepare a family quotation."""

LEAD_COUPLE = """Dear Generali Team,
I would like to request a quotation for comprehensive private health insurance for two adults, currently residing in Voula, Greece.
We are interested in your Life On Premium / Medical Prime plan, or the closest comparable comprehensive medical insurance plan available.
Could you please provide details regarding:
* Hospitalisation and inpatient coverage
* Outpatient consultations and specialist visits
* Diagnostic tests and examinations
* Direct billing with private hospitals in Greece
* International / overseas medical coverage
* Treatment of pre-existing conditions
* Waiting periods
Kind regards"""


def ids(r):
    return {h.rule for h in r.hits}


def test_family_lead_goes_mixed_with_the_right_gaps():
    r = route(LEAD_FAMILY)
    assert r.track == MIXED and r.afm == "unknown"
    assert {"free_doctor_choice", "enriched_outpatient", "zero_deductible"} <= ids(r)
    assert "no_waiting_periods" not in ids(r)  # asking to explain waiting periods is not asking to waive them


def test_couple_lead_flags_overseas_but_not_direct_billing_in_greece():
    r = route(LEAD_COUPLE)
    assert r.track == MIXED and r.asked_for_life_on
    assert "cover_abroad" in ids(r)
    abroad = next(h for h in r.hits if h.rule == "cover_abroad")
    assert "overseas" in abroad.evidence.lower()


def test_plain_life_on_lead_stays_with_generali():
    r = route("Hi, I live in Athens and have an AFM. I would like a quote for hospital cover for myself, age 40.")
    assert r.track == GENERALI and r.afm == "has" and not r.gaps


def test_diagnostics_alone_is_a_review_not_a_gap():
    r = route("I need hospital cover and also diagnostic tests. I have a Greek AFM.")
    assert r.track == GENERALI and [h.rule for h in r.reviews] == ["diagnostics"]


def test_no_afm_makes_generali_impossible():
    for text in ("I do not have a Greek AFM yet.", "We don't have an AFM.", "I am a non-resident.", "No valid Greek tax number."):
        assert route(text + " I want hospital cover.").track == INTERNATIONAL, text


def test_waiver_and_zero_deductible_requests():
    r = route("I want no waiting periods and zero deductible. I have an AFM.")
    assert {"no_waiting_periods", "zero_deductible"} <= ids(r)


def test_draft_never_invents_facts_and_asks_for_afm_when_unknown():
    d = draft_reply(route(LEAD_FAMILY))
    assert "Greek AFM" in d and "commission" in d and "no fee" not in d
    g = draft_reply(route("I live in Athens and have an AFM. I want hospital cover."))
    assert "[CONFIRM" in g  # the participation rule in the quote must be checked against the applicant's own quote


def test_international_draft_does_not_pitch_life_on():
    d = draft_reply(route("I have no AFM. I want hospital cover."))
    assert "Life On is" not in d and "not an option" in d


def test_mixed_draft_uses_the_quote_figures_and_the_brokers_structure():
    d = draft_reply(route(LEAD_FAMILY), name="Julian")
    assert d.startswith("Dear Julian,") and "Medical Prime" in d
    assert "Unlimited scheduled visits to partner doctors, €10 per visit" in d  # the maximum visits in the quote
    assert "Hygeia" in d and "Euromedica" in d and "€300,000" in d
    assert "one month after the start" in d and "ten years" in d
    assert "not reimbursed" not in d and "[CONFIRM" in d
    assert d.rstrip().endswith("Protection built for the life you live.")


def test_on_demand_waiting_table_has_both_languages():
    from core import waiting_periods as wp
    assert [wp.rows(wp.ON_DEMAND, "en")[i][0][:6] for i in range(2)] == ["Dental", "Aesthe"]
    assert all(wp.rows(wp.ON_DEMAND, "el"))
