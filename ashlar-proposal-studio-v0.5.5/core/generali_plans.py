"""What each Generali plan offers, kept separately so the lead router never mixes them up.

Sources (benefit terms only, no personal data and no individual prices):
* Life On: a Generali Life On quotation dated 21/10/2026 (modules Prevention Standard, Doctors & Exams Premium,
  Hospital Premium Flexi, Rehabilitation Standard, basic life and supplementary covers), plus the user's note that
  the participation (excess) is voluntary and can be 0, 750, 1,500, 3,000, 5,000 or 10,000 euros.
* Medical Prime: quote 08547743 and the Medical Prime booklet (Generali, 19 spreads).
* Partner hospital list: pasted by the broker from generali.gr (Cooperating hospitals page).

Every figure comes from one adult's quotation, so replies flag it [CONFIRM] against the applicant's own quote.
Statuses for a request: wording (the documents answer it), confirm (not settled, ask Generali), partial (part of it
is offered), not_offered (the documents give no such benefit).
"""
from __future__ import annotations

LIFE_ON = "life_on"
MEDICAL_PRIME = "medical_prime"
PLAN_NAMES = {LIFE_ON: "Life On", MEDICAL_PRIME: "Medical Prime"}
DEFAULT_PLAN = LIFE_ON  # the plan Generali wants promoted when a lead names none

# Life On: the participation is chosen by the applicant and lowers the premium as it rises.
LIFE_ON_PARTICIPATION = (0, 750, 1500, 3000, 5000, 10000)

# What the Generali quoting screen offers for Life On (broker's screenshots, 22/10/2026). Only the terms of the tiers we hold
# documents for (Prevention Standard, Doctors & Exams Premium, Hospital Premium Flexi, Rehabilitation Standard) may be described
# in a reply; the other tiers are listed so the broker can see what exists, and are never promised.
LIFE_ON_HOSPITAL_CAPITAL = (620000, 940000, 1240000)   # annual limit options for Hospital Premium Flexi
LIFE_ON_HOSPITAL_ROOMS = ("A", "B")
LIFE_ON_TIERS = {
    "Prevention": ["Basic", "Standard", "Premium", "On Demand"],
    "Doctors & Exams": ["Basic", "Standard", "Premium", "On Demand"],
    "Hospital": ["Premium Flexi", "Premium Flexi Plus", "Premium", "Basic", "Standard", "Fee PLUS add-on"],
    "Rehabilitation": ["Basic", "Standard", "Premium"],
    "Basic life cover": ["Life", "Life Plus"],
}
LIFE_ON_LIFE_CAPITAL = (500, 10000, 20000, 30000, 50000)  # basic life cover capital options on the quoting screen
LIFE_ON_SUPPLEMENTARY = ["Income loss from temporary disability (accident, or accident or illness)", "Post-accident care",
                         "Hospital daily allowance", "Accidental death", "Permanent total disability (accident or illness)",
                         "Permanent total or partial disability (accident)", "Protection of future insurability", "Surgical allowance"]

# Partner hospitals (broker's paste from generali.gr). Medical Prime has its own, narrower partners.
LIFE_ON_NETWORK = {
    "Athens": ["Athens Eye Hospital", "Henry Dunant", "Euroclinic Athens", "Euroclinic Children", "ENT Clinic Karras",
               "Iaso", "Iaso Children", "Iatriko Athinon", "Pediatric Center Athens", "Iatriko Peristeriou",
               "Iatriko Psychikou", "Iatropolis", "Leukos Stavros", "Metropolitan Hospital", "Metropolitan General",
               "Mitera", "Mitera Children", "Therapis", "Hygeia"],
    "Thessaloniki": ["Agios Lucas", "Euromedica General Clinic", "Euromedica Kyanous Stavros",
                     "Iatriko Diavalkaniko Thessaloniki"],
    "Other regions": ["Creta Interclinic (Crete)", "Iaso Thessalias (Thessaly)", "Ophthalmica", "Laservision"],
}
MEDICAL_PRIME_NETWORK = {
    "Athens": ["Hygeia", "Mitera"],       # Hygeia Group
    "Thessaloniki": ["Euromedica General Clinic"],
}


