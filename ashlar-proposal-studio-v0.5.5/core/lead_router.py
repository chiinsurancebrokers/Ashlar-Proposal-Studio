"""Route an English-language Generali lead: Life On first, an international plan only when needed.

Generali sells local plans only and enrols only people with a valid Greek AFM. The router reads a lead
and decides one of three tracks:

* ``generali_life_on``: nothing in the enquiry goes beyond Life On, so the reply promotes Life On.
* ``generali_plus_international``: the lead wants things Life On does not offer (free choice of doctors,
  enriched outpatient, no waiting periods, cover or direct billing abroad, nil deductible). The reply
  still presents Life On honestly for the hospital core, then offers an international plan for the rest.
* ``international_only``: the lead says they have no Greek AFM, so Generali cannot enrol them.

Nothing here is a price. Facts about Life On come from the Family Mix work (hospital-only, EUR 1,500
participation, optional Doctors & Exams add-on) and from core/waiting_periods.py. Anything not known is
left as a [CONFIRM] marker for the broker, never filled in.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

GENERALI = "generali_life_on"
MIXED = "generali_plus_international"
INTERNATIONAL = "international_only"

GAP = "gap"        # Life On cannot meet it: a reason to bring in an international plan
REVIEW = "review"  # needs a look at the wording or underwriting; not a reason to switch on its own

# (id, label, severity, patterns). Edit this table to tune the router; nothing else needs to change.
RULES: list[tuple[str, str, str, list[str]]] = [
    ("free_doctor_choice", "Free choice of doctors / out-of-network reimbursement", GAP, [
        r"free(dom)?\s+(of\s+)?choice", r"choos\w*\s+(our|my|their)?\s*(own\s+)?(doctors?|hospitals?|physicians?)",
        r"any\s+(doctor|hospital|specialist)", r"out[\s-]*of[\s-]*network", r"outside\s+(of\s+)?(your|the)\s+network",
        r"non[\s-]*network", r"not\s+(limited|restricted)\s+to\s+(a\s+)?network",
    ]),
    ("enriched_outpatient", "Enriched outpatient cover (specialists, visits, prescriptions, check-ups)", GAP, [
        r"out[\s-]*patient", r"specialist", r"doctor\s+visits?", r"consultations?", r"prescription",
        r"check[\s-]*ups?", r"preventive", r"without\s+(a\s+)?hospital", r"no\s+hospital\s+admission",
        r"not\s+requir\w*\s+hospital", r"hospital\s+admission\s+is\s+not\s+required",
    ]),
    ("no_waiting_periods", "No waiting periods", GAP, [
        r"no\s+waiting", r"without\s+(any\s+)?waiting", r"waiting\s+periods?\s+(waived|waiver|removed)",
        r"immediate\s+(cover|coverage|start)", r"waive\w*\s+(the\s+)?waiting",
    ]),
    ("cover_abroad", "Cover or direct billing abroad", GAP, [
        r"overseas", r"worldwide", r"world[\s-]*wide", r"\babroad\b", r"outside\s+(of\s+)?greece",
        r"global\s+(cover|coverage|plan)", r"international\s+(/\s*overseas\s+)?(medical\s+)?(cover|coverage|plan|health)",
        r"stud\w+\s+(in|abroad)", r"expat",
    ]),
    ("zero_deductible", "Nil or low deductible / no participation", GAP, [
        r"(zero|nil|no|low)\s+(or\s+(zero|nil|no)\s+)?(deductibles?|excess|participation|co[\s-]*pay)",
        r"full\s+reimbursement",
    ]),
    ("pre_existing", "Pre-existing conditions", REVIEW, [r"pre[\s-]*existing", r"existing\s+conditions?"]),
    ("diagnostics", "Diagnostic tests (Doctors & Exams add-on)", REVIEW, [r"diagnostic", r"\bexams?\b", r"examinations?"]),
]

AFM_NONE = [
    r"(do(es)?\s*n['’]?t|do(es)?\s+not|don['’]?t|no|without|not\s+yet|yet\s+to)\s+(yet\s+)?(have|hold|got|obtained)?\s*(a\s+|an\s+|the\s+)?(valid\s+)?(greek\s+)?(a\.?f\.?m\.?|tax\s+(id|number|identification|registration|resid\w+))",
    r"non[\s-]*(tax[\s-]*)?resident", r"not\s+(a\s+)?(greek\s+)?tax\s+resident", r"no\s+tax\s+residen\w+\s+in\s+greece",
]
AFM_HAS = [r"\ba\.?f\.?m\.?\b", r"greek\s+tax\s+(id|number)", r"tax\s+resident\s+in\s+greece", r"\bvat\s+number\b"]

DISCLOSURE = ("I handle English-language enquiries for Generali Greece. Ashlar Assurance also works with the leading "
              "insurers, so I can compare other options for you. We are paid only by commission from the insurer whose "
              "policy you choose, and we do not charge you any fee. [CONFIRM your exact regulatory status wording]")


@dataclass
class Hit:
    rule: str
    label: str
    severity: str
    evidence: str


@dataclass
class Routing:
    track: str
    afm: str                      # "has", "none" or "unknown"
    hits: list[Hit] = field(default_factory=list)
    asked_for_life_on: bool = False

    @property
    def gaps(self) -> list[Hit]:
        return [h for h in self.hits if h.severity == GAP]

    @property
    def reviews(self) -> list[Hit]:
        return [h for h in self.hits if h.severity == REVIEW]


def _sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+|\n+|\s*[*•]\s+", text)
    return [p.strip() for p in parts if p and p.strip()]


def _first(patterns: list[str], sentences: list[str]) -> str | None:
    for s in sentences:
        if any(re.search(p, s, re.I) for p in patterns):
            return s
    return None


def route(text: str) -> Routing:
    sents = _sentences(text)
    hits: list[Hit] = []
    for rid, label, sev, pats in RULES:
        ev = _first(pats, sents)
        if ev:
            hits.append(Hit(rid, label, sev, ev))

    if _first(AFM_NONE, sents):
        afm = "none"
    elif _first(AFM_HAS, sents):
        afm = "has"
    else:
        afm = "unknown"

    if afm == "none":
        track = INTERNATIONAL
    elif any(h.severity == GAP for h in hits):
        track = MIXED
    else:
        track = GENERALI
    return Routing(track, afm, hits, asked_for_life_on=bool(re.search(r"life[\s-]*on", text, re.I)))


def draft_reply(r: Routing, name: str = "", family: str = "") -> str:
    """A first draft for the broker to edit. Known facts only; everything else is a [CONFIRM] marker."""
    who = f"Dear {name}," if name else "Hello,"
    out = [who, "", "Thank you for your enquiry. " + DISCLOSURE, ""]

    if r.track == INTERNATIONAL:
        out += ["Generali's plans are local Greek policies and can only be issued to someone with a valid Greek tax number (AFM). "
                "Since you do not have one, Generali is not an option for you at this stage. "
                "If that changes, I would be glad to revisit it.", "",
                "What I can do is compare international health plans for you. [CONFIRM which carriers and plans to name]", ""]
    else:
        out += ["Generali Life On is a hospital-focused plan with a EUR 1,500 participation (a cost share, not an excess). "
                "It suits a family that wants a strong hospital cover at a sensible price. "
                "An optional Doctors & Exams add-on extends it to doctor visits and tests. "
                "[CONFIRM plan names, direct-billing hospital list and out-of-network reimbursement before sending]", ""]
        if r.track == MIXED:
            out += ["From your message, the following go beyond what Life On offers, so I want to be upfront about it:"]
            out += [f"- {h.label}" for h in r.gaps]
            out += ["", "If those matter most to you, an international health plan is the better fit, and I can put the two options "
                    "side by side with prices, deductibles, waiting periods and exclusions so you can choose. "
                    "[CONFIRM which international plan to name]", ""]
        if r.reviews:
            out += ["I will also check the policy wording on: " + "; ".join(h.label.lower() for h in r.reviews) + ".", ""]

    asks = ["Full names and dates of birth of everyone to be insured",
            "Country of residence and intended start date",
            "Any existing medical conditions or past treatment (needed for underwriting)"]
    if r.afm != "has":
        asks.insert(1, "Whether each adult holds a valid Greek AFM")
    out += ["To prepare a quotation I need:"] + [f"- {a}" for a in asks] + ["", "Kind regards,"]
    return "\n".join(out)
