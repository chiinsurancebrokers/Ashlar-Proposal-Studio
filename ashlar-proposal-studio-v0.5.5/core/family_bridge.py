"""Turn analysed Studio options into offers for the family optimiser.

The Case Studio already reads each quote and brochure into one analysis per option: premium,
excess, area of cover and a benefit cell per benefit. This module reuses that work. It does not
read documents itself. The broker says who each option covers, and the benefit cells are classified
with the same deterministic rules the comparison matrix uses.
"""
from __future__ import annotations

import re
from decimal import Decimal
from typing import Iterable, Mapping

from core.amounts import annual_premium
from core.benefit_state import COVERED, UNKNOWN, classify
from core.family_optimizer import Offer, Profile, Need, MUST, HIGH, MEDIUM, LOW

# The benefit keys the analyser writes. A need names one of these.
BENEFITS = {
    "inpatient": "Inpatient treatment",
    "outpatient": "Outpatient doctor visits",
    "cancer": "Cancer care",
    "chronic_conditions": "Chronic conditions",
    "mental_health": "Mental health",
    "maternity": "Maternity",
    "dental": "Dental",
    "optical": "Optical",
    "diagnostics_imaging": "Diagnostics and imaging",
    "preventive": "Preventive care and check-ups",
    "evacuation_repatriation": "Evacuation and repatriation",
    "emergency": "Emergency and urgent care",
}
WEIGHTS = {"Must have": MUST, "High": HIGH, "Medium": MEDIUM, "Low": LOW}
BUDGETS = {"High": "high", "Normal": "normal", "Low": "low"}

_NOT_SHOWN = {"", "not mentioned", "not specified", "unspecified", "unknown", "none mentioned"}
_PLAIN_YES = re.compile(r"^(covered|included)\b", re.I)


def benefit_state(text) -> str:
    """One benefit cell to a state. A cell that says nothing is unknown, never covered."""
    value = str(text or "").strip()
    if value.casefold() in _NOT_SHOWN:
        return UNKNOWN
    state = classify(value)
    if state == UNKNOWN and _PLAIN_YES.match(value):
        return COVERED   # "Covered" or "Included" on its own: the classifier leaves it open
    return state


def benefit_states(analysis: Mapping) -> dict[str, str]:
    benefits = analysis.get("benefits") or {}
    return {key: benefit_state(benefits.get(key)) for key in BENEFITS}


def benefit_details(analysis: Mapping) -> dict[str, str]:
    """The text to show beside each benefit state. ``benefit_display`` (for example the same cells in
    the client's language) wins over ``benefits``; blank cells are left out."""
    shown = analysis.get("benefit_display") or {}
    benefits = analysis.get("benefits") or {}
    out: dict[str, str] = {}
    for key in BENEFITS:
        text = str(shown.get(key) or benefits.get(key) or "").strip()
        if text and text.casefold() not in _NOT_SHOWN:
            out[key] = text
    return out


def plan_display(result: Mapping) -> str:
    analysis = result.get("analysis") or {}
    provider = str(analysis.get("provider") or result.get("provider") or "").strip()
    plan = str(analysis.get("plan_name") or result.get("target_plan") or "").strip()
    return f"{provider} {plan}".strip() or "Unnamed option"


def offer_from_result(offer_id: str, result: Mapping, persons: Iterable[str], *,
                      residences: Iterable[str] | None = None) -> tuple[Offer | None, str]:
    """One analysed option covering ``persons`` at the premium it quotes.

    Returns ``(offer, "")`` or ``(None, reason)``. The premium is the quoted total for everyone the
    option covers, converted to a yearly figure from its payment frequency. Nothing is estimated:
    an option with no readable premium is left out and the reason says so.
    """
    persons = tuple(persons)
    if not persons:
        return None, f"{plan_display(result)}: not assigned to anyone."
    analysis = result.get("analysis") or {}
    yearly = annual_premium(analysis.get("premium"))
    if yearly is None:
        return None, f"{plan_display(result)}: no readable premium, so it cannot be priced."
    currency, total, _, _ = yearly
    if currency and currency != "EUR":
        return None, f"{plan_display(result)}: premium is in {currency}; enter it in EUR first."
    label = plan_display(result)
    return Offer(offer_id, label, label, persons, Decimal(str(total)),
                 frozenset(r for r in (residences or []) if str(r).strip()) or frozenset({"*"}),
                 benefit_states(analysis), details=benefit_details(analysis)), ""


