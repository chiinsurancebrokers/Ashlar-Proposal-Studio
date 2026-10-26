"""The optimiser must pick the family combination from the evidence, not from the adviser's habit."""
from datetime import date
from decimal import Decimal

from core.benefit_state import COVERED, NOT_COVERED, SUB_LIMIT
from core.family_mix import PersonQuote, check_scenario, Person
from core.family_optimizer import (
    HIGH, LOW, MEDIUM, MUST, Need, Offer, Profile, as_scenario, explain, offer_from_quotes, optimise, person_fit,
)

KATJA = Profile("katja", "Katja", "Greece",
                (Need("inpatient", MUST), Need("outpatient", MEDIUM), Need("diagnostics_imaging", MEDIUM),
                 Need("preventive", LOW)), budget="high")


def student(key, name):
    return Profile(key, name, "Germany",
                   (Need("inpatient", MUST), Need("outpatient", HIGH), Need("mental_health", HIGH),
                    Need("diagnostics_imaging", HIGH), Need("dental", LOW)), budget="normal")


D1, D2 = student("d1", "Daughter 1"), student("d2", "Daughter 2")
PROFILES = [KATJA, D1, D2]

IMG_BENEFITS = {"inpatient": COVERED}   # the screens show nothing else
IMG_AREA = {"Greece", "Germany"}


def q(person, insurer, plan, amount, freq="annual", **kw):
    return PersonQuote(person, insurer, plan, amount, freq, **kw)


def offers():
    generali = offer_from_quotes("generali", [q("katja", "Generali", "Life On", "180.82", "monthly")],
                                 residences={"Greece"},
                                 benefits={"inpatient": COVERED, "outpatient": SUB_LIMIT,
                                           "diagnostics_imaging": SUB_LIMIT, "preventive": COVERED})
    vumi = offer_from_quotes("vumi", [q("katja", "VUMI", "Euro Health VIP Priority", "2909.50")],
                             residences={"Greece"},
                             benefits={"inpatient": COVERED, "outpatient": NOT_COVERED,
                                       "diagnostics_imaging": COVERED, "preventive": SUB_LIMIT,
                                       "mental_health": SUB_LIMIT, "dental": SUB_LIMIT})
    img = [offer_from_quotes(f"img-{p}", [q(p, "IMG", "Global Prima Bronze Plus", "1338.61")],
                             residences=IMG_AREA, benefits=IMG_BENEFITS) for p in ("d1", "d2")]
    april = [offer_from_quotes(f"april-{p}", [q(p, "APRIL", "International", "1633.00")],
                               residences={"Germany"},
                               benefits={"inpatient": COVERED, "outpatient": NOT_COVERED,
                                         "diagnostics_imaging": NOT_COVERED, "mental_health": NOT_COVERED,
                                         "dental": NOT_COVERED}) for p in ("d1", "d2")]
    family = offer_from_quotes("img-family", [q(p, "IMG", "Global Prima Bronze Plus", "0")
                                              for p in ("katja", "d1", "d2")],
                               residences=IMG_AREA, benefits=IMG_BENEFITS, bundle_yearly="6992.28")
    return [generali, vumi, *img, *april, family]


def test_totikidis_best_combination_is_generali_plus_img():
    result = optimise(PROFILES, offers())
    assert result.winner.total == Decimal("4847.06")
    assert {o.plan_key for o in result.winner.offers} == {"Generali Life On", "IMG Global Prima Bronze Plus"}
    assert len(result.winner.offers) == 3
    assert result.robust        # holds whichever way IMG's unknown benefits turn out
    assert result.resolutions_tested >= 2


def test_every_combination_is_considered_including_the_family_policy():
    ranked = optimise(PROFILES, offers()).ranked
    # Katja has 2 options, each daughter 2 (IMG or APRIL): 2 x 2 x 2 = 8, plus the one family policy
    assert len(ranked) == 9
    assert sum(1 for s in ranked if len(s.offers) == 1) == 1


def test_family_policy_is_ranked_below_the_mix_on_cost_and_fit():
    ranked = optimise(PROFILES, offers()).ranked
    family = next(s for s in ranked if len(s.offers) == 1)
    assert family.total == Decimal("6992.28")
    assert ranked[0].utility > family.utility


def test_unknown_benefit_is_not_credited():
    img = offers()[2]
    fit = person_fit(D1, img)
    assert fit.eligible
    assert set(fit.unknown) == {"outpatient", "mental_health", "diagnostics_imaging", "dental"}
    assert fit.value == round(3 / 13, 4)


