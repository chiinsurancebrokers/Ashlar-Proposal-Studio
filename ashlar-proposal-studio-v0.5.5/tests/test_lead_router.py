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
* Emergency treatment and day surgery
* Direct billing with private hospitals in Greece
* International / overseas medical coverage
* Annual health check-ups and preventive care
* Prescription medication coverage
* Annual premium
* Deductible options
* Coverage limits
* Waiting periods
* Treatment of pre-existing conditions
* Renewal terms and age limits
* Medical underwriting requirements
* Earliest possible policy start date

Please let us know what information or documents you require in order to prepare the quotation.
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
    assert d.startswith("Dear Julian,") and "Medical Prime" not in d  # he did not ask for it
    assert "four visits a year to a doctor of your own choice" in d  # Life On is promoted when no plan is named
    assert "€620,000" in d and "€0, €750" in d and "Hygeia" in d and "€300,000" not in d
    assert "first three months of the first year" in d
    assert "not reimbursed" not in d and "[CONFIRM" in d
    assert d.rstrip().endswith("Protection built for the life you live.")


def test_on_demand_waiting_table_has_both_languages():
    from core import waiting_periods as wp
    assert [wp.rows(wp.ON_DEMAND, "en")[i][0][:6] for i in range(2)] == ["Dental", "Aesthe"]
    assert all(wp.rows(wp.ON_DEMAND, "el"))


def test_every_request_in_the_lead_is_acknowledged_and_answered_or_promised():
    from core.lead_router import coverage
    r = route(LEAD_FAMILY)
    assert {"hospital_list", "out_of_network", "waiting_periods", "exclusions", "annual_limits", "deductibles", "direct_billing", "info_needed"} <= set(r.requests)
    assert "renewal_age" not in r.requests  # "coverage limits" must not read as "age limits"
    d = draft_reply(r, name="Julian")
    assert "You asked about" in d and "the participating hospital list" in d
    assert "deductible options" in d.split("For the international options we will also provide")[1]
    assert set(coverage(r).values()) <= {"answered", "promised", "ipmi_only"} and set(coverage(r)) == set(r.requests)


def test_long_checklist_lead_gets_every_item_promised():
    from core.lead_router import coverage
    r = route(LEAD_COUPLE)
    assert {"premium", "deductibles", "annual_limits", "waiting_periods", "pre_existing", "renewal_age", "underwriting",
            "start_date", "prescriptions", "preventive", "overseas", "direct_billing"} <= set(r.requests)
    d = draft_reply(r)
    assert "detailed list of questions" in d
    promised = d.split("For the international options we will also provide")[1].split(".")[0]
    for phrase in ("the annual premium", "renewal terms and age limits", "the earliest possible start date", "prescription cover", "overseas cover"):
        assert phrase in promised
    assert coverage(r)["premium"] == "promised"


def test_acknowledgement_is_short_and_asks_the_afm_question_once():
    from core.lead_router import draft_acknowledgement
    a = draft_acknowledgement(route(LEAD_FAMILY), name="Julian")
    assert a.startswith("Dear Julian,") and "I have received it" in a and a.count("Greek AFM") == 1
    assert len(a.splitlines()) < 22
    assert "Greek AFM" not in draft_acknowledgement(route("I have no AFM. I want hospital cover."))


def test_generali_side_never_promises_what_its_wording_does_not_offer():
    from core.generali_plans import wording_for
    from core.lead_router import generali_promises, coverage
    for lead in (LEAD_FAMILY, LEAD_COUPLE):
        r = route(lead)
        GENERALI_WORDING = wording_for(r.plans)
        promised = generali_promises(r)
        # nothing the wording does not offer, and nothing partial, is promised for Generali
        assert all(GENERALI_WORDING[x][0] in ("wording", "confirm") for x in promised)
        d = draft_reply(r)
        gen = [ln for ln in d.splitlines() if ln.startswith(("For the Generali option", "I will confirm"))]
        for banned in ("out-of-network", "prescription", "overseas", "worldwide"):
            assert not any(banned in ln for ln in gen), (banned, gen)
        assert "For each option we will provide" not in d
    assert coverage(route(LEAD_FAMILY))["out_of_network"] == "answered"  # Life On reimburses four own-choice visits
    from core.generali_plans import MEDICAL_PRIME
    assert coverage(route("Medical Prime please. Reimbursement for any doctor. I have an AFM."))["out_of_network"] == "ipmi_only"
    assert coverage(route(LEAD_COUPLE))["prescriptions"] == "ipmi_only"


