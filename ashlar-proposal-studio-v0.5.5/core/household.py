"""Insured household (main applicant + dependants), mirroring the HAL 3 rules.

* A dependant is a spouse/partner, a child, or another dependant.
* A child dependant must be under 25 (HAL 3 rule).
* Maternity can only apply to a female member aged 18–47 (HAL 3 rule); a flag on
  anyone else is ignored and reported back.
"""
from __future__ import annotations

from datetime import date, datetime
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


def _dob(value: Any) -> str:
    """ISO date (YYYY-MM-DD) from a date, datetime or common text format; '' if unknown."""
    if _blank(value):
        return ""
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    text = str(value).strip()[:10]
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d.%m.%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            continue
    return ""


def age_on(dob_iso: str, on: date | None = None) -> int | None:
    if not dob_iso:
        return None
    born = date.fromisoformat(dob_iso)
    today = on or date.today()
    return today.year - born.year - ((today.month, today.day) < (born.month, born.day))


def is_applicant_row(raw: Any) -> bool:
    return isinstance(raw, dict) and _text(raw.get("relationship", raw.get("Relationship"))).casefold() == "main applicant"


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
        if is_applicant_row(raw):
            continue  # the applicant's own details travel with the household, not as a dependant
        name = _text(raw.get("name", raw.get("Name")))
        rel_raw = _text(raw.get("relationship", raw.get("Relationship")))
        relationship = _REL_ALIASES.get(rel_raw.casefold(), rel_raw if rel_raw in RELATIONSHIPS else "")
        dob = _dob(raw.get("dob", raw.get("Date of birth")))
        age = age_on(dob) if dob else _age(raw.get("age", raw.get("Age")))
        sex = _sex(raw.get("sex", raw.get("Sex")))
        nationality = _text(raw.get("nationality", raw.get("Nationality")))
        maternity = _flag(raw.get("maternity", raw.get("Maternity cover")))
        if not (name or relationship or age is not None):
            continue  # empty editor row
        label = name or relationship or "Dependant"
        if not relationship:
            relationship = "Other dependant"
        if relationship == "Child" and age is not None and age > CHILD_MAX_AGE:
            warnings.append(f"{label}: a child dependant must be under 25 — not added.")
            continue
        member = {"name": name, "relationship": relationship, "dob": dob, "age": age, "sex": sex,
                  "nationality": nationality, "maternity": False}
        if maternity:
            if maternity_eligible(member):
                member["maternity"] = True
            else:
                warnings.append(f"{label}: maternity can only apply to a female member aged 18–47 — flag ignored.")
        members.append(member)
    return members, warnings


def applicant_details(rows: Any) -> dict:
    """Nationality / date of birth stored for the main applicant, if any."""
    for raw in rows or []:
        if is_applicant_row(raw):
            return {"dob": _dob(raw.get("dob", raw.get("Date of birth"))),
                    "nationality": _text(raw.get("nationality", raw.get("Nationality")))}
    return {"dob": "", "nationality": ""}


def applicant_row(*, dob: Any = None, nationality: Any = None) -> dict | None:
    """Household entry carrying the applicant's own extra details (None when empty)."""
    dob_iso, nat = _dob(dob), _text(nationality)
    if not (dob_iso or nat):
        return None
    return {"relationship": "Main applicant", "dob": dob_iso, "nationality": nat}


def insured_people(*, client_name: str = "", client_sex: str = "", client_age: Any = None,
                   members: Any = None) -> list[dict]:
    """Main applicant first, then dependants — the list shown in the report."""
    extra = applicant_details(members)
    age = age_on(extra["dob"]) if extra["dob"] else _age(client_age)
    main = {"name": str(client_name or "").strip(), "relationship": "Main applicant", "dob": extra["dob"],
            "age": age, "sex": _sex(client_sex), "nationality": extra["nationality"], "maternity": False}
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
