"""Find the best combination of plans for a whole family.

Picking a plan per person by hand is cherry-picking. This module searches every way of
covering the household, scores each way against what each person needs, and says how
sure the answer is.

WHAT IT DOES
------------
1. Offers. An offer is one insurer plan with one price for one or more people. A single
   plan for one person and a family policy for three are both offers, so a family price
   competes fairly with the same insurer priced person by person.
2. Eligibility (hard rules). An offer is out for a person when it does not cover where they
   live, or when a benefit marked "must" is not covered.
3. Fit (0 to 1). Each need has a weight: must, high, medium or low. A covered benefit earns
   full credit, one that needs an action first earns 0.8, a capped one 0.6, and an excluded one
   nothing. A benefit the quote does not show earns nothing. The studio never assumes cover that
   no document shows.
4. Combinations. Every way of covering each person exactly once is built by an exact search
   (offers may cover several people), so no combination is missed.
5. Utility. Household fit minus a price penalty. The penalty is the extra cost over the cheapest
   eligible combination, scaled by how sensitive the household is to cost. Both numbers are shown,
   so the broker can see why one combination beat another.
6. Robustness. Benefits that no document shows are unknown. The module re-runs the ranking with every
   unknown benefit that matters resolved as covered or not covered, and reports which unknown
   would change the answer. That list is what the broker must confirm before recommending.

It never estimates a price. Prices come from the offers the broker entered.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from itertools import product
from typing import Iterable, Mapping

from core.benefit_state import ACTION, COVERED, NOT_COVERED, SUB_LIMIT, UNKNOWN
from core.family_mix import PersonQuote, Scenario

CENT = Decimal("0.01")
MUST, HIGH, MEDIUM, LOW = "must", "high", "medium", "low"
WEIGHT = {MUST: 3.0, HIGH: 3.0, MEDIUM: 2.0, LOW: 1.0}
CREDIT = {COVERED: 1.0, ACTION: 0.8, SUB_LIMIT: 0.6, NOT_COVERED: 0.0, UNKNOWN: 0.0}
BUDGET = {"high": 1.0, "normal": 0.5, "low": 0.2}
MAX_UNKNOWNS = 10          # 2**10 resolutions at most; beyond this the bounds are reported instead
MAX_SELECTIONS = 200_000   # guard against a runaway search


def _money(value) -> Decimal:
    return Decimal(str(value)).quantize(CENT, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class Need:
    benefit: str
    weight: str = MEDIUM


@dataclass(frozen=True)
class Profile:
    """What one person needs. ``budget`` is how much cost matters to them."""

    person: str
    name: str
    residence: str
    needs: tuple[Need, ...] = ()
    budget: str = "normal"
    importance: float = 1.0


@dataclass(frozen=True)
class Offer:
    """One plan, one price, for one or more people."""

    offer_id: str
    plan_key: str                          # insurer and plan; the same key shares unknown benefits
    label: str
    persons: tuple[str, ...]
    yearly: Decimal
    residences: frozenset[str]             # countries of residence the plan accepts; "*" means any
    benefits: Mapping[str, str] = field(default_factory=dict)  # benefit -> COVERED / SUB_LIMIT / ...
    quotes: tuple[PersonQuote, ...] = ()
    stand_in: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "yearly", _money(self.yearly))
        object.__setattr__(self, "residences", frozenset(r.casefold() for r in self.residences))


def offer_from_quotes(offer_id: str, quotes: Iterable[PersonQuote], *, residences: Iterable[str],
                      benefits: Mapping[str, str], bundle_yearly=None) -> Offer:
    """Build an offer from per-person quotes. ``bundle_yearly`` is a family price that replaces the sum."""
    quotes = tuple(quotes)
    total = _money(bundle_yearly) if bundle_yearly is not None else sum((q.yearly for q in quotes), Decimal("0"))
    first = quotes[0]
    return Offer(offer_id, f"{first.insurer} {first.plan}".strip(), f"{first.insurer} {first.plan}".strip(),
                 tuple(q.person for q in quotes), total, frozenset(residences), dict(benefits), quotes,
                 any(q.stand_in for q in quotes))


@dataclass(frozen=True)
class Fit:
    value: float
    eligible: bool
    unknown: tuple[str, ...]      # needed benefits the quote does not show
    reasons: tuple[str, ...]      # why it is ineligible, if it is


Resolution = Mapping[tuple[str, str], float]  # (plan_key, benefit) -> credit


def person_fit(profile: Profile, offer: Offer, resolved: Resolution | None = None) -> Fit:
    if "*" not in offer.residences and profile.residence.casefold() not in offer.residences:
        return Fit(0.0, False, (), (f"{offer.label} does not cover residence in {profile.residence}.",))
    earned = total = 0.0
    unknown: list[str] = []
    reasons: list[str] = []
    for need in profile.needs:
        state = offer.benefits.get(need.benefit, UNKNOWN)
        weight = WEIGHT[need.weight]
        total += weight
        if state == UNKNOWN:
            unknown.append(need.benefit)
            credit = (resolved or {}).get((offer.plan_key, need.benefit), 0.0)
        else:
            credit = CREDIT[state]
        earned += weight * credit
        if need.weight == MUST and state == NOT_COVERED:
            reasons.append(f"{offer.label} does not cover {need.benefit}, which {profile.name} must have.")
    value = earned / total if total else 1.0
    return Fit(round(value, 4), not reasons, tuple(unknown), tuple(reasons))


@dataclass(frozen=True)
class Selection:
    offers: tuple[Offer, ...]
    total: Decimal
    fits: tuple[tuple[str, float], ...]   # (person, fit)
    fit: float                            # household fit
    penalty: float
    utility: float
    unknown: tuple[tuple[str, str], ...]  # (offer label, benefit) still to confirm
    unconfirmed_must: tuple[tuple[str, str], ...]
    over_budget: bool = False

    @property
    def label(self) -> str:
        return " + ".join(o.label + (f" ({', '.join(o.persons)})" if len(self.offers) > 1 else "")
                          for o in self.offers)


@dataclass(frozen=True)
class Flip:
    """One unknown benefit whose confirmation would change which combination wins."""

    plan_key: str
    benefit: str
    resolved_as: str      # "covered" or "not covered"
    new_winner: str


@dataclass
class Result:
    ranked: list[Selection]
    frontier: list[Selection]
    winner: Selection | None
    margin: float                       # utility gap between first and second
    flips: list[Flip]
    robust: bool                        # the winner survives every resolution of the unknowns
    resolutions_tested: int
    infeasible: list[str]               # people for whom no eligible offer exists


def _partitions(order: list[str], by_person: dict[str, list[Offer]], covered: frozenset[str],
                picked: tuple[Offer, ...], out: list[tuple[Offer, ...]]) -> None:
    if len(out) >= MAX_SELECTIONS:
        return
    remaining = [p for p in order if p not in covered]
    if not remaining:
        out.append(picked)
        return
    lead = remaining[0]
    for offer in by_person.get(lead, []):
        members = frozenset(offer.persons)
        if members & covered:
            continue
        _partitions(order, by_person, covered | members, picked + (offer,), out)


def _eligible_offers(profiles: list[Profile], offers: list[Offer], resolved: Resolution | None):
    """Offers that every covered person can use, indexed by each member."""
    prof = {p.person: p for p in profiles}
    usable: list[Offer] = []
    for o in offers:
        if not o.persons or any(p not in prof for p in o.persons):
            continue
        if all(person_fit(prof[p], o, resolved).eligible for p in o.persons):
            usable.append(o)
    return usable


def _score(selection: tuple[Offer, ...], profiles: list[Profile], min_cost: Decimal, k: float,
           cap: Decimal | None, resolved: Resolution | None) -> Selection:
    prof = {p.person: p for p in profiles}
    fits: list[tuple[str, float]] = []
    unknown: list[tuple[str, str]] = []
    must_open: list[tuple[str, str]] = []
    for offer in selection:
        for person in offer.persons:
            f = person_fit(prof[person], offer, resolved)
            fits.append((person, f.value))
            for benefit in f.unknown:
                unknown.append((offer.label, benefit))
                need = next(n for n in prof[person].needs if n.benefit == benefit)
                if need.weight == MUST:
                    must_open.append((offer.label, benefit))
    importance = {p.person: p.importance for p in profiles}
    weight_sum = sum(importance[p] for p, _ in fits)
    household_fit = sum(importance[p] * v for p, v in fits) / weight_sum if weight_sum else 0.0
    total = sum((o.yearly for o in selection), Decimal("0"))
    extra = float(total / min_cost) - 1.0 if min_cost > 0 else 0.0
    penalty = k * extra
    return Selection(selection, _money(total), tuple(fits), round(household_fit, 4), round(penalty, 4),
                     round(household_fit - penalty, 4), tuple(dict.fromkeys(unknown)),
                     tuple(dict.fromkeys(must_open)), bool(cap is not None and total > cap))


def _rank(profiles: list[Profile], offers: list[Offer], cap: Decimal | None,
          resolved: Resolution | None) -> tuple[list[Selection], list[str]]:
    usable = _eligible_offers(profiles, offers, resolved)
    by_person: dict[str, list[Offer]] = {}
    for o in usable:
        for p in o.persons:
            by_person.setdefault(p, []).append(o)
    order = [p.person for p in profiles]
    missing = [p.name for p in profiles if p.person not in by_person]
    if missing:
        return [], missing
    combos: list[tuple[Offer, ...]] = []
    _partitions(order, by_person, frozenset(), (), combos)
    if not combos:
        return [], [p.name for p in profiles]
    totals = [sum((o.yearly for o in c), Decimal("0")) for c in combos]
    min_cost = min(totals)
    k = sum(BUDGET[p.budget] for p in profiles) / len(profiles)
    scored = [_score(c, profiles, min_cost, k, cap, resolved) for c in combos]
    scored.sort(key=lambda s: (s.over_budget, -s.utility, s.total, s.label))
    return scored, []


def _frontier(ranked: list[Selection]) -> list[Selection]:
    """Combinations that no other combination beats on both cost and fit."""
    out = []
    for s in ranked:
        dominated = any(o.total <= s.total and o.fit >= s.fit and (o.total < s.total or o.fit > s.fit)
                        for o in ranked)
        if not dominated:
            out.append(s)
    return sorted(out, key=lambda s: s.total)


def _unknown_keys(profiles: list[Profile], offers: list[Offer]) -> list[tuple[str, str]]:
    keys: list[tuple[str, str]] = []
    benefits = {n.benefit for p in profiles for n in p.needs}
    for o in offers:
        for b in benefits:
            if o.benefits.get(b, UNKNOWN) == UNKNOWN and (o.plan_key, b) not in keys:
                keys.append((o.plan_key, b))
    return keys


def optimise(profiles: list[Profile], offers: list[Offer], *, budget_cap=None) -> Result:
    """Rank every way of covering the household and test how firm the winner is."""
    cap = _money(budget_cap) if budget_cap is not None else None
    ranked, missing = _rank(profiles, offers, cap, None)
    if not ranked:
        return Result([], [], None, 0.0, [], True, 0, missing)
    winner = ranked[0]
    margin = round(winner.utility - ranked[1].utility, 4) if len(ranked) > 1 else winner.utility

    keys = _unknown_keys(profiles, offers)
    flips: list[Flip] = []
    tested = 0
    robust = True
    if keys and len(keys) <= MAX_UNKNOWNS:
        for values in product((0.0, 1.0), repeat=len(keys)):
            resolved = dict(zip(keys, values))
            r, _ = _rank(profiles, offers, cap, resolved)
            tested += 1
            if r and r[0].label != winner.label:
                robust = False
                # the unknowns set to covered in this run are what moved the answer
                for (plan_key, benefit), v in resolved.items():
                    if v == 1.0 and not any(f.plan_key == plan_key and f.benefit == benefit
                                            and f.new_winner == r[0].label for f in flips):
                        flips.append(Flip(plan_key, benefit, "covered", r[0].label))
    elif keys:
        robust = False  # too many unknowns to test; the broker confirms them first
    return Result(ranked, _frontier(ranked), winner, margin, _decisive(flips, profiles, offers, cap, winner),
                  robust, tested, [])


def _decisive(flips: list[Flip], profiles, offers, cap, winner: Selection) -> list[Flip]:
    """Keep only unknowns that flip the winner when resolved alone, with everything else unconfirmed."""
    decisive: list[Flip] = []
    for f in flips:
        r, _ = _rank(profiles, offers, cap, {(f.plan_key, f.benefit): 1.0})
        if r and r[0].label != winner.label:
            decisive.append(Flip(f.plan_key, f.benefit, "covered", r[0].label))
    return decisive


def explain(result: Result, profiles: list[Profile]) -> list[str]:
    """Plain reasons, one line per person plus the firmness of the answer."""
    if result.winner is None:
        return [f"No eligible plan exists for: {', '.join(result.infeasible)}."]
    lines: list[str] = []
    prof = {p.person: p for p in profiles}
    for offer in result.winner.offers:
        for person in offer.persons:
            p = prof[person]
            states = {n.benefit: offer.benefits.get(n.benefit, UNKNOWN) for n in p.needs}
            covered = [b for b, s in states.items() if s in (COVERED, ACTION)]
            capped = [b for b, s in states.items() if s == SUB_LIMIT]
            absent = [b for b, s in states.items() if s == NOT_COVERED]
            unknown = [b for b, s in states.items() if s == UNKNOWN]
            parts = [f"{p.name}: {offer.label}"]
            if covered:
                parts.append("covers " + ", ".join(covered))
            if capped:
                parts.append("capped for " + ", ".join(capped))
            if absent:
                parts.append("does not cover " + ", ".join(absent))
            if unknown:
                parts.append("not shown: " + ", ".join(unknown))
            lines.append("; ".join(parts) + ".")
    lines.append(f"Household total {result.winner.total} a year, fit {result.winner.fit:.2f}, "
                 f"price penalty {result.winner.penalty:.2f}.")
    if result.robust:
        lines.append("The result holds whichever way the benefits not shown turn out.")
    elif result.flips:
        lines.append("Confirm before recommending: " + "; ".join(
            f"{f.plan_key} {f.benefit} (if covered, {f.new_winner} wins)" for f in result.flips) + ".")
    else:
        lines.append("Some benefits are not shown. Confirm them before recommending.")
    if result.winner.unconfirmed_must:
        lines.append("A must-have benefit is not shown for: " + "; ".join(
            f"{o} {b}" for o, b in result.winner.unconfirmed_must) + ".")
    if result.winner.over_budget:
        lines.append("Every combination is over the stated budget.")
    return lines


def as_scenario(selection: Selection) -> Scenario | None:
    """The quotes behind a selection, for the family_mix checks, when every offer carries them."""
    if not all(o.quotes for o in selection.offers):
        return None
    return Scenario(tuple(q for o in selection.offers for q in o.quotes))
