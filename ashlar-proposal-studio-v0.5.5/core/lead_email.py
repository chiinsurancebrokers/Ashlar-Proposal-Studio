"""Render a routed lead reply as an Ashlar-styled HTML email, a plain-text twin, and (optionally) a PDF.

The words come from core/lead_router.py and core/generali_plans.py, so the email can never promise more than the
Generali documents say. This module only lays them out in the Ashlar visual system: limestone ground, ink type,
hairline mortar rules between blocks, square corners, one oxblood word in the headline.

    from core.lead_router import route
    from core.lead_email import render_html, render_text, render_pdf
    r = route(lead_text)
    html = render_html(r, name="Julian")
"""
from __future__ import annotations

import html as _html
import re
from pathlib import Path

from core.generali_plans import (DEFAULT_PLAN, LIFE_ON, LIFE_ON_NETWORK, LIFE_ON_PARTICIPATION, MEDICAL_PRIME,
                                 PLAN_NAMES)
from core.lead_router import (ASKS, AFM_ASK, BRIDGE, COMMISSION, GENERALI, INTERNATIONAL, MIXED, SIGNATURE, _CARRIERS,
                              _REQ, _generali_position, Routing)

PAPER, FINE, MORTAR, INK, OX, VER, AMB = "#F2EDE4", "#F9F6EE", "#D7CDBC", "#1B2432", "#70181C", "#4A6E6B", "#B88A2B"
SERIF = "Fraunces,Georgia,'Times New Roman',serif"
SANS = "'Instrument Sans','Helvetica Neue',Arial,sans-serif"
MONO = "'JetBrains Mono','Courier New',monospace"
B = f"border:1px solid {MORTAR};"

U_DOCS = "https://www.generali.gr/el/eksyphrethsh-pelatwn/enimerotika-eggrafa/"
U_HOSP = "https://www.generali.gr/el/eksyphrethsh-pelatwn/synergazomena-nosileytika-idrymata/"
U_DIAG = "https://www.generali.gr/el/eksyphrethsh-pelatwn/symvevlimena-diagnwstika-kentra/"
U_LIFEON = "https://www.generali.gr/el/idiwtiki-asfaleia-ugeias/life-on-programma-asfalishs-ygeias/"
U_PRIME = "https://www.generali.gr/el/idiwtiki-asfaleia-ugeias/nosokomeiako-programma-asfalishs-ygeias-medical-prime/"
FONT_LINK = ('<link href="https://fonts.googleapis.com/css2?family=Fraunces:ital,opsz@0,9..144;1,9..144'
             '&family=Instrument+Sans&family=JetBrains+Mono&display=swap" rel="stylesheet">')
# Where each request is answered from. Requests not listed here are answered in the text only.
REQUEST_LINK = {"hospital_list": U_HOSP, "direct_billing": U_HOSP, "out_of_network": U_DIAG, "waiting_periods": U_DOCS,
                "exclusions": U_DOCS, "annual_limits": U_DOCS, "deductibles": U_DOCS}
EOPYY_NOTE = ("We have already noted that you want to be independent of EOPYY, and we mention this benefit "
              "only for your information.")

_E = _html.escape


def _a(t: str, u: str) -> str:
    return f'<a href="{u}" style="color:{INK};text-decoration:underline">{t}</a>'


def _eyebrow(t: str, color: str = INK) -> str:
    return (f'<div style="font-family:{MONO};font-size:10px;letter-spacing:.14em;text-transform:uppercase;'
            f'color:{color};margin:0 0 8px">{_E(t)}</div>')


def _h2(t: str, color: str = INK) -> str:
    return (f'<div style="font-family:{SERIF};font-size:24px;line-height:1.2;font-weight:400;letter-spacing:-.01em;'
            f'color:{color};margin:0 0 12px">{t}</div>')


def _p(t: str, color: str = INK, size: int = 15, m: str = "0 0 12px") -> str:
    return f'<p style="font-family:{SANS};font-size:{size}px;line-height:1.6;color:{color};margin:{m}">{t}</p>'


