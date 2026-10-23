"""Totikidis family: a mother on a local plan, two students on an international one."""
from datetime import date
from decimal import Decimal

import pytest

from core.family_mix import (
    BLOCKING, REVIEW, FamilyMix, Person, PersonQuote, build_scenarios, can_release,
    check_household, check_scenario, difference,
)

TODAY = date(2026, 10, 21)

KATJA = Person("katja", "Katja", age=55, residence="Greece")
D1 = Person("d1", "Daughter 1", age=19, residence="Germany")
D2 = Person("d2", "Daughter 2", age=18, residence="Germany")
PEOPLE = [KATJA, D1, D2]


def generali():
    return PersonQuote("katja", "Generali", "Life On", "180.82", "monthly", excess=None,
                       participation=Decimal("1500"), area="Greece", age=55,
                       valid_until=date(2026, 11, 20), source="Study 08547587", local=True)


def vumi():
    return PersonQuote("katja", "VUMI", "Euro Health VIP Priority", "2909.50", "annual", excess=Decimal("0"),
                       area="European Union", age=56, start=date(2026, 11, 1), source="Quote 21/10/2026")


def img(person, **kw):
    base = dict(excess=Decimal("0"), area="Europe", start=date(2026, 10, 22), source="IMG screen 21/10/2026")
    base.update(kw)
    return PersonQuote(person, "IMG", "Global Prima Medical Bronze Plus", "1338.61", "annual", **base)


def case():
    return FamilyMix(PEOPLE, {"katja": [vumi(), generali()], "d1": [img("d1")], "d2": [img("d2")]})


def test_monthly_quote_gives_yearly_total():
    assert generali().yearly == Decimal("2169.84")


def test_scenarios_total_and_sort_lowest_first():
    scenarios = case().scenarios()
    assert [s.total for s in scenarios] == [Decimal("4847.06"), Decimal("5586.72")]
    assert scenarios[0].quotes[0].insurer == "Generali"
    assert [s.monthly for s in scenarios] == [Decimal("403.92"), Decimal("465.56")]
    assert difference(scenarios[0], scenarios[1]) == Decimal("739.66")


def test_no_scenario_when_someone_has_no_quote():
    options = {"katja": [generali()], "d1": [img("d1")]}
    assert build_scenarios(PEOPLE, options) == []
    flags = check_household(PEOPLE, options)
    assert [(f.code, f.persons) for f in flags] == [("no_quote", ("d2",))]
    assert flags[0].severity == BLOCKING


def test_totikidis_flags_age_start_and_participation():
    mix = case()
    generali_scenario, vumi_scenario = mix.scenarios()
    g = {f.code for f in check_scenario(generali_scenario, PEOPLE, today=TODAY)}
    assert {"age_not_shown", "participation"} <= g
    v = {f.code for f in check_scenario(vumi_scenario, PEOPLE, today=TODAY)}
    # VUMI priced Katja at 56 while the household record (Generali date of birth) says 55
    assert "age_mismatch" in v
    # VUMI starts 01/11/2026 while the IMG screens run from 22/10/2026
    assert "start_differs" in v


def test_stand_in_is_blocking_and_labelled():
    stand_in = img("d2", stand_in=True)
    mix = FamilyMix(PEOPLE, {"katja": [generali()], "d1": [img("d1")], "d2": [stand_in]})
    scenario = mix.scenarios()[0]
    flags = check_scenario(scenario, PEOPLE, today=TODAY)
    assert any(f.code == "stand_in" and f.severity == BLOCKING for f in flags)
    assert any(f.code == "only_stand_in" for f in check_household(PEOPLE, mix.options))
    mix.broker_reviewed = True
    assert not mix.releasable(scenario, today=TODAY)


def test_expired_quote_is_blocking():
    flags = check_scenario(case().scenarios()[0], PEOPLE, today=date(2026, 11, 21))
    assert any(f.code == "expired" and f.severity == BLOCKING for f in flags)


def test_different_excess_in_one_combination_is_flagged():
    katja_500 = PersonQuote("katja", "IMG", "Global Prima Medical Bronze Plus", "301.27", "monthly",
                            excess=Decimal("500"), area="Europe", age=55)
    mix = FamilyMix(PEOPLE, {"katja": [katja_500], "d1": [img("d1")], "d2": [img("d2")]})
    scenario = mix.scenarios()[0]
    assert scenario.total == Decimal("3615.24") + Decimal("2677.22")
    flags = check_scenario(scenario, PEOPLE, today=TODAY)
    assert any(f.code == "excess_differs" and f.severity == REVIEW for f in flags)
    assert any(f.code == "yearly_derived" for f in flags)


def test_release_needs_broker_review_and_no_blocking_flag():
    mix = case()
    scenario = mix.scenarios()[0]
    flags = mix.flags(scenario, today=TODAY)
    assert not any(f.severity == BLOCKING for f in flags)
    assert not can_release(flags, broker_reviewed=False)
    assert can_release(flags, broker_reviewed=True)


def test_unknown_frequency_is_rejected():
    with pytest.raises(ValueError):
        PersonQuote("katja", "X", "Y", "100", "fortnightly")
