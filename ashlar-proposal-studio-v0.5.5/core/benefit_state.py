"""Classify a comparison-table cell into one of four states.

Ashlar uses one state vocabulary across its sites and documents (the
`insurance-marks` house rules): covered, action needed, sub-limit, not
covered. Each state has a colour AND a shape, so a reader who cannot
distinguish the colours still reads the state.

    covered        verdigris   filled dot    paid, included, in network
    action         slate ink   open circle   something must happen first
    sub_limit      amber       triangle      paid, but capped or conditional
    not_covered    oxblood     cross         excluded, declined, no cover

WHY THIS IS DETERMINISTIC
-------------------------
`build_comparison_matrix` builds its rows from extracted document values
"without LLM interpretation", and this classifier keeps that promise: it
reads the cell text the extraction already produced and maps it to a
state. No model call, no judgement, and the same input always gives the
same mark.

THE RULE IT ENFORCES
--------------------
When a benefit is NOT COVERED, the document shows "Not covered" and
nothing else. Writing "not covered at this tier, complications €10,000
after 10 months" next to a cross tells the reader two contradictory
things at once. `display_text` applies that rule so a renderer cannot
forget it.
"""
from __future__ import annotations

import re

COVERED = "covered"
ACTION = "action"
SUB_LIMIT = "sub_limit"
NOT_COVERED = "not_covered"
UNKNOWN = "unknown"

def _norm(text) -> str:
    """Lower-case and collapse whitespace.

    Note for Greek: casefold() maps the final sigma "ς" to "σ", so a literal
    written with "ς" can never match normalised input. Every phrase list
    below is pushed through this same function at import time, which keeps
    both sides in the same alphabet instead of relying on whoever adds the
    next phrase to remember.
    """
    return " ".join(str(text or "").strip().casefold().split())


def _normalised(*phrases):
    return tuple(_norm(p) for p in phrases)


# Phrases that mean the benefit is not there. Checked first: a cell reading
# "not covered, see page 12" is still not covered.
_NOT_COVERED = _normalised(
    "not covered", "no cover", "not included", "excluded", "exclusion",
    "not available", "not applicable", "not offered", "declined",
    # Greek
    "δεν καλύπτεται", "χωρίς κάλυψη", "εξαιρείται", "δεν περιλαμβάνεται",
)

# These mean "nothing" only when they are the WHOLE cell. A dash inside a
# sentence is punctuation: "Full refund – max 5 visits" is a benefit that
# pays in full, and reading its en-dash as "nothing here" would tell a
# client they have no cover when they have cover with a cap on it.
_NOT_COVERED_WHOLE_CELL = set(_normalised(*{
    "—", "–", "-", "none", "nil", "n/a", "na", "no", "0", "0.00",
    "κανένα", "καμία", "όχι",
}))

# The verdict lives in the opening clause. These extractions are written
# verdict-first -- "Included ...", "Not covered ...", "Unclear ..." -- and
# everything after it describes that verdict.
_LEAD_SPLIT = re.compile(r"[.;\n]")


def _lead(value: str) -> str:
    """The cell's opening clause: what the extraction concluded."""
    return _LEAD_SPLIT.split(value, 1)[0].strip()


# Something has to happen before the benefit pays.
_ACTION = _normalised(
    "pre-authorisation", "pre-authorization", "preauthorisation", "preauthorization",
    "prior approval", "pre-approval", "preapproval", "prior authorisation",
    "requires approval", "must be approved", "on referral", "referral required",
    "reimbursed on claim", "confirm with insurer", "subject to approval",
    "unclear", "to be confirmed", "depending on underwriting", "depends on underwriting",
    "not stated", "confirm on the certificate",
    # Greek
    "προέγκριση", "κατόπιν έγκρισης", "απαιτείται έγκριση", "παραπομπή",
)

# Paid without a ceiling worth naming.
_COVERED = _normalised(
    "full refund", "paid in full", "in full", "100%", "covered in full",
    "included in full", "full cover",
    # Greek
    "πλήρης κάλυψη", "πλήρως", "εξ ολοκλήρου",
)

# Explicitly uncapped. Checked before the sub-limit scan, because "no limit"
# and "unlimited" both contain the word "limit".
_UNCAPPED = _normalised("unlimited", "no limit", "no overall limit", "without limit",
             "χωρίς όριο", "απεριόριστο")

# A countable allowance. A cell can say "paid in full" AND cap the number of
# visits — "15 consultations, paid in full" is capped at fifteen, and the cap
# is the part the reader needs.
_COUNTABLE = re.compile(
    r"\b\d[\d,.]*\s*(?:visits?|sessions?|consultations?|nights?|days?|weeks?|months?|"
    r"admissions?|treatments?|times?|επισκ|συνεδρ|ημέρ|νύχτ)",
    re.I,
)