def _badge(label: str, dot: str) -> str:
    return (f'<span style="display:inline-block;{B}padding:2px 7px;font-family:{MONO};font-size:10px;'
            f'letter-spacing:.1em;text-transform:uppercase;color:{INK};background:{FINE}">'
            f'<span style="color:{dot}">&#9679;</span>&nbsp;{_E(label)}</span>')


def _ul(items: list[str], color: str = INK) -> str:
    mark = VER if color == INK else "#9db5b2"
    rows = "".join(
        f'<tr><td valign="top" style="font-family:{MONO};font-size:12px;color:{mark};padding:3px 10px 3px 0;width:18px">&mdash;</td>'
        f'<td style="font-family:{SANS};font-size:15px;line-height:1.55;color:{color};padding:3px 0">{i}</td></tr>' for i in items)
    return f'<table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%">{rows}</table>'


def _block(inner: str, bg: str = FINE, pad: str = "24px 28px") -> str:
    return f'<tr><td style="{B}background:{bg};padding:{pad}">{inner}</td></tr>'


def _rows(pairs: list[tuple[str, str]], label_w: int = 150) -> str:
    out = "".join(
        f'<tr><td valign="top" width="{label_w}" style="{B}background:{PAPER};padding:12px 14px;font-family:{MONO};font-size:10px;'
        f'letter-spacing:.14em;text-transform:uppercase;color:{INK}">{k}</td>'
        f'<td valign="top" style="{B}background:{FINE};padding:12px 16px;font-family:{SANS};font-size:15px;line-height:1.55;color:{INK}">{v}</td></tr>'
        for k, v in pairs)
    return f'<table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%" style="border-collapse:collapse">{out}</table>'


# ---- plan content (every line traces to core/generali_plans.py and the Generali documents) -------------------------
def _life_on_rows(eopyy: bool) -> list[tuple[str, str]]:
    part = ", ".join(f"&euro;{v:,}" for v in LIFE_ON_PARTICIPATION[:-1]) + f" or &euro;{LIFE_ON_PARTICIPATION[-1]:,}"
    bonus = ("You can combine Life On with a public or private insurer such as EOPYY. If the other insurer pays more than your "
             "participation, a bonus of up to &euro;5,000 a year applies." + (" " + EOPYY_NOTE if eopyy else ""))
    return [
        ("Hospital cover", "Hospital Premium Flexi, with an annual capital of &euro;620,000, &euro;940,000 or &euro;1,240,000 per person."),
        ("Reimbursement", "100% in Greece and abroad (95% in the USA and Canada) after your participation, and 100% with no participation in public hospitals."),
        ("Participation", f"You choose it: {part} a year. A higher participation lowers the premium. With &euro;750 or &euro;1,500, "
                          "the seven listed serious-illness categories carry no participation."),
        ("Direct payment", "Generali pays partner hospitals directly, so you pay only your participation."),
        ("With EOPYY", bonus),
        ("Your room", "Room A (private) or room B (semi-private). Room A carries a higher premium than the same cover with room B. "
                      "Our reference quotation is for room A."),
    ]


