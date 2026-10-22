"""Route an English-language Generali lead: Life On first, an international plan only when needed.

Generali sells local plans only and enrols only people with a valid Greek AFM. The router reads a lead
and decides one of three tracks:

* ``generali_life_on``: nothing in the enquiry goes beyond Life On, so the reply promotes Life On.
* ``generali_plus_international``: the lead wants things Life On does not offer (free choice of doctors,
  enriched outpatient, no waiting periods, cover or direct billing abroad, nil deductible). The reply
  still presents Life On honestly for the hospital core, then offers an international plan for the rest.
* ``international_only``: the lead says they have no Greek AFM, so Generali cannot enrol them.

Nothing here is a price. Per-plan benefit facts (Life On and Medical Prime, kept apart) live in
core/generali_plans.py; waiting periods in core/waiting_periods.py. Anything not known is
left as a [CONFIRM] marker for the broker, never filled in.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from core.generali_plans import (DEFAULT_PLAN, LIFE_ON, MEDICAL_PRIME, PLAN_NAMES, PLAN_POINTS, PLAN_WAITS, wording_for)

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
    ("zero_deductible", "Nil or low deductible / no participation (Life On offers a €0 option)", REVIEW, [
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

# What the applicant asks us to explain or provide: (id, how the reply names it, how "we will provide" names it, patterns).
# The reply acknowledges every request it finds and promises, or answers, each one.
REQUEST_RULES: list[tuple[str, str | None, str | None, list[str]]] = [
    ("hospital_list", "the participating hospital list", "the participating hospital list", [r"hospital\s+list", r"participating\s+hospitals?", r"network\s+hospitals?"]),
    ("direct_billing", "direct billing", "direct-billing arrangements", [r"direct\s+(billing|payment|settlement)"]),
    ("out_of_network", "reimbursement outside the network", "reimbursement for out-of-network doctors", [r"reimburse\w*", r"out[\s-]*of[\s-]*network", r"outside\s+(of\s+)?(your|the)\s+network"]),
    ("waiting_periods", "waiting periods", "waiting periods", [r"waiting\s+periods?"]),
    ("exclusions", "exclusions", "exclusions", [r"exclusions?"]),
    ("annual_limits", "annual limits", "annual limits", [r"(annual|coverage)\s+(coverage\s+)?limits?"]),
    ("deductibles", "deductibles", "deductible options", [r"deductibles?", r"\bexcess\b", r"co[\s-]*pay"]),
    ("premium", "the annual premium", "the annual premium", [r"annual\s+premium", r"\bpremiums?\b", r"how\s+much", r"\bprice\b"]),
    ("pre_existing", "pre-existing conditions", "how pre-existing conditions are treated", [r"pre[\s-]*existing"]),
    ("underwriting", "underwriting requirements", "the medical underwriting requirements", [r"underwriting"]),
    ("renewal_age", "renewal terms and age limits", "renewal terms and age limits", [r"renewal", r"\bage\s+limits?"]),
    ("start_date", "the earliest start date", "the earliest possible start date", [r"start\s+date", r"earliest\s+possible"]),
    ("prescriptions", "prescription cover", "prescription cover", [r"prescription"]),
    ("preventive", "check-ups and preventive care", "check-up and preventive cover", [r"check[\s-]*ups?", r"preventive"]),
    ("overseas", "overseas cover", "overseas cover", [r"overseas", r"worldwide", r"\babroad\b"]),
    ("info_needed", None, None, [r"what\s+(information|documents)", r"(information|documents)\s+(you\s+)?(need|require)"]),
]
# Always promised for each option, then any extra the applicant asked for.
DEFAULT_PROVIDE = ["hospital_list", "direct_billing", "out_of_network", "waiting_periods", "exclusions", "annual_limits"]
# Answered with facts in the reply itself (Generali tracks); everything else is promised in the quotation.
ANSWERED_NOW = {"hospital_list", "waiting_periods", "deductibles", "annual_limits", "info_needed", "direct_billing", "preventive"}
_REQ = {rid: (ack, prov) for rid, ack, prov, _ in REQUEST_RULES}

# What the Generali documents allow us to say, per plan, lives in core/generali_plans.py (PLAN_WORDING).
# The reply may promise on Generali's behalf only what the plans in play support: see wording_for(r.plans).
_GEN_PHRASE = {"exclusions": "the exclusions", "pre_existing": "how pre-existing conditions are treated",
               "direct_billing": "direct billing", "premium": "the annual premium", "underwriting": "the medical underwriting requirements",
               "renewal_age": "renewal terms and age limits", "start_date": "the earliest possible start date"}

# International carriers Ashlar can compare. Edit here to change who the drafts name.
INTERNATIONAL_CARRIERS = ("VUMI", "Bupa", "Cigna", "Allianz Care", "IMG", "APRIL International",
                          "OneHealth", "Now Health", "Morgan Price")
_CARRIERS = ", ".join(INTERNATIONAL_CARRIERS[:-1]) + " and " + INTERNATIONAL_CARRIERS[-1]

# Why the lead reached Ashlar. Ashlar is an independent broker: not employed by or on the payroll of Generali, and
# responsible for its own advice. Never say or imply otherwise. Edit the registration marker before sending.
# Registration as shown on the Athens Chamber of Commerce and Industry certificate of 06/03/2025 (Special Register 9999,
# "Insurance agents", activity: insurance intermediary) and the registry certificate of 28/08/2026. The registration is in the
# name of Christos Iatropoulos; the trading name Ashlar Assurance is not on either certificate.
REGISTRATION = ("registered with the Athens Chamber of Commerce and Industry in the Special Register of Insurance Intermediaries "
                "(registry no. 191526, GEMI 061564903000, in the name of Christos Iatropoulos)")
BRIDGE = ("As we have been serving expats and affluent Greeks for many years, working with top-tier international health insurance "
          "providers, we have established a strategic collaboration with Generali, so we can guide you to the best insurance solution "
          "for your health needs and priorities. Ashlar Assurance is an independent insurance intermediary. We are not employed by "
          "Generali and have no employment relationship with it. We are " + REGISTRATION + ", and we are responsible for the advice "
          "and service we give you. Chris Iatropoulos holds the Chartered Insurance Institute's Award in General Insurance (March 2025).")
COMMISSION = ("We are paid only by commission from the insurer whose policy you choose, and we do not charge you any fee.")
DISCLOSURE = (BRIDGE + " " + COMMISSION)


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
    requests: list[str] = field(default_factory=list)
    plans: list[str] = field(default_factory=list)  # Generali plans the lead names; empty = none named

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
    requests = [rid for rid, _, _, pats in REQUEST_RULES if _first(pats, sents)]
    plans = [p for p, pat in ((LIFE_ON, r"life[\s-]*on"), (MEDICAL_PRIME, r"medical[\s-]*prime")) if re.search(pat, text, re.I)]
    return Routing(track, afm, hits, asked_for_life_on=bool(re.search(r"life[\s-]*on", text, re.I)), requests=requests, plans=plans)


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


_OWN_DOCTOR = {False: "Routine visits to private doctors and specialists of your own choice are not included.",
               True: "Visits to doctors of your own choice outside the network are limited to a set number a year."}


def _join(items: list[str]) -> str:
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


def _generali_position(r: Routing, skip: tuple[str, ...] = ()) -> list[str]:
    """Plain statements about requested points Generali does not offer in full."""
    w = wording_for(r.plans)
    lines = [w[x][1] for x in r.requests if w.get(x, ("", ""))[0] in ("not_offered", "partial") and x not in skip]
    return [" ".join(lines), ""] if lines else []


def generali_promises(r: Routing) -> list[str]:
    """What the reply promises for the Generali option: only items its wording supports or Generali confirms."""
    wanted = ["exclusions"] + [x for x in r.requests if x in _GEN_PHRASE]
    w = wording_for(r.plans)
    out: list[str] = []
    for x in wanted:
        if w[x][0] in ("wording", "confirm") and x not in out:
            out.append(x)
    return out


def _generali_sentences(r: Routing) -> list[str]:
    items = generali_promises(r)
    w = wording_for(r.plans)
    said = [w[x][0] for x in items]
    wording = [_GEN_PHRASE[x] for x, k in zip(items, said) if k == "wording"]
    confirm = [_GEN_PHRASE[x] for x, k in zip(items, said) if k == "confirm"]
    out = []
    if wording:
        out.append(f"For the Generali option I will send {_join(wording)} as the policy wording states them.")
    if confirm:
        out.append(f"I will confirm {_join(confirm)} with Generali.")
    return out


def _acknowledge(r: Routing) -> list[str]:
    """One paragraph saying we read what they asked, or an empty list when nothing specific was asked."""
    labels = [_REQ[x][0] for x in r.requests if _REQ[x][0]]
    if not labels:
        return []
    if len(labels) > 7:
        return ["You sent a detailed list of questions, and I cover each of them in this reply or in the quotation.", ""]
    return [f"You asked about {_join(labels)}, and I cover each of these in this reply or in the quotation.", ""]


def _provide(r: Routing) -> str:
    keys = DEFAULT_PROVIDE + [x for x in r.requests if x not in DEFAULT_PROVIDE and _REQ[x][1]]
    return _join([_REQ[k][1] for k in keys])


def coverage(r: Routing) -> dict[str, str]:
    """For the broker: each request and how the reply treats it.
    answered = facts are in the reply; promised = Generali wording or confirmation follows; ipmi_only = Generali does not offer it."""
    out: dict[str, str] = {}
    w = wording_for(r.plans)
    for x in r.requests:
        kind = w.get(x, ("confirm", ""))[0]
        if r.track == INTERNATIONAL:
            out[x] = "answered" if x == "info_needed" else "promised"
        elif x in ANSWERED_NOW:
            out[x] = "answered"
        elif kind in ("not_offered", "partial"):
            out[x] = "ipmi_only" if kind == "not_offered" else "answered"
        else:
            out[x] = "promised"
    return out


def draft_acknowledgement(r: Routing, name: str = "") -> str:
    """A short receipt to send straight away, before the full reply is ready."""
    who = f"Dear {name}," if name else "Hello,"
    labels = [_REQ[x][0] for x in r.requests if _REQ[x][0]]
    out = [who, "", "Thank you for your enquiry. I have received it and am preparing a reply."]
    if labels and len(labels) <= 7:
        out.append(f"You asked about {_join(labels)}, and I will answer each of these.")
    out += ["", "I will come back to you [CONFIRM when]."]
    if r.afm != "has" and r.track != INTERNATIONAL:
        out += ["", "One quick question in the meantime: does each adult hold a valid Greek AFM? Generali can only insure people who do."]
    return "\n".join(out + ["", "Best regards,", ""] + SIGNATURE)


def _plan_block(r: Routing) -> list[str]:
    """Bullets and waiting periods for the plans in play. A plan the lead did not name is not named in the reply."""
    plans = r.plans or [DEFAULT_PLAN]
    out: list[str] = []
    for p in plans:
        if r.plans and len(plans) > 1:
            out += [f"{PLAN_NAMES[p]}:", ""]
        out += [f"* {x}" for x in PLAN_POINTS[p]] + ["", PLAN_WAITS[p], ""]
    return out


def draft_reply(r: Routing, name: str = "") -> str:
    """A first draft for the broker to edit. The mixed track follows the broker's own draft for lead 001;
    facts the broker has not confirmed are [CONFIRM] markers, never filled in."""
    who = f"Dear {name}," if name else "Hello,"
    asks = list(ASKS)
    if r.afm != "has":
        asks.insert(1, AFM_ASK)
    questions = [f"{i}. {a}" for i, a in enumerate(asks, 1)]
    left = [h for h in r.reviews if h.rule not in ("diagnostics", "zero_deductible")]  # answered by the plan facts
    review = (["I will also check the policy wording on: " + "; ".join(h.label.lower() for h in left) + ".", ""] if left else [])
    sign = ["Best regards,", ""] + SIGNATURE

    if r.track == INTERNATIONAL:
        out = [who, "", "Thank you for your enquiry. " + DISCLOSURE, "",
               "Generali's plans are local Greek policies and can only be issued to someone with a valid Greek tax number (AFM). "
               "Since you do not have one, Generali is not an option for you at this stage. If that changes, I would be glad to revisit it.", "",
               *_acknowledge(r),
               f"What I can do is compare international health plans for you from providers such as {_CARRIERS}.", ""]
    elif r.track == GENERALI:
        out = [who, "", "Thank you for your enquiry. " + DISCLOSURE, "",
               *_acknowledge(r), "Generali covers hospitalisation in Greece and, within its partner network, on a recent Generali quotation:", ""]
        out += _plan_block(r) + _generali_position(r) + [" ".join(_generali_sentences(r)), ""] + review
    else:  # MIXED
        wants = _join([_WANTS[h.rule] for h in r.gaps if h.rule in _WANTS])
        out = [who, "",
               "Thank you for your enquiry and for considering Generali as your health insurance provider. Generali is a well-known insurer "
               "in Greece, distinguished for its hospital cover and the range of benefits it offers.", "",
               *_acknowledge(r),
               "To be fully transparent about your requirements: Generali's programmes cover hospitalisation in Greece very well, "
               "but doctors, tests and emergency visits are covered mainly within their partner network. " + _OWN_DOCTOR[LIFE_ON in (r.plans or [DEFAULT_PLAN])]
               + " In more detail, on a recent Generali quotation:", ""]
        out += _plan_block(r) + [
               f"Since you are looking for {wants}, we would recommend an international private medical insurance (IPMI) plan, "
               "alongside, or instead of, a Generali plan.", "",
               BRIDGE + f" That means we can compare Generali with international providers including {_CARRIERS}, so you can see both routes. "
               + COMMISSION.replace("the insurer whose policy you choose", "the insurer you choose"), "",
               "IPMI plans can combine:", ""]
        out += [f"* {_IPMI_POINTS[h.rule]}" for h in r.gaps if h.rule in _IPMI_POINTS] + [""]
        out += ["If these are not a high priority, we can instead provide a Generali hospital cover quotation alongside the IPMI one, "
                "so you can compare both and decide what suits you best."
                + (" Generali requires a valid Greek AFM for each adult." if r.afm != "has" else ""), "",
                *_generali_position(r, skip=("out_of_network",)),
                " ".join(_generali_sentences(r)), "",
                f"For the international options we will also provide {_provide(r)}.", ""] + review

    out += ["To prepare your quotation, please send us:"] + questions + [""] + sign
    return "\n".join(out)