def network_text(plan: str) -> str:
    net = LIFE_ON_NETWORK if plan == LIFE_ON else MEDICAL_PRIME_NETWORK
    return "; ".join(f"{city}: {', '.join(names)}" for city, names in net.items())


LIFE_ON_POINTS = [
    "Hospital cover (Hospital Premium Flexi) with an annual capital of €620,000, €940,000 or €1,240,000 per person (the quote I have is "
    "€620,000): 100% in Greece and abroad (95% in the USA and Canada) after your participation, and 100% with no participation in public "
    "hospitals. [CONFIRM: figures are from a recent quote for one adult]",
    "Voluntary participation (excess) of €0, €750, €1,500, €3,000, €5,000 or €10,000 a year; a higher participation lowers the premium. "
    "With €750 or €1,500, the seven listed serious-illness categories carry no participation.",
    "Partner hospitals are paid directly by Generali, so you pay only your participation. If another insurer, such as EOPYY, pays more "
    "than your participation, a bonus of up to €5,000 a year applies. [CONFIRM: how the bonus applies if you use EOPYY]",
    "Your choice of room: A (private) or B (semi-private). Room A has a higher premium than the same cover with room B. The quote I have is for room A.",
    "Wide network of partner hospitals, including " + network_text(LIFE_ON) + ".",
    "Life On is built from modules, so you can add or drop prevention, doctors and exams, hospital, rehabilitation, life cover and accident covers to suit you.",
    "Doctors & Exams Premium: unlimited visits to partner doctors at €20 per visit, a family doctor at €40 for the first visit and €12 "
    "after that, and four visits a year to a doctor of your own choice outside the network, reimbursed up to €20 a visit. "
    "Diagnostic tests at partner diagnostic centres up to €2,500 a year with no participation, on a referral from a partner doctor.",
    "Prevention Standard: an annual check-up (19 tests for adults, 11 for children), with other preventive exams at preferential prices.",
    "Also in the hospital cover: doctor visits and tests up to 30 days before, and tests, medication and physiotherapy up to 60 days after, "
    "the hospital stay; day surgery with no participation; a private nurse for up to 30 days; emergency medical transport up to €5,000 a year "
    "in Greece and the EU; a second medical opinion for 13 serious conditions, up to twice per condition; and the option of continuing cover "
    "for protected members without a new health check.",
    "Around the hospital stay: preventive mastectomy or ovary and tube removal up to €5,000 (once) and breast reconstruction up to €5,000 (once); "
    "psychological support at €50 a session for up to 10 sessions; legal expenses up to €3,000 a year; emergencies without admission up to €500 "
    "per incident, and listed medical procedures up to €1,000 a year, at special partner hospitals with no participation; a newborn allowance of "
    "€1,200 in the third insurance year and €1,800 in the fourth.",
    "If you are hospitalised and do not submit expenses: a daily allowance of €100 (€150 in intensive care) for up to 15 days, and a surgery "
    "allowance from €100 to €2,000 depending on the class of operation.",
]

LIFE_ON_WAITS = ("Waiting periods (Hospital Premium Flexi, Article 5): appendectomy the first three months of the first year; "
                 "nasal growths and tonsillectomy the first year; bowel and genital conditions (except malignancy) and pregnancy complications "
                 "the first two years; deviated septum, spinal conditions and removal of moles and papillomas the first three years. "
                 "Doctors & Exams Premium: spinal and knee conditions after the first year. Optional dental cover applies after two years "
                 "and aesthetic medicine after three. [CONFIRM against the full wording before sending]")

