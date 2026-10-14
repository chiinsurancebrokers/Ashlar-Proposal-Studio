"""Insured household (main applicant + dependants), mirroring the HAL 3 rules.

* A dependant is a spouse/partner, a child, or another dependant.
* A child dependant must be under 25 (HAL 3 rule).
* Maternity can only apply to a female member aged 18–47 (HAL 3 rule); a flag on
  anyone else is ignored and reported back.
"""
from __future__ import annotations

from typing import Any

RELATIONSHIPS = ("Spouse / partner", "Child", "Other dependant")
SEXES = ("Not specified", "Male", "Female")
CHILD_MAX_AGE = 24
MATERNITY_MIN_AGE, MATERNITY_MAX_AGE = 18, 47

_REL_ALIASES = {
    "spouse": "Spouse / partner", "partner": "Spouse / partner", "wife": "Spouse / partner",
    "husband": "Spouse / partner", "spouse / partner": "Spouse / partner", "σύζυγος": "Spouse / partner",
    "child": "Child", "son": "Child", "daughter": "Child", "παιδί": "Child",
    "other": "Other dependant", "other dependant": "Other dependant",
}

REL_GREEK = {"Main applicant": "Κύριος ασφαλισμένος", "Spouse / partner": "Σύζυγος / σύντροφος",
             "Child": "Τέκνο", "Other dependant": "Άλλο εξαρτώμενο μέλος"}


def _blank(value: Any) -> bool:
    return value is None or (isinstance(value, float) and value != value) or str(value).strip().casefold() in {"", "nan", "none"}


def _text(value: Any) -> str:
    return "" if _blank(value) else str(value).strip()


def _flag(value: Any) -> bool:
    if _blank(value):
        return False
    if isinstance(value, str):
        return value.strip().casefold() in {"true", "yes", "1", "ναι"}
    return bool(value)


def _age(value: Any) -> int | None:
    try:
        if _blank(value):
            return None
        age = int(float(value))
    except (TypeError, ValueError):
        return None
    return age if 0 <= age <= 120 else None


def _sex(value: Any) -> str:
    key = str(value or "").strip().casefold()
    if key in {"male", "m", "άνδρας", "αρρεν", "άρρεν"}:
        return "Male"
    if key in {"female", "f", "γυναίκα", "θήλυ", "θηλυ"}:
        return "Female"
    return "Not specified"


def maternity_eligible(member: dict) -> bool:
    age = member.get("age")
    return member.get("sex") == "Female" and age is not None and MATERNITY_MIN_AGE <= age <= MATERNITY_MAX_AGE


def normalise_members(rows: Any) -> tuple[list[dict], list[str]]:
    """Clean dependant rows from the form; return (members, warnings)."""
    members: list[dict] = []
    warnings: list[str] = []
    for raw in rows or []:
        if not isinstance(raw, dict):
            continue
        name = _text(raw.get("name", raw.get("Name")))
        rel_raw = _text(raw.get("relationship", raw.get("Relationship")))
        relationship = _REL_ALIASES.get(rel_raw.casefold(), rel_raw if rel_raw in RELATIONSHIPS else "")
        age = _age(raw.get("age", raw.get("Age")))
        sex = _sex(raw.get("sex", raw.get("Sex")))
        maternity = _flag(raw.get("maternity", raw.get("Maternity cover")))
        if not (name or relationship or age is not None):
            continue  # empty editor row
        label = name or relationship or "Dependant"
        if not relationship:
            relationship = "Other dependant"
        if relationship == "Child" and age is not None and age > CHILD_MAX_AGE:
            warnings.append(f"{label}: a child dependant must be under 25 — not added.")
            continue
        member = {"name": name, "relationship": relationship, "age": age, "sex": sex, "maternity": False}
        if maternity:
            if maternity_eligible(member):
                member["maternity"] = True
            else:
                warnings.append(f"{label}: maternity can only apply to a female member aged 18–47 — flag ignored.")
        members.append(member)
    return members, warnings


def insured_people(*, client_name: str = "", client_sex: str = "", client_age: Any = None,
                   members: Any = None) -> list[dict]:
    """Main applicant first, then dependants — the list shown in the report."""
    main = {"name": str(client_name or "").strip(), "relationship": "Main applicant",
            "age": _age(client_age), "sex": _sex(client_sex), "maternity": False}
    cleaned, _ = normalise_members(members)
    return [main] + cleaned


def household_maternity_relevant(*, client_sex: str = "", client_age: Any = None, members: Any = None) -> bool | None:
    """True/False when dependants were entered; None when there is no household data."""
    cleaned, _ = normalise_members(members)
    if not cleaned:
        return None
    people = [{"sex": _sex(client_sex), "age": _age(client_age)}] + cleaned
    if any(m.get("maternity") for m in cleaned):
        return True
    return any(p.get("sex") == "Female" and (p.get("age") is None or maternity_eligible(p)) for p in people)