_LIFE_ON_MODULES = [
    ("Doctors &amp; Exams Premium", "Unlimited visits to partner doctors at &euro;20 per visit. A family doctor at &euro;40 for the first visit and "
     "&euro;12 after that. Four visits a year to a doctor of your own choice outside the network, reimbursed up to &euro;20 a visit. "
     "Diagnostic tests at partner diagnostic centres up to &euro;2,500 a year with no participation, on referral from a partner doctor."),
    ("Prevention Standard", "An annual check-up (19 tests for adults, 11 for children), with other preventive exams at preferential prices."),
]
_LIFE_ON_AROUND = [
    "Doctor visits and tests up to 30 days before the stay, and medication, lab tests and physiotherapy up to 60 days after it",
    "Day surgery with no participation", "A private nurse for up to 30 days",
    "Emergency medical transport up to &euro;5,000 a year in Greece and the EU",
    "A second medical opinion for 13 serious conditions, up to twice per condition",
    "Continued cover for protected members without a new health check",
    "Preventive mastectomy, or ovary and tube removal, up to &euro;5,000 (once), and breast reconstruction up to &euro;5,000 (once)",
    "Psychological support at &euro;50 a session, for up to 10 sessions", "Legal expenses up to &euro;3,000 a year",
    "Emergencies without admission up to &euro;500 per incident, and listed medical procedures up to &euro;1,000 a year, at special partner hospitals with no participation",
    "A newborn allowance of &euro;1,200 in the third insurance year and &euro;1,800 in the fourth",
]
_LIFE_ON_NOEXP = ["A daily allowance of &euro;100 (&euro;150 in intensive care) for up to 15 days",
                  "A surgery allowance from &euro;100 to &euro;2,000, depending on the class of operation"]
_LIFE_ON_WAITS = [
    ("Appendectomy", "The first three months of the first year"), ("Nasal growths and tonsillectomy", "The first year"),
    ("Bowel and genital conditions (except malignancy), pregnancy complications", "The first two years"),
    ("Deviated septum, spinal conditions, removal of moles and papillomas", "The first three years"),
    ("Doctors &amp; Exams Premium: spinal and knee conditions", "After the first year"),
    ("Optional dental cover", "After two years"), ("Optional aesthetic medicine", "After three years"),
]
_PRIME_ROWS = [
    ("Hospital cover", "Hospital stays in Greece covered at 100% with no participation, up to &euro;300,000 a year per person, in Generali&rsquo;s "
     "partner hospitals: Hygeia and Mitera (Hygeia Group) in Athens and Euromedica in Thessaloniki."),
    ("Your room", "Room B (semi-private) by default. You can upgrade to room A (private) for a contribution of &euro;100 a night."),
    ("Direct payment", "Generali pays partner hospitals directly."),
    ("Participation", "You choose your participation when the policy starts, and a higher one lowers the premium."),
    ("Doctors", "Unlimited scheduled visits to partner doctors, &euro;10 per visit. In an emergency, a visit to a partner doctor on duty has no "
     "participation, and a partner specialist called out costs &euro;50."),
    ("Tests and physio", "Diagnostic tests and medical procedures up to &euro;1,500 per insurance year, with 15% participation, on referral from "
     "a partner doctor. Physiotherapy up to &euro;1,000 per insurance year, with 15% participation."),
    ("Prevention", "An annual check-up (14 tests for adults, 5 for children), &euro;10 each, from six months after the start. Adults can add "
     "specialised preventive exams once a year, from one year after the start."),
    ("Chronic conditions", "Chronic conditions you declare, known or unknown, can be covered after the waiting period. Children are covered up to age 25 if they study."),
]
_PRIME_WAITS = [
    ("Doctors and tests", "From one month after the start"),
    ("Hospital: declared conditions you already know about", "After two years (five years for a malignancy)"),
    ("Hospital: conditions unknown and undeclared at the start", "After one or two years, depending on the condition"),
    ("Hospital: congenital conditions (other than cardiac) and listed special conditions", "After ten years"),
]


def _network_table() -> str:
    labels = {"Athens": "Athens", "Thessaloniki": "Thessaloniki", "Other regions": "Other regions"}
    rows = "".join(
        f'<tr><td valign="top" width="150" style="{B}background:{PAPER};padding:12px 14px;font-family:{MONO};font-size:10px;'
        f'letter-spacing:.14em;text-transform:uppercase">{labels[k]}</td><td style="{B}background:{FINE};padding:12px 16px;'
        f'font-family:{SANS};font-size:14px;line-height:1.6">{_E(", ".join(v))}</td></tr>' for k, v in LIFE_ON_NETWORK.items())
    return f'<table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%" style="border-collapse:collapse">{rows}</table>'


