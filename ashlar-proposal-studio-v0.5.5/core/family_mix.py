"""Family mix: give each insured person their own quote, then total every combination.

A household does not have to sit on one insurer. A parent in Greece can take a local plan
while students abroad take an international one. This module is deterministic: it holds
the per-person quotes the broker has entered, builds each combination (a scenario), totals
it, sorts it by one stated criterion and lists the checks the broker must clear first.
It never estimates a price. A price that stands in for a missing quote is labelled.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from itertools import product
from typing import Iterable

from core.amounts import annual_factor

CENT = Decimal("0.01")

# Flag severities, most serious first.
BLOCKING, REVIEW, INFO = "blocking", "review", "info"
_ORDER = {BLOCKING: 0, REVIEW: 1, INFO: 2}


def _money(value: Decimal | float | int | str) -> Decimal:
    return Decimal(str(value)).quantize(CENT, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class Person:
    key: str                      # stable id, e.g. "katja"
    name: str
    age: int | None = None
    residence: str = ""


@dataclass(frozen=True)
class PersonQuote:
    """One insurer price for one person, as the insurer quoted it."""

    person: str                   # Person.key
    insurer: str
    plan: str
    amount: Decimal               # the amount as quoted, taxes included
    frequency: str = "annual"     # frequency of that amount: annual, semiannual, quarterly, monthly
    excess: Decimal | None = None  # deductible / excess the price was calculated for
    participation: Decimal | None = None  # separate cost share that is not an excess (e.g. a hospital participation)
    area: str = ""
    age: int | None = None        # age the insurer priced; None when the quote does not show it
    start: date | None = None
    valid_until: date | None = None
    source: str = ""
    stand_in: bool = False        # True when this price stands in for a quote the person does not have
    local: bool = False           # a local (Greek) plan rather than an international one

    def __post_init__(self) -> None:
        object.__setattr__(self, "amount", _money(self.amount))
        if annual_factor(self.frequency) is None:
            raise ValueError(f"Unknown payment frequency: {self.frequency!r}")

    @property
    def yearly(self) -> Decimal:
        return _money(self.amount * annual_factor(self.frequency))

    @property
    def label(self) -> str:
        return f"{self.insurer} {self.plan}".strip()


@dataclass(frozen=True)
class Flag:
    severity: str
    code: str
    message: str
    persons: tuple[str, ...] = ()


@dataclass(frozen=True)
class Scenario:
    """One quote per person. ``total`` is the yearly cost of the whole household."""

    quotes: tuple[PersonQuote, ...]

    @property
    def total(self) -> Decimal:
        return sum((q.yearly for q in self.quotes), Decimal("0.00"))

    @property
    def monthly(self) -> Decimal:
        """Yearly total divided by 12. Real instalments follow each insurer's payment option."""
        return _money(self.total / 12)

    @property
    def title(self) -> str:
        return " + ".join(f"{q.label} ({q.person})" for q in self.quotes)


def build_scenarios(people: Iterable[Person], options: dict[str, list[PersonQuote]]) -> list[Scenario]:
    """Every combination of one option per person, lowest yearly total first.

    A person with no option makes the household incomplete, so no scenario is built.
    Ties keep the order the broker entered the options.
    """
    people = list(people)
    pools = []
    for person in people:
        pool = [q for q in options.get(person.key, []) if q.person == person.key]
        if not pool:
            return []
        pools.append(pool)
    scenarios = [Scenario(tuple(combo)) for combo in product(*pools)]
    return sorted(scenarios, key=lambda s: s.total)


def _distinct(values: Iterable) -> list:
    seen: list = []
    for value in values:
        if value not in seen:
            seen.append(value)
    return seen