MEDICAL_PRIME_POINTS = [
    "Hospital stays in Greece covered at 100% with no participation, up to €300,000 a year per person, in Generali's partner hospitals: "
    "Hygeia and Mitera (Hygeia Group) in Athens and Euromedica in Thessaloniki. The room is B (semi-private) by default, and you can upgrade to room A (private) for a contribution of €100 a night. "
    "Partner hospitals settle directly with Generali. "
    "[CONFIRM: these figures come from a recent quote for one adult and may differ on your family quote; the quote shows no participation 'with use of a social insurance fund', so check how it applies if you do not use one]",
    "You choose your participation when the policy starts, and a higher one lowers the premium. [CONFIRM: the participation options for this plan]",
    "Unlimited scheduled visits to partner doctors, €10 per visit.",
    "Emergencies: a visit to a partner doctor on duty has no participation; a partner specialist called out in an emergency costs €50.",
    "Diagnostic tests and medical procedures: up to €1,500 per insurance year, with 15% participation, on referral from a partner doctor.",
    "Physiotherapy: up to €1,000 per insurance year, with 15% participation.",
    "Annual preventive check-up (14 tests for adults, 5 for children), €10 each, available from six months after the start. "
    "Adults can also add specialised preventive exams once a year, from one year after the start.",
    "Chronic conditions you declare, known or unknown, can be covered after the waiting period, and children are covered up to age 25 if they study.",
]
MEDICAL_PRIME_WAITS = ("Waiting periods: doctors and tests are covered from one month after the start. For hospital cover, conditions you "
                       "declare and already know about are covered after two years (five years if they relate to a malignancy); conditions "
                       "that were unknown and undeclared after one or two years, depending on the condition; and congenital conditions "
                       "(other than cardiac) and listed special conditions after ten years.")

PLAN_POINTS = {LIFE_ON: LIFE_ON_POINTS, MEDICAL_PRIME: MEDICAL_PRIME_POINTS}
PLAN_WAITS = {LIFE_ON: LIFE_ON_WAITS, MEDICAL_PRIME: MEDICAL_PRIME_WAITS}

# request id -> (status, sentence the client may read). One table per plan.
PLAN_WORDING: dict[str, dict[str, tuple[str, str]]] = {
    LIFE_ON: {
        "hospital_list": ("wording", ""), "waiting_periods": ("wording", ""), "annual_limits": ("wording", ""),
        "deductibles": ("wording", ""), "exclusions": ("wording", ""), "pre_existing": ("wording", ""),
        "info_needed": ("wording", ""), "direct_billing": ("wording", ""), "preventive": ("wording", ""),
        "premium": ("confirm", ""), "underwriting": ("confirm", ""), "renewal_age": ("confirm", ""), "start_date": ("confirm", ""),
        "out_of_network": ("partial", "Doctors outside Generali's partner network are not reimbursed in general; "
                                       "Doctors & Exams Premium reimburses four visits a year to a doctor of your own choice, up to €20 a visit."),
        "prescriptions": ("not_offered", "Prescription medication is not covered under the doctors and tests cover; "
                                          "chronic-condition medication is available only through a separate add-on."),
        "overseas": ("partial", "Hospital stays abroad are covered at 100% (95% in the USA and Canada) after your participation on the quotation I have; "
                                "outpatient care abroad is not part of the programme. [CONFIRM against the wording]"),
    },
    MEDICAL_PRIME: {
        "hospital_list": ("wording", ""), "waiting_periods": ("wording", ""), "annual_limits": ("wording", ""),
        "deductibles": ("wording", ""), "exclusions": ("wording", ""), "pre_existing": ("wording", ""),
        "info_needed": ("wording", ""), "direct_billing": ("wording", ""), "preventive": ("wording", ""),
        "premium": ("confirm", ""), "underwriting": ("confirm", ""), "renewal_age": ("confirm", ""), "start_date": ("confirm", ""),
        "out_of_network": ("not_offered", "Reimbursement for doctors outside Generali's partner network is not part of the programme."),
        "prescriptions": ("not_offered", "Prescription medication is not covered under the doctors and tests cover; "
                                          "chronic-condition medication is available only through a separate add-on."),
        "overseas": ("partial", "Hospital stays abroad are covered at 100% (90% in the USA and Canada), with prior approval and your social insurance "
                               "in force; you pay and claim the money back, so there is no direct billing abroad. Outpatient care abroad is not "
                               "part of the programme. [CONFIRM against the wording]"),
    },
}
_RANK = {"not_offered": 0, "confirm": 1, "partial": 2, "wording": 3}


def wording_for(plans: list[str]) -> dict[str, tuple[str, str]]:
    """The wording table for the plans in play. With two plans, a point is promised only if both support it."""
    plans = plans or [DEFAULT_PLAN]
    if len(plans) == 1:
        return PLAN_WORDING[plans[0]]
    out: dict[str, tuple[str, str]] = {}
    for rid in PLAN_WORDING[plans[0]]:
        rows = [(p, PLAN_WORDING[p][rid]) for p in plans]
        kinds = {k for _, (k, _) in rows}
        texts = {t for _, (_, t) in rows}
        if len(kinds) == 1 and len(texts) == 1:
            out[rid] = rows[0][1]
            continue
        worst = min(kinds, key=_RANK.get)
        text = " ".join(f"{PLAN_NAMES[p]}: {t}" for p, (k, t) in rows if t)
        out[rid] = ("partial" if worst == "not_offered" and text else worst, text)
    return out


