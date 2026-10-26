from decimal import Decimal

from core.benefit_state import COVERED, NOT_COVERED, SUB_LIMIT, UNKNOWN
from core.family_bridge import benefit_state, offers_from_assignments, profile
from core.family_optimizer import optimise


def result(provider, plan, amount, frequency="annual", **benefits):
    return {"provider": provider, "target_plan": plan, "analysis": {
        "provider": provider, "plan_name": plan,
        "premium": {"amount": amount, "currency": "EUR", "frequency": frequency},
        "benefits": benefits}}


def test_cells_that_say_nothing_are_unknown():
    assert benefit_state("Not mentioned") == UNKNOWN
    assert benefit_state(None) == UNKNOWN
    assert benefit_state("Not specified") == UNKNOWN


def test_plain_covered_and_included_count_as_covered():
    assert benefit_state("Covered") == COVERED
    assert benefit_state("Included") == COVERED
    assert benefit_state("Not covered") == NOT_COVERED
    assert benefit_state("EUR 2,500") == SUB_LIMIT


def test_monthly_premium_becomes_a_yearly_offer():
    offers, notes = offers_from_assignments([result("Generali", "Life On", "180.82", "monthly", inpatient="Covered")],
                                            {0: ["katja"]})
    assert notes == [] and offers[0].yearly == Decimal("2169.84")
    assert offers[0].benefits["inpatient"] == COVERED and offers[0].residences == frozenset({"*"})


def test_unassigned_and_unpriced_options_are_left_out_with_a_reason():
    results = [result("A", "One", "100"), result("B", "Two", None), result("C", "Three", "50")]
    offers, notes = offers_from_assignments(results, {0: ["x"], 1: ["x"]})
    assert [o.label for o in offers] == ["A One"]
    assert len(notes) == 1 and "B Two" in notes[0] and "no readable premium" in notes[0]


def test_non_euro_premium_is_not_guessed():
    r = result("A", "One", "100")
    r["analysis"]["premium"]["currency"] = "USD"
    offers, notes = offers_from_assignments([r], {0: ["x"]})
    assert offers == [] and "USD" in notes[0]


def test_family_option_prices_everyone_at_once_and_competes_with_single_plans():
    people = [profile("m", "Mother", "Greece", {"inpatient": "Must have", "dental": "Medium"}, "High"),
              profile("s", "Student", "Germany", {"inpatient": "Must have", "dental": "Medium"}, "Normal")]
    results = [
        result("Local", "Plan", "1000", inpatient="Covered", dental="Not covered"),
        result("Intl", "Plan", "1500", inpatient="Covered", dental="Not covered"),
        result("Family", "Plan", "2000", inpatient="Covered", dental="EUR 500"),
    ]
    offers, _ = offers_from_assignments(results, {0: ["m"], 1: ["s"], 2: ["m", "s"]})
    outcome = optimise(people, offers)
    assert {s.total for s in outcome.ranked} == {Decimal("2500.00"), Decimal("2000.00")}
    assert outcome.winner.total == Decimal("2000.00")   # the family plan is cheaper and covers dental


def test_run_family_mix_end_to_end_from_screen_tables():
    from core.family_bridge import BENEFITS, run_family_mix
    people = [{"Name": "Katja", "Residence": "Greece", "Budget": "High"},
              {"Name": "Daughter", "Residence": "Germany", "Budget": "Normal"}]
    needs = [{"Benefit": BENEFITS["inpatient"], "Katja": "Must have", "Daughter": "Must have"},
             {"Benefit": BENEFITS["outpatient"], "Katja": "Medium", "Daughter": "High"},
             {"Benefit": BENEFITS["dental"], "Katja": "", "Daughter": "Low"}]
    results = [
        result("Generali", "Life On", "180.82", "monthly", inpatient="Covered", outpatient="EUR 20 per visit"),
        result("IMG", "Bronze Plus", "1338.61", inpatient="Covered"),
    ]
    outcome, profiles, notes = run_family_mix(people, needs, results, {0: ["katja"], 1: ["daughter"]},
                                              residences={0: ["Greece"]})
    assert notes == [] and [p.name for p in profiles] == ["Katja", "Daughter"]
    assert outcome.winner.total == Decimal("3508.45")
    # Generali only accepts residents of Greece, so a Generali policy that also covers the daughter is
    # out, and nothing else covers Katja
    outcome, _, _ = run_family_mix(people, needs, results, {0: ["katja", "daughter"], 1: ["daughter"]},
                                   residences={0: ["Greece"]})
    assert outcome.winner is None and outcome.infeasible == ["Katja"]


def test_missing_residence_is_reported_not_guessed():
    from core.family_bridge import profiles_from_tables
    profiles, warnings = profiles_from_tables([{"Name": "Ana", "Residence": "", "Budget": "Normal"}], [])
    assert profiles == [] and "residence is missing" in warnings[0]


def test_person_key_keeps_greek_letters_and_keeps_names_apart():
    from core.family_bridge import person_key
    assert person_key("Δεύτερη κόρη") and person_key("Κάτια") != person_key("Κατερίνα")
    assert person_key("Anna Maria") == "anna-maria"