def check_scenario(scenario: Scenario, people: Iterable[Person], *, today: date | None = None) -> list[Flag]:
    """Flags the broker must clear before a scenario goes into a client study."""
    today = today or date.today()
    by_key = {p.key: p for p in people}
    flags: list[Flag] = []

    for q in scenario.quotes:
        person = by_key.get(q.person)
        who = person.name if person else q.person
        if q.stand_in:
            flags.append(Flag(BLOCKING, "stand_in",
                              f"{who}: the price for {q.label} is a stand-in, not a quote of their own.", (q.person,)))
        if q.valid_until and q.valid_until < today:
            flags.append(Flag(BLOCKING, "expired",
                              f"{who}: the {q.label} quote expired on {q.valid_until.isoformat()}.", (q.person,)))
        if q.age is None:
            flags.append(Flag(REVIEW, "age_not_shown",
                              f"{who}: the {q.label} quote does not show the age it was priced for.", (q.person,)))
        elif person and person.age is not None and q.age != person.age:
            flags.append(Flag(REVIEW, "age_mismatch",
                              f"{who}: {q.label} was priced for age {q.age}; the household record says {person.age}.",
                              (q.person,)))
        if q.participation:
            flags.append(Flag(INFO, "participation",
                              f"{who}: {q.label} carries a participation of {q.participation} a year, so its price "
                              f"is not like for like with a nil-excess quote.", (q.person,)))
        if annual_factor(q.frequency) != 1:
            flags.append(Flag(INFO, "yearly_derived",
                              f"{who}: the {q.label} yearly figure is the quoted {q.frequency} amount multiplied "
                              f"by {annual_factor(q.frequency)}.", (q.person,)))

    excesses = _distinct(q.excess for q in scenario.quotes if q.excess is not None)
    if len(excesses) > 1:
        flags.append(Flag(REVIEW, "excess_differs",
                          "Quotes in this combination use different excess levels: "
                          + ", ".join(str(e) for e in excesses) + ".",
                          tuple(q.person for q in scenario.quotes)))
    starts = _distinct(q.start for q in scenario.quotes if q.start is not None)
    if len(starts) > 1:
        flags.append(Flag(REVIEW, "start_differs",
                          "Quotes in this combination start on different dates: "
                          + ", ".join(s.isoformat() for s in starts) + ".",
                          tuple(q.person for q in scenario.quotes)))
    return sorted(flags, key=lambda f: _ORDER[f.severity])


def check_household(people: Iterable[Person], options: dict[str, list[PersonQuote]]) -> list[Flag]:
    """Flags that do not depend on a combination: who has no quote of their own."""
    flags: list[Flag] = []
    for person in people:
        pool = options.get(person.key, [])
        if not pool:
            flags.append(Flag(BLOCKING, "no_quote", f"{person.name}: no quote entered.", (person.key,)))
        elif all(q.stand_in for q in pool):
            flags.append(Flag(BLOCKING, "only_stand_in",
                              f"{person.name}: every price is a stand-in. Request a quote of their own.",
                              (person.key,)))
    return flags


def can_release(flags: Iterable[Flag], *, broker_reviewed: bool) -> bool:
    """A study reaches a customer only after broker review and with no blocking flag open."""
    return broker_reviewed and not any(f.severity == BLOCKING for f in flags)


def difference(a: Scenario, b: Scenario) -> Decimal:
    """Yearly cost of ``b`` minus yearly cost of ``a``."""
    return _money(b.total - a.total)


@dataclass
class FamilyMix:
    """The case: household, the options entered for each person, and the criterion used to sort."""

    people: list[Person]
    options: dict[str, list[PersonQuote]] = field(default_factory=dict)
    criterion: str = "yearly total, lowest first"
    broker_reviewed: bool = False

    def scenarios(self) -> list[Scenario]:
        return build_scenarios(self.people, self.options)

    def flags(self, scenario: Scenario | None = None, *, today: date | None = None) -> list[Flag]:
        out = check_household(self.people, self.options)
        if scenario is not None:
            out += check_scenario(scenario, self.people, today=today)
        return sorted(out, key=lambda f: _ORDER[f.severity])

    def releasable(self, scenario: Scenario, *, today: date | None = None) -> bool:
        return can_release(self.flags(scenario, today=today), broker_reviewed=self.broker_reviewed)