def test_must_not_covered_makes_an_offer_ineligible():
    needs_outpatient = Profile("d1", "Daughter 1", "Germany", (Need("outpatient", MUST),))
    april = offers()[4]
    fit = person_fit(needs_outpatient, april)
    assert not fit.eligible and "must have" in fit.reasons[0]


def test_residence_not_covered_makes_an_offer_ineligible():
    assert not person_fit(KATJA, offers()[4]).eligible   # APRIL accepts Germany only


def test_person_without_an_eligible_offer_is_reported():
    result = optimise([KATJA, Profile("x", "Visitor", "Spain", ())], offers())
    assert result.winner is None and result.infeasible == ["Visitor"]
    assert explain(result, [KATJA])[0].startswith("No eligible plan")


def test_unknown_that_changes_the_winner_is_named():
    p = Profile("a", "Ana", "Greece", (Need("inpatient", MUST), Need("dental", HIGH)), budget="normal")
    cheap = Offer("w", "W Plan", "W Plan", ("a",), Decimal("1000"), frozenset({"greece"}),
                  {"inpatient": COVERED, "dental": NOT_COVERED})
    dear = Offer("c", "C Plan", "C Plan", ("a",), Decimal("1100"), frozenset({"greece"}),
                 {"inpatient": COVERED})   # dental not shown
    result = optimise([p], [cheap, dear])
    assert result.winner.label.startswith("W Plan")
    assert not result.robust
    assert [(f.plan_key, f.benefit, f.new_winner.split(" (")[0]) for f in result.flips] == [("C Plan", "dental", "C Plan")]
    assert any("Confirm before recommending" in line for line in explain(result, [p]))


def test_budget_cap_ranks_over_budget_combinations_last():
    result = optimise(PROFILES, offers(), budget_cap="5000")
    assert not result.winner.over_budget and result.winner.total <= Decimal("5000")
    assert result.ranked[-1].over_budget


def test_cost_sensitivity_changes_the_answer():
    # With cost not mattering, the better-covered VUMI plan beats Generali for Katja on fit alone.
    katja = Profile("katja", "Katja", "Greece", KATJA.needs, budget="low")
    solo = [o for o in offers() if o.persons == ("katja",)]
    result = optimise([katja], solo)
    assert result.winner.label.startswith("Generali")   # fit 0.80 against 0.70 and cheaper
    pricey = Offer("g2", "Generali Life On", "Generali Life On", ("katja",), Decimal("2169.84"),
                   frozenset({"greece"}), {"inpatient": COVERED})
    assert optimise([katja], [pricey, solo[1]]).winner.label.startswith("VUMI")


def test_frontier_keeps_only_undominated_combinations():
    result = optimise(PROFILES, offers())
    totals = [s.total for s in result.frontier]
    assert totals == sorted(totals)
    for s in result.frontier:
        assert not any(o.total <= s.total and o.fit >= s.fit and (o.total < s.total or o.fit > s.fit)
                       for o in result.ranked)


def test_winner_scenario_feeds_the_broker_checks():
    scenario = as_scenario(optimise(PROFILES, offers()).winner)
    assert scenario is not None and scenario.total == Decimal("4847.06")
    people = [Person("katja", "Katja", 55), Person("d1", "Daughter 1", 19), Person("d2", "Daughter 2", 18)]
    codes = {f.code for f in check_scenario(scenario, people, today=date(2026, 10, 21))}
    assert "age_not_shown" in codes


def test_fit_order_puts_the_best_match_first_even_when_it_costs_more():
    cheap = offer_from_quotes("cheap", [q("katja", "Cheap", "Basic", "100", "monthly")], residences={"Greece"},
                              benefits={"inpatient": SUB_LIMIT, "outpatient": NOT_COVERED,
                                        "diagnostics_imaging": NOT_COVERED, "preventive": COVERED})
    full = offer_from_quotes("full", [q("katja", "Full", "Plus", "3000")], residences={"Greece"},
                             benefits={"inpatient": COVERED, "outpatient": COVERED,
                                       "diagnostics_imaging": COVERED, "preventive": COVERED})
    by_fit = optimise([KATJA], [cheap, full], order="fit")
    assert by_fit.ranked[0].fit >= by_fit.ranked[1].fit
    assert by_fit.winner.offers[0].label.endswith("Plus")