def _wait_table(rows: list[tuple[str, str]]) -> str:
    body = "".join(
        f'<tr><td style="{B}background:{FINE};padding:10px 14px;font-family:{SANS};font-size:14px;line-height:1.5">{a}</td>'
        f'<td width="230" style="{B}background:{FINE};padding:10px 14px">{_badge(b, AMB)}</td></tr>' for a, b in rows)
    return f'<table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%" style="border-collapse:collapse">{body}</table>'


def _plans(r: Routing) -> list[str]:
    return r.plans or [DEFAULT_PLAN]


def email_subject(r: Routing, family: bool = False) -> str:
    who = "Your family's health insurance" if family else "Your health insurance enquiry"
    if r.track == INTERNATIONAL:
        return f"{who}: international plans compared"
    names = " and ".join(PLAN_NAMES[p] for p in _plans(r))
    return f"{who}: {names} from Generali" + (", with an international alternative" if r.track == MIXED else "")


def _headline(r: Routing) -> str:
    ox = lambda w: f'<i style="color:{OX}">{w}</i>'
    if r.track == INTERNATIONAL:
        return f"Health cover that goes where you do, compared across {ox('leading')} international providers."
    if r.track == MIXED:
        return f"Hospital cover in Greece, with a route to {ox('international')} cover if you need it."
    return f"Hospital cover in Greece, with the benefits arranged around {ox('you')}."


def _acknowledge_html(r: Routing) -> str:
    labels = [x for x in r.requests if _REQ[x][0]]
    if not labels:
        return ""
    if len(labels) > 7:
        return _p("You sent a detailed list of questions. This email covers each of them, and the quotation settles the rest.")
    parts = [(_a(_REQ[x][0], REQUEST_LINK[x]) if x in REQUEST_LINK else _E(_REQ[x][0])) for x in labels]
    joined = parts[0] if len(parts) == 1 else ", ".join(parts[:-1]) + " and " + parts[-1]
    tail = ("This email answers each of these, and the full exclusions follow in the policy wording that comes with your quotation."
            if "exclusions" in r.requests else "This email answers each of these, and anything that depends on your own quotation follows with it.")
    return _p(f"You asked about {joined}. {tail}")


def _generali_blocks(r: Routing) -> list[str]:
    out: list[str] = []
    plans = _plans(r)
    for plan in plans:
        tag = f"{PLAN_NAMES[plan]}: " if len(plans) > 1 else ""
        if plan == LIFE_ON:
            intro = ("Life On covers hospital stays very well. Doctors, tests and emergency visits are covered mainly within Generali&rsquo;s "
                     "partner network, and visits to a doctor of your own choice outside it are limited to a set number a year. "
                     + ("Generali&rsquo;s flagship plan is Life On, and this is what it covers." if not r.plans else "This is what Life On covers."))
            out.append(_block(_eyebrow("Where Life On is strongest" if len(plans) == 1 else "Life On") + _h2(tag + "Hospitalisation in Greece is its core")
                              + _p(intro, m="0 0 16px") + _rows(_life_on_rows(r.mentions_eopyy)), FINE))
            out.append(_block(_eyebrow("Partner hospitals") + _h2("A wide network across Greece") + _network_table(), FINE))
            out.append(_block(_eyebrow("Built from modules") + _h2("Add the cover you need")
                              + _p("You can add or drop prevention, doctors and exams, hospital, rehabilitation, life cover and accident covers.", m="0 0 16px")
                              + _rows(_LIFE_ON_MODULES), FINE))
            out.append(_block(_eyebrow("Also in the hospital cover") + _h2("Around the stay") + _ul(_LIFE_ON_AROUND) + '<div style="height:14px"></div>'
                              + _eyebrow("If you are hospitalised and do not submit expenses") + _ul(_LIFE_ON_NOEXP), FINE))
            out.append(_block(_eyebrow("Waiting periods") + _h2("What applies, and when")
                              + _p("Hospital Premium Flexi, Article 5, and Doctors &amp; Exams Premium. Some conditions are covered only after a waiting "
                                   "period from the start of the policy.", m="0 0 14px") + _wait_table(_LIFE_ON_WAITS), FINE))
        else:
            out.append(_block(_eyebrow("Medical Prime") + _h2(tag + "Hospital cover with the Hygeia Group and Euromedica")
                              + _p("Medical Prime is built around hospital cover in Greece, with doctors, tests and prevention inside the partner network.", m="0 0 16px")
                              + _rows(_PRIME_ROWS), FINE))
            out.append(_block(_eyebrow("Waiting periods") + _h2("What applies, and when") + _wait_table(_PRIME_WAITS), FINE))
    pos = [x for x in _generali_position(r, skip=("out_of_network",)) if x]
    if pos:
        sentences = [s.strip() for s in re.split(r"(?<=[.\]])\s+(?=[A-Z])", pos[0]) if s.strip()]
        sentences = [re.sub(r"\s*\[CONFIRM[^\]]*\]", "", s) for s in sentences]
        out.append(_block(_eyebrow("Where Generali stops") + _h2("What it does not offer, and where we can help")
                          + _ul([_E(s) for s in sentences if s]), FINE))
    return out


