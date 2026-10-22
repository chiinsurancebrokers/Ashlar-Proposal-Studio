"""Route an English-language Generali lead: Life On first, an international plan only when needed.

Generali sells local plans only and enrols only people with a valid Greek AFM. The router reads a lead
and decides one of three tracks:

* ``generali_life_on``: nothing in the enquiry goes beyond Life On, so the reply promotes Life On.
* ``generali_plus_international``: the lead wants things Life On does not offer (free choice of doctors,
  enriched outpatient, no waiting periods, cover or direct billing abroad, nil deductible). The reply
  still presents Life On honestly for the hospital core, then offers an international plan for the rest.
* ``international_only``: the lead says they have no Greek AFM, so Generali cannot enrol them.

Nothing here is a price. Facts about Life On come from the Family Mix work (hospital-only, €1,500
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

# International carriers Ashlar can compare. Edit here to change who the drafts name.
INTERNATIONAL_CARRIERS = ("VUMI", "Bupa", "Cigna", "Allianz Care", "IMG", "APRIL International",
                          "OneHealth", "Now Health", "Morgan Price")
_CARRIERS = ", ".join(INTERNATIONAL_CARRIERS[:-1]) + " and " + INTERNATIONAL_CARRIERS[-1]

DISCLOSURE = ("I handle English-language enquiries for Generali Greece. Ashlar Assurance also works with the leading "
              "insurers, so I can compare other options for you. We are paid only by commission from the insurer whose "
              "policy you choose, and we do not charge you any fee.")


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


# The numbered questions in the broker's own reply to lead 001.
ASKS = [
    "Dates of birth and nationalities of everyone to be insured",
    "Any existing conditions or ongoing treatment",
    "Hospitals or doctors you would like to keep using",
    "Whether you want cover in Greece only, Europe, or worldwide",
    "Any extras you want, such as maternity, dental, or check-ups",
    "Your approximate annual budget",
    "Your preferred start date",
]
AFM_ASK = "Whether each adult holds a valid Greek AFM (Generali requires one)"

# What an international plan can offer for each gap. Waiting periods are never promised away.
_IPMI_POINTS = {
    "free_doctor_choice": "Free choice of private hospitals and doctors, with no need for public hospitals or EOPYY",
    "enriched_outpatient": "Outpatient cover for doctors, specialists, diagnostics and prescriptions, with emergency care including visits where admission is not required",
    "zero_deductible": "Low or zero deductible options",
    "cover_abroad": "Cover and direct billing outside Greece, in Europe or worldwide",
    "no_waiting_periods": "Waiting periods that vary by plan; we will show them for every option",
}


# Generali facts. Medical Prime figures come from the Table of Benefits of quote 08547743 (21/10/2026), issued
# for one adult, so participations and limits must be checked against the applicant's own quote.
MEDICAL_PRIME_POINTS = [
    "Hospital stays in Greece covered at 100% with no participation, up to €300,000 a year per person, in Generali's partner hospitals: "
    "Hygeia and Mitera (Hygeia Group) in Athens and Euromedica in Thessaloniki. A first-class room adds €100 a night. "
    "[CONFIRM: these figures come from a recent quote for one adult and may differ on your family quote; the quote shows no participation 'with use of a social insurance fund', so check how it applies if you do not use one]",
    "Unlimited scheduled visits to partner doctors, €10 per visit.",
    "Emergencies: a visit to a partner doctor on duty has no participation; a partner specialist called out in an emergency costs €50.",
    "Diagnostic tests and medical procedures: up to €1,500 per insurance year, with 15% participation, on referral from a partner doctor.",
    "Physiotherapy: up to €1,000 per insurance year, with 15% participation.",
    "Annual preventive check-up (14 tests for adults, 5 for children), €10 each, available from six months after the start.",
]
MEDICAL_PRIME_WAITS = ("Waiting periods: doctors and tests are covered from one month after the start. For hospital cover, conditions you "
                       "declare and already know about are covered after two years (five years if they relate to a malignancy); conditions "
                       "that were unknown and undeclared after one or two years, depending on the condition; and congenital conditions "
                       "(other than cardiac) and listed special conditions after ten years.")
PREMIUM_COVERS = ("unlimited visits to Generali's partner doctors, with a participation per visit; "
                  "diagnostic tests at partner diagnostic centres, with a referral and Generali's prior approval; "
                  "a family doctor chosen from the partner network; and a set number of visits a year to a doctor of your own "
                  "choice outside the network, reimbursed as the Table of Benefits shows")
PREMIUM_NOT = ("preventive check-ups, prescription medication, pregnancy, tests done only in a hospital, "
               "and exams or specialties outside the partner network")
SIGNATURE = ["Chris Iatropoulos", "Founder | Ashlar Assurance", "M +30 697 590 0189",
             "E c.iatropoulos@ashlarassurance.com", "W ashlarassurance.com", "Protection built for the life you live."]
_WANTS = {
    "free_doctor_choice": "free choice of private doctors and hospitals",
    "enriched_outpatient": "outpatient cover for doctors, specialists and tests",
    "zero_deductible": "low or zero deductibles",
    "cover_abroad": "cover and direct billing abroad",
    "no_waiting_periods": "no waiting periods",
}


def _join(items: list[str]) -> str:
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


def draft_reply(r: Routing, name: str = "") -> str:
    """A first draft for the broker to edit. The mixed track follows the broker's own draft for lead 001;
    facts the broker has not confirmed are [CONFIRM] markers, never filled in."""
    who = f"Dear {name}," if name else "Hello,"
    asks = list(ASKS)
    if r.afm != "has":
        asks.insert(1, AFM_ASK)
    questions = [f"{i}. {a}" for i, a in enumerate(asks, 1)]
    left = [h for h in r.reviews if h.rule != "diagnostics"]  # diagnostics are answered by the plan facts
    review = (["I will also check the policy wording on: " + "; ".join(h.label.lower() for h in left) + ".", ""] if left else [])
    sign = ["Best regards,", ""] + SIGNATURE

    if r.track == INTERNATIONAL:
        out = [who, "", "Thank you for your enquiry. " + DISCLOSURE, "",
               "Generali's plans are local Greek policies and can only be issued to someone with a valid Greek tax number (AFM). "
               "Since you do not have one, Generali is not an option for you at this stage. If that changes, I would be glad to revisit it.", "",
               f"What I can do is compare international health plans for you from providers such as {_CARRIERS}.", ""]
    elif r.track == GENERALI:
        out = [who, "", "Thank you for your enquiry. " + DISCLOSURE, "",
               "Generali covers hospitalisation in Greece and, within its partner network, on a recent Generali quotation:", ""]
        out += [f"* {x}" for x in MEDICAL_PRIME_POINTS] + ["", MEDICAL_PRIME_WAITS, ""] + review
    else:  # MIXED
        wants = _join([_WANTS[h.rule] for h in r.gaps if h.rule in _WANTS])
        out = [who, "",
               "Thank you for your enquiry and for considering Generali as your health insurance provider. Generali is a well-known insurer "
               "in Greece, distinguished for its hospital cover and the range of benefits it offers.", "",
               "To be fully transparent about your requirements: Generali's programmes cover hospitalisation in Greece very well, "
               "but doctors, tests and emergency visits are covered only within their partner network. Routine visits to private doctors and "
               "specialists of your own choice are not included. In more detail, on a recent Generali quotation:", ""]
        out += [f"* {x}" for x in MEDICAL_PRIME_POINTS] + ["", MEDICAL_PRIME_WAITS, "",
               f"Since you are looking for {wants}, we would recommend an international private medical insurance (IPMI) plan, "
               "and for this reason your enquiry has been passed to me.", "",
               "At Ashlar we work with Generali in the Greek market, and we also have direct agreements with many IPMI providers, "
               f"including {_CARRIERS}, so we can compare both routes for you. We are paid only by commission from the insurer you choose, "
               "and we do not charge you any fee.", "",
               "IPMI plans can combine:", ""]
        out += [f"* {_IPMI_POINTS[h.rule]}" for h in r.gaps if h.rule in _IPMI_POINTS] + [""]
        out += ["If these are not a high priority, we can instead provide a Generali hospital cover quotation alongside the IPMI one, "
                "so you can compare both and decide what suits you best."
                + (" Generali requires a valid Greek AFM for each adult." if r.afm != "has" else ""), "",
                "For each option we will provide the participating hospital list, direct-billing arrangements, reimbursement for "
                "out-of-network doctors, waiting periods, exclusions and annual limits.", ""] + review

    out += ["To prepare your quotation, please send us:"] + questions + [""] + sign
    return "\n".join(out)