def test_every_request_has_a_generali_position():
    from core.generali_plans import PLAN_WORDING
    from core.lead_router import REQUEST_RULES
    for plan, table in PLAN_WORDING.items():
        assert {rid for rid, *_ in REQUEST_RULES} <= set(table), plan


def test_plans_are_kept_apart_and_only_named_plans_appear():
    from core.generali_plans import LIFE_ON, MEDICAL_PRIME, LIFE_ON_PARTICIPATION, wording_for
    assert route(LEAD_FAMILY).plans == [] and route(LEAD_COUPLE).plans == [LIFE_ON, MEDICAL_PRIME]
    assert LIFE_ON_PARTICIPATION == (0, 750, 1500, 3000, 5000, 10000)
    # the doctors-outside-the-network position differs by plan
    assert wording_for([LIFE_ON])["out_of_network"][0] == "partial"
    assert wording_for([MEDICAL_PRIME])["out_of_network"][0] == "not_offered"
    both = wording_for([LIFE_ON, MEDICAL_PRIME])["out_of_network"]
    assert both[0] == "partial" and "Life On:" in both[1] and "Medical Prime:" in both[1]
    assert wording_for([LIFE_ON])["direct_billing"][0] == "wording"
    d_life = draft_reply(route("I want Life On hospital cover and free choice of doctors. I have an AFM."))
    assert "€620,000" in d_life and "€300,000" not in d_life and "Medical Prime" not in d_life
    d_both = draft_reply(route(LEAD_COUPLE))
    assert "Life On:" in d_both and "Medical Prime:" in d_both and "€620,000" in d_both and "€300,000" in d_both


def test_zero_deductible_is_not_a_reason_to_leave_generali():
    r = route("I have a Greek AFM and want hospital cover with zero deductible.")
    assert r.track == GENERALI and [h.rule for h in r.reviews] == ["zero_deductible"]
    d = draft_reply(route("I have a Greek AFM, free choice of doctors and zero deductible."))
    assert "€0, €750" in draft_reply(route("Life On please, free choice of doctors, zero deductible. I have an AFM."))
    assert "I will also check the policy wording on: nil" not in d


def test_lead_with_foreign_hospital_abroad_is_told_no_direct_billing_abroad_for_medical_prime():
    from core.generali_plans import MEDICAL_PRIME, wording_for
    assert "no direct billing abroad" in wording_for([MEDICAL_PRIME])["overseas"][1]


def test_every_track_says_why_the_lead_reached_ashlar_without_implying_a_tie_to_generali():
    for text in (LEAD_FAMILY, "I have no AFM. I want hospital cover.", "I live in Athens and have an AFM. I want hospital cover."):
        d = draft_reply(route(text))
        assert "independent insurance intermediary" in d and "not employed by Generali" in d
        assert "no employment relationship" in d and "we are responsible for the advice and service we give you" in d and "registry no. 191526" in d and "licensed" not in d and "Award in General Insurance (March 2025)" in d
        for banned in ("on behalf of Generali", "our Generali team", "I handle English-language enquiries for Generali", "passed to me"):
            assert banned not in d


def test_life_on_screen_options_are_recorded():
    from core.generali_plans import LIFE_ON_HOSPITAL_CAPITAL, LIFE_ON_HOSPITAL_ROOMS, LIFE_ON_LIFE_CAPITAL
    assert LIFE_ON_HOSPITAL_CAPITAL == (620000, 940000, 1240000) and LIFE_ON_HOSPITAL_ROOMS == ("A", "B")
    assert LIFE_ON_LIFE_CAPITAL == (500, 10000, 20000, 30000, 50000)
    assert "€940,000" in draft_reply(route("Life On please, free choice of doctors. I have an AFM."))