def _ipmi_block(r: Routing) -> str:
    from core.lead_router import _IPMI_POINTS
    pts = [_IPMI_POINTS[h.rule] for h in r.gaps if h.rule in _IPMI_POINTS] + [
        "Comprehensive benefits, such as mental health, maternity and complementary therapies"]
    if r.track == INTERNATIONAL:
        lead = ("Generali&rsquo;s plans are local Greek policies and can be issued only to someone with a valid Greek tax number (AFM), "
                "so Generali is not an option for you at this stage. If that changes, we would be glad to revisit it. "
                f"What we can do is compare international health plans from providers such as {_CARRIERS}.")
        head = "International plans, compared for you"
    else:
        wants = "free choice of private doctors and hospitals, and outpatient cover for doctors, specialists and tests"
        lead = (f"You asked for {wants}. For that, we would also like to offer you an international private medical insurance (IPMI) plan. "
                f"We can compare {_CARRIERS}, so you can see both routes side by side.")
        head = "An international plan, as an alternative"
    tail = ("" if r.track == INTERNATIONAL else
            _p("If these matter less to you, Life On on its own may be the simpler and more economical choice. We can quote it alongside the "
               "IPMI plan so you can decide with both in front of you.", FINE))
    return (f'<tr><td style="border:1px solid {INK};background:{INK};padding:28px">' + _eyebrow("If you want free choice of doctors", "#9db5b2")
            + _h2(head, FINE) + _p(lead, FINE) + _ul(pts, FINE) + '<div style="height:12px"></div>' + tail
            + _p(COMMISSION, FINE, 14, "0") + "</td></tr>")


def _links_block(r: Routing) -> str:
    items = [_a("Policy wordings and informational documents", U_DOCS) + " (Generali, Greek)"]
    for p in _plans(r):
        items.append(_a(f"{PLAN_NAMES[p]} programme page", U_LIFEON if p == LIFE_ON else U_PRIME) + " (Generali, Greek)")
    items += [_a("Partner hospitals", U_HOSP) + " (Generali, Greek)", _a("Partner doctors and diagnostic centres", U_DIAG) + " (Generali, Greek)"]
    return _block(_eyebrow("Read it in Generali's own words") + _h2("Policy wordings and partner networks")
                  + _p("Generali publishes these in Greek. Your quotation will include the policy wording for the modules you choose.", m="0 0 12px") + _ul(items), FINE)


def _asks(r: Routing) -> list[str]:
    asks = list(ASKS)
    if r.afm != "has":
        asks.insert(1, AFM_ASK)
    return asks