# Structured Life On facts for the HTML email (plain text; the renderer escapes it). Same figures as LIFE_ON_POINTS.
LIFE_ON_ROWS = [
    ("Hospital cover", "Hospital Premium Flexi, with an annual capital of €620,000, €940,000 or €1,240,000 per person."),
    ("Reimbursement", "100% in Greece and abroad (95% in the USA and Canada) after your participation, and 100% with no participation in public hospitals."),
    ("Participation", "You choose it: €0, €750, €1,500, €3,000, €5,000 or €10,000 a year. A higher participation lowers the premium. "
                      "With €750 or €1,500, the seven listed serious-illness categories carry no participation."),
    ("Direct payment", "Generali pays partner hospitals directly, so you pay only your participation."),
    ("With EOPYY", "You can combine Life On with a public or private insurer such as EOPYY. If the other insurer pays more than your "
                   "participation, a bonus of up to €5,000 a year applies."),
    ("Your room", "Room A (private) or room B (semi-private). Room A carries a higher premium than the same cover with room B. "
                  "Our reference quotation is for room A."),
]
LIFE_ON_MODULE_ROWS = [
    ("Doctors & Exams Premium", "Unlimited visits to partner doctors at €20 per visit. A family doctor at €40 for the first visit and €12 after that. "
        "Four visits a year to a doctor of your own choice outside the network, reimbursed up to €20 a visit. Diagnostic tests at partner "
        "diagnostic centres up to €2,500 a year with no participation, on referral from a partner doctor."),
    ("Prevention Standard", "An annual check-up (19 tests for adults, 11 for children), with other preventive exams at preferential prices."),
]
LIFE_ON_AROUND = [
    "Doctor visits and tests up to 30 days before the stay, and medication, lab tests and physiotherapy up to 60 days after it",
    "Day surgery with no participation", "A private nurse for up to 30 days",
    "Emergency medical transport up to €5,000 a year in Greece and the EU",
    "A second medical opinion for 13 serious conditions, up to twice per condition",
    "Continued cover for protected members without a new health check",
    "Preventive mastectomy, or ovary and tube removal, up to €5,000 (once), and breast reconstruction up to €5,000 (once)",
    "Psychological support at €50 a session, for up to 10 sessions", "Legal expenses up to €3,000 a year",
    "Emergencies without admission up to €500 per incident, and listed medical procedures up to €1,000 a year, at special partner hospitals with no participation",
    "A newborn allowance of €1,200 in the third insurance year and €1,800 in the fourth",
]
LIFE_ON_NO_EXPENSES = ["A daily allowance of €100 (€150 in intensive care) for up to 15 days",
                       "A surgery allowance from €100 to €2,000, depending on the class of operation"]
LIFE_ON_WAIT_ROWS = [
    ("Appendectomy", "The first three months of the first year"), ("Nasal growths and tonsillectomy", "The first year"),
    ("Bowel and genital conditions (except malignancy), pregnancy complications", "The first two years"),
    ("Deviated septum, spinal conditions, removal of moles and papillomas", "The first three years"),
    ("Doctors & Exams Premium: spinal and knee conditions", "After the first year"),
    ("Optional dental cover", "After two years"), ("Optional aesthetic medicine", "After three years"),
]
# Generali pages (Greek). The policy wording itself is issued with the quotation.
URL_DOCS = "https://www.generali.gr/el/eksyphrethsh-pelatwn/enimerotika-eggrafa/"
URL_HOSPITALS = "https://www.generali.gr/el/eksyphrethsh-pelatwn/synergazomena-nosileytika-idrymata/"
URL_DIAGNOSTICS = "https://www.generali.gr/el/eksyphrethsh-pelatwn/symvevlimena-diagnwstika-kentra/"
URL_LIFE_ON = "https://www.generali.gr/el/idiwtiki-asfaleia-ugeias/life-on-programma-asfalishs-ygeias/"