def offers_from_assignments(results: list[Mapping], assignments: Mapping[int, Iterable[str]], *,
                            residences: Mapping[int, Iterable[str]] | None = None) -> tuple[list[Offer], list[str]]:
    """Offers for every assigned option, plus a note for each option that was left out."""
    offers: list[Offer] = []
    notes: list[str] = []
    for index, result in enumerate(results):
        assigned = tuple(assignments.get(index, ()))
        if not assigned:
            continue
        offer, reason = offer_from_result(f"option-{index}", result, assigned,
                                          residences=(residences or {}).get(index))
        if offer is None:
            notes.append(reason)
        else:
            offers.append(offer)
    return offers, notes


def profile(person: str, name: str, residence: str, needs: Mapping[str, str], budget: str = "Normal",
            importance: float = 1.0) -> Profile:
    """A profile from screen values: needs maps a benefit key to 'Must have', 'High', 'Medium' or 'Low'."""
    return Profile(person, name, residence,
                   tuple(Need(b, WEIGHTS[w]) for b, w in needs.items() if b in BENEFITS and w in WEIGHTS),
                   BUDGETS.get(budget, "normal"), importance)


def _key(name: str) -> str:
    # \w is Unicode-aware, so Greek names keep their letters. An ASCII-only pattern turned
    # "Δεύτερη κόρη" into an empty key and made two Greek names collide.
    return re.sub(r"[\W_]+", "-", name.casefold()).strip("-")


def profiles_from_tables(people: Iterable[Mapping], needs_table: Iterable[Mapping]) -> tuple[list[Profile], list[str]]:
    """Profiles from the two tables on the screen.

    ``people`` rows hold Name, Residence and Budget. ``needs_table`` has one row per benefit key,
    with a column per person name holding "Low", "Medium", "High", "Must have" or blank.
    Returns the profiles and a warning for each row that could not be used.
    """
    warnings: list[str] = []
    profiles: list[Profile] = []
    seen: set[str] = set()
    rows = list(needs_table)
    for row in people:
        name = str(row.get("Name") or "").strip()
        residence = str(row.get("Residence") or "").strip()
        if not name:
            continue
        if not residence:
            warnings.append(f"{name}: residence is missing, so plans cannot be checked against it.")
            continue
        key = _key(name)
        if key in seen:
            warnings.append(f"{name}: the name is used twice. Give each person a different name.")
            continue
        seen.add(key)
        needs = {r["Benefit"]: r.get(name) for r in rows if r.get(name) in WEIGHTS}
        profiles.append(profile(key, name, residence, needs, str(row.get("Budget") or "Normal")))
    return profiles, warnings


def person_key(name: str) -> str:
    return _key(name)


def run_family_mix(people_rows: Iterable[Mapping], need_rows: Iterable[Mapping], results: list[Mapping],
                   assignments: Mapping[int, Iterable[str]], *, residences: Mapping[int, Iterable[str]] | None = None,
                   budget_cap=None):
    """Everything the screen does on the button: profiles, offers, then the optimiser.

    ``need_rows`` may name a benefit by its label or its key. Returns ``(outcome, profiles, notes)``
    where ``outcome`` is None when there is nothing to search.
    """
    from core.family_optimizer import optimise

    inverse = {label: key for key, label in BENEFITS.items()}
    rows = [{**r, "Benefit": inverse.get(r.get("Benefit"), r.get("Benefit"))} for r in need_rows]
    profiles, warnings = profiles_from_tables(people_rows, rows)
    offers, notes = offers_from_assignments(results, assignments, residences=residences)
    if not profiles or not offers:
        return None, profiles, warnings + notes
    return optimise(profiles, offers, budget_cap=budget_cap), profiles, warnings + notes