def render_html(r: Routing, name: str = "", family: bool = False, fonts_css: str = "") -> str:
    """The full email. `fonts_css` is optional @font-face CSS (used for the PDF so the brand fonts are embedded)."""
    who = _E(name)
    mail = "mailto:c.iatropoulos@ashlarassurance.com?subject=Details%20for%20my%20health%20insurance%20quotation"
    btn = (f'<a href="{mail}" style="display:inline-block;background:{INK};color:{FINE};border:1px solid {INK};padding:12px 20px;'
           f'font-family:{SANS};font-size:14px;text-decoration:none">Reply with your details&nbsp;<span style="font-family:{MONO}">&rarr;</span></a>')
    head = (f'<tr><td style="background:{INK};padding:18px 28px;border:1px solid {INK}"><span style="font-family:{MONO};font-size:11px;'
            f'letter-spacing:.2em;text-transform:uppercase;color:{FINE}">Ashlar Assurance</span>'
            + (f'<span style="font-family:{MONO};font-size:10px;letter-spacing:.14em;text-transform:uppercase;color:#9db5b2;float:right">Prepared for {who}</span>' if name else "")
            + "</td></tr>")
    opening = (f'{_eyebrow("Your health insurance enquiry")}'
               f'<div style="font-family:{SERIF};font-size:34px;line-height:1.12;font-weight:400;letter-spacing:-.025em;color:{INK};margin:0 0 16px">{_headline(r)}</div>'
               + _p(f"Dear {who}," if name else "Hello,")
               + _p(("Thank you for your enquiry, and for considering Generali for your " + ("family&rsquo;s " if family else "") + "health insurance. "
                     "Generali is a well-established insurer in Greece, known for its hospital cover and the range of benefits that come with it.")
                    if r.track != INTERNATIONAL else "Thank you for your enquiry.")
               + _p(BRIDGE_HTML) + _acknowledge_html(r))
    body = head + _block(opening.rstrip(), PAPER, "32px 28px")
    if r.track != INTERNATIONAL:
        body += "".join(_generali_blocks(r))
    if r.track in (MIXED, INTERNATIONAL):
        body += _ipmi_block(r)
    elif r.track == GENERALI:
        body += _block(_p(COMMISSION, INK, 14, "0"), FINE)
    if r.track != INTERNATIONAL:
        body += _links_block(r)
    body += _block(_eyebrow("Next step") + _h2("What we need to prepare your quotation") + _ul([_E(a) for a in _asks(r)])
                   + '<div style="height:18px"></div>' + btn, FINE)
    body += _block(_p("The figures above come from recent Generali quotations for one adult. Your own quotation confirms the terms, and Generali "
                      "confirms final eligibility and premium after underwriting.", INK, 13, "0 0 12px") + _p(BRIDGE_DISCLOSURE_HTML, INK, 13, "0"), PAPER, "20px 28px")
    sig = (f'<p style="font-family:{SANS};font-size:15px;color:{INK};margin:0 0 10px">Best regards,</p>'
           f'<div style="font-family:{SERIF};font-size:20px;color:{INK}">{_E(SIGNATURE[0])}</div>'
           f'<div style="font-family:{MONO};font-size:10px;letter-spacing:.14em;text-transform:uppercase;color:{INK};margin:4px 0 10px">{_E(SIGNATURE[1])}</div>'
           f'<div style="font-family:{SANS};font-size:14px;line-height:1.7;color:{INK}">{_E(SIGNATURE[2])}<br>E <a href="mailto:c.iatropoulos@ashlarassurance.com" style="color:{INK}">c.iatropoulos@ashlarassurance.com</a>'
           f'<br>W <a href="https://ashlarassurance.com" style="color:{INK}">ashlarassurance.com</a></div>'
           f'<div style="font-family:{SERIF};font-style:italic;font-size:15px;color:{INK};margin-top:12px">{_E(SIGNATURE[-1])}</div>')
    body += _block(sig, PAPER, "24px 28px")
    subj = _E(email_subject(r, family))
    return (f'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<meta name="color-scheme" content="light"><title>{subj}</title>{FONT_LINK if not fonts_css else ""}'
            f'{"<style>" + fonts_css + "</style>" if fonts_css else ""}</head>'
            f'<body style="margin:0;padding:0;background:{PAPER}"><div style="display:none;max-height:0;overflow:hidden">{subj}</div>'
            f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background:{PAPER}"><tr><td align="center" style="padding:16px">'
            f'<table role="presentation" width="640" cellpadding="0" cellspacing="0" border="0" style="width:100%;max-width:640px;border-collapse:collapse">{body}</table>'
            f'</td></tr></table></body></html>')