# Present, but capped, delayed or shared.
_SUB_LIMIT = _normalised(
    "limit", "up to", "max", "maximum", "capped", "combined",
    "waiting period", "co-insurance", "coinsurance", "co-payment", "copayment",
    "per year", "per claim", "per person", "annual allowance", "sub-limit",
    "visits", "sessions", "nights", "days",
    # Greek
    "όριο", "έως", "μέγιστο", "αναμονή", "συμμετοχή", "ανά έτος", "επισκέψεις",
)

_MONEY = re.compile(r"[€£$]\s?[\d,.]+|\b\d[\d,.]*\s?(?:eur|gbp|usd|€|£|\$)", re.I)
_BARE_NUMBER = re.compile(r"\b\d[\d,.]{2,}\b")


def classify(text) -> str:
    """Return the state this cell describes.

    Order matters. "Not covered" wins over everything, because a cell that
    mentions a limit while saying the benefit is absent is still absent.
    A conditional ("pre-authorisation required") outranks a plain amount,
    because the condition is the thing the reader must act on.
    """
    value = _norm(text)
    if not value or value in {"not specified", "unspecified", "unknown"}:
        return UNKNOWN

    if value in _NOT_COVERED_WHOLE_CELL:
        return NOT_COVERED

    # The absence has to be the verdict, not a clause inside it.
    #
    # This scanned the whole cell once, and it put a client-facing document
    # into the world saying APRIL covered no maternity, no dental, no optical
    # and no cancer. Each of those cells began "Included ..." and went on to
    # name what sat outside the benefit -- "Orthodontics are not covered",
    # "Laser vision correction is not covered", "Cancer preventive surgery is
    # not covered". A detail of a covered benefit was read as the verdict on
    # it, and display_text then replaced the whole cell with "Not covered",
    # deleting the cover the client had actually bought.
    #
    # A benefit is absent when its opening clause says so.
    if any(term in _lead(value) for term in _NOT_COVERED):
        return NOT_COVERED
    if any(term in value for term in _ACTION):
        return ACTION

    # Uncapped before capped: "no limit" and "unlimited" both contain "limit".
    if any(term in value for term in _UNCAPPED):
        return COVERED

    is_full = any(term in value for term in _COVERED)
    # A countable allowance caps the benefit even when the cell also says the
    # money is paid in full: "15 consultations, paid in full" runs out at 15.
    if _COUNTABLE.search(value):
        return SUB_LIMIT
    if any(term in value for term in _SUB_LIMIT):
        return SUB_LIMIT
    if is_full:
        return COVERED
    # A bare amount with no "in full" wording is an allowance.
    if _MONEY.search(value) or _BARE_NUMBER.search(value):
        return SUB_LIMIT
    return UNKNOWN


def display_text(text, state: str | None = None) -> str:
    """What the cell should actually say.

    A benefit that is not covered reads "Not covered" and stops. Keeping
    the original phrasing there — "not covered at this tier, complications
    paid to €10,000 after 10 months" — puts a specification next to a
    cross and leaves the reader unsure which half to believe.
    """
    state = state or classify(text)
    if state == NOT_COVERED:
        return "Not covered"
    if state == UNKNOWN:
        return "Not specified"
    return str(text).strip()


def mark(text) -> dict:
    """The cell ready to render: state, the text to show, and whether the
    renderer may add a supporting note beneath it."""
    state = classify(text)
    return {
        "state": state,
        "text": display_text(text, state),
        "allows_detail": state not in (NOT_COVERED, UNKNOWN),
        "original": str(text or "").strip(),
    }


# ---------------------------------------------------------------------------
# Coverage scope
# ---------------------------------------------------------------------------

def coverage_areas(results: list[dict]) -> dict[str, str]:
    """Each plan's area of cover, as the extraction recorded it."""
    from .client_analysis import plan_display_name
    out = {}
    for result in results or []:
        analysis = result.get("analysis") or {}
        out[plan_display_name(result)] = str(analysis.get("area_of_cover") or "").strip()
    return out


def scope_differs(results: list[dict]) -> bool:
    """True when the plans being compared are not written for the same
    territory.

    Comparing a Europe-only premium against two worldwide premiums reads as
    a price gap when it is a scope gap. The reader has to be told before
    they look at the money, so the report checks rather than relying on
    whoever wrote it noticing.
    """
    areas = {_norm(v) for v in coverage_areas(results).values() if _norm(v)}
    return len(areas) > 1