# The bridge paragraph is split so the first part (collaboration) opens the email and the legal part closes it.
_SPLIT = BRIDGE.index("Ashlar Assurance is an independent")
BRIDGE_HTML = _E(BRIDGE[:_SPLIT].strip()).replace("&#x27;", "&rsquo;")
BRIDGE_DISCLOSURE_HTML = _E(BRIDGE[_SPLIT:].strip()).replace("&#x27;", "&rsquo;")


def render_text(r: Routing, name: str = "", family: bool = False) -> str:
    h = render_html(r, name, family)
    h = re.sub(r"<head>.*?</head>", "", h, flags=re.S)
    h = re.sub(r'<div style="display:none.*?</div>', "", h, flags=re.S)
    h = re.sub(r'<a href="mailto:([^"?]*)[^"]*"[^>]*>(.*?)</a>', r"\2", h)
    seen: set[str] = set()

    def _link(m: re.Match) -> str:
        url, label = m.group(1), m.group(2)
        if label == url or url in seen:
            return label
        seen.add(url)
        return f"{label} ({url})"
    h = re.sub(r'<a href="([^"]+)"[^>]*>(.*?)</a>', _link, h)
    h = re.sub(r"</(tr|p|div|li)>", "\n", h)
    h = h.replace("<br>", "\n")
    h = re.sub(r"</td>", " ", h)
    t = _html.unescape(re.sub(r"<[^>]+>", "", h))
    t = re.sub(r"[ \t]+", " ", t)
    t = re.sub(r"\n\s*\n+", "\n\n", t).strip()
    return f"Subject: {email_subject(r, family)}\n\n{t}\n"


def embedded_fonts_css() -> str:
    """@font-face rules with the Ashlar fonts (SIL OFL, latin subset) inlined, so a PDF does not depend on Google Fonts."""
    import base64
    d = Path(__file__).parent / "fonts"
    faces = [("Fraunces", "normal", "fraunces-latin-400-normal"), ("Fraunces", "italic", "fraunces-latin-400-italic"),
             ("Instrument Sans", "normal", "instrument-sans-latin-400-normal"), ("JetBrains Mono", "normal", "jetbrains-mono-latin-400-normal")]
    out = []
    for fam, style, f in faces:
        fp = d / f"{f}.woff2"
        if fp.exists():
            b64 = base64.b64encode(fp.read_bytes()).decode()
            out.append(f"@font-face{{font-family:'{fam}';font-style:{style};font-weight:400;src:url(data:font/woff2;base64,{b64}) format('woff2')}}")
    return "".join(out)


def render_pdf(html: str, out_path: str | Path) -> Path:
    """Print the email to an A4 PDF with headless Chromium. Links stay clickable. Needs `playwright` and Chromium."""
    from playwright.sync_api import sync_playwright
    out = Path(out_path)
    tmp = out.with_suffix(".print.html")
    tmp.write_text(html, encoding="utf-8")
    try:
        with sync_playwright() as p:
            b = p.chromium.launch()
            pg = b.new_page()
            pg.goto(tmp.resolve().as_uri())
            pg.wait_for_timeout(300)
            pg.pdf(path=str(out), format="A4", print_background=True, margin={"top": "10mm", "bottom": "10mm", "left": "8mm", "right": "8mm"})
            b.close()
    finally:
        tmp.unlink(missing_ok=True)
    return out
