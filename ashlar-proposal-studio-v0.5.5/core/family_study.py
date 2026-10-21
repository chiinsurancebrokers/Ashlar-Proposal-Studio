"""The family study: the optimiser's answer as a client document, in Greek or English.

One self-contained HTML page in the Ashlar comparison layout: family and options, benefits, total
cost, confirmations. It shows states, not amounts. Amounts stay in the case report. Every price is a
figure the broker entered from an insurer quote. The study never says a plan "wins". It shows the
combination that fits best on the stated needs and why, and what must be confirmed first.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from html import escape
from typing import Sequence

from core.benefit_state import ACTION, COVERED, NOT_COVERED, SUB_LIMIT, UNKNOWN
from core.family_bridge import BENEFITS
from core import waiting_periods
from core.family_optimizer import MUST, Profile, Result, Selection

_STRINGS = {
    "en": {
        "lang": "en", "title": "Health cover for your family", "eyebrow": "ASHLAR ASSURANCE",
        "prepared": "Prepared for", "people": "Who is covered", "person": "Person", "lives": "Lives",
        "plan": "Plan", "cost": "Yearly cost", "month": "Per month",
        "chosen": "The combination that fits best", "why": "Why this combination",
        "benefits": "What each plan covers", "benefit": "Benefit",
        "all": "Other combinations compared", "combo": "Combination", "fit": "Fit to stated needs",
        "confirm": "Before you decide", "none_confirm": "No open points beyond the insurers' own underwriting.",
        "total": "Household total", "per_year": "a year", "per_month": "a month (yearly total divided by 12)",
        "intro": "We compared every way of covering your household and matched each person's needs to the plans quoted. The combination below fits the stated needs best for the price. The other combinations are shown so you can see what each choice trades off.",
        "sorted": "Sorted by fit to stated needs after a price adjustment. The first row is the combination described above.",
        "covered": "Covered", "sub_limit": "Covered with a limit", "action": "Covered, approval needed first",
        "not_covered": "Not covered", "unknown": "Not shown in the quote",
        "must": "must have",
        "conf_unknown": "The quote does not show {benefit} for {plan}. Ask the insurer, because the choice could change if it is covered.",
        "conf_decisive": "If {plan} covers {benefit}, a different combination ({winner}) would fit better.",
        "conf_must": "{benefit} is a must-have for you and the quote for {plan} does not show it.",
        "over": "Every combination is above the stated yearly budget.",
        "fair1": "A licensed Ashlar broker reviews every recommendation before anything is placed.",
        "fair2": "Prices come from the insurers' own quotes, never from an AI estimate. Benefit summaries are simplified from the insurers' documents; the policy wording prevails.",
        "fair3": "Not everyone needs international cover. If a local plan fits, we say so. The public health system remains an essential safety net. This is not an offer of cover. Final eligibility, terms and premium are confirmed by each insurer after underwriting, and nothing is assumed about pre-existing conditions until the insurer confirms in writing.",
        "waiting": "Waiting periods", "condition": "Condition", "covered_after": "Covered after",
        "nl": ".", "dec": ".", "thou": ",",
    },
    "el": {
        "lang": "el", "title": "Ασφάλιση υγείας για την οικογένειά σας", "eyebrow": "ASHLAR ASSURANCE",
        "prepared": "Προετοιμάστηκε για", "people": "Ποιοι ασφαλίζονται", "person": "Ασφαλισμένος",
        "lives": "Διαμονή", "plan": "Πρόγραμμα", "cost": "Ετήσιο κόστος", "month": "Ανά μήνα",
        "chosen": "Ο συνδυασμός που ταιριάζει καλύτερα", "why": "Γιατί αυτός ο συνδυασμός",
        "benefits": "Τι καλύπτει κάθε πρόγραμμα", "benefit": "Παροχή",
        "all": "Οι υπόλοιποι συνδυασμοί που συγκρίναμε", "combo": "Συνδυασμός",
        "fit": "Προσαρμογή στις ανάγκες", "confirm": "Πριν αποφασίσετε",
        "none_confirm": "Δεν υπάρχουν ανοιχτά θέματα πέρα από την ανάληψη κινδύνου από τις ίδιες τις ασφαλιστικές εταιρίες.",
        "total": "Σύνολο οικογένειας", "per_year": "τον χρόνο", "per_month": "τον μήνα (το ετήσιο σύνολο διά 12)",
        "intro": "Συγκρίναμε κάθε τρόπο να καλυφθεί η οικογένειά σας και ταιριάξαμε τις ανάγκες κάθε ασφαλισμένου με τα προγράμματα που τιμολογήθηκαν. Ο συνδυασμός παρακάτω ταιριάζει καλύτερα στις ανάγκες που δηλώσατε για την τιμή του. Οι υπόλοιποι συνδυασμοί εμφανίζονται ώστε να βλέπετε τι θυσιάζει κάθε επιλογή.",
        "sorted": "Σειρά με βάση την προσαρμογή στις ανάγκες μετά από διόρθωση για την τιμή. Η πρώτη γραμμή είναι ο συνδυασμός που περιγράφεται παραπάνω.",
        "covered": "Καλύπτεται", "sub_limit": "Καλύπτεται με όριο", "action": "Καλύπτεται, με προηγούμενη έγκριση",
        "not_covered": "Δεν καλύπτεται", "unknown": "Δεν φαίνεται στην προσφορά",
        "must": "απαραίτητη",
        "conf_unknown": "Η προσφορά δεν δείχνει την παροχή «{benefit}» για το {plan}. Ρωτήστε την ασφαλιστική εταιρία, γιατί η επιλογή μπορεί να αλλάξει αν καλύπτεται.",
        "conf_decisive": "Αν το {plan} καλύπτει «{benefit}», θα ταίριαζε καλύτερα άλλος συνδυασμός ({winner}).",
        "conf_must": "Η παροχή «{benefit}» είναι απαραίτητη για εσάς και η προσφορά για το {plan} δεν την δείχνει.",
        "over": "Κάθε συνδυασμός ξεπερνά τον ετήσιο προϋπολογισμό που δηλώσατε.",
        "fair1": "Κάθε πρόταση ελέγχεται από αδειοδοτημένο ασφαλιστικό διαμεσολαβητή της Ashlar πριν την τοποθέτηση.",
        "fair2": "Οι τιμές προέρχονται από τις προσφορές των ίδιων των ασφαλιστικών εταιριών και όχι από εκτίμηση της AI. Η περίληψη παροχών βασίζεται στα έγγραφα των ασφαλιστών. Το ασφαλιστήριο συμβόλαιο είναι η τελική πηγή.",
        "fair3": "Δεν χρειάζονται όλοι διεθνή κάλυψη. Αν ταιριάζει ένα τοπικό πρόγραμμα, θα το πούμε. Το δημόσιο σύστημα υγείας παραμένει απαραίτητο δίχτυ ασφαλείας. Πρόκειται για προκαταρκτική σύγκριση και όχι για προσφορά κάλυψης. Η τελική επιλεξιμότητα, οι όροι και το ασφάλιστρο επιβεβαιώνονται από κάθε ασφαλιστική εταιρία μετά την ανάληψη κινδύνου. Καμία προϋπάρχουσα πάθηση δεν θεωρείται δεδομένη μέχρι να το επιβεβαιώσει γραπτώς η ασφαλιστική εταιρία.",
        "waiting": "Περίοδοι αναμονής", "condition": "Πάθηση", "covered_after": "Καλύπτεται μετά",
        "nl": ".", "dec": ",", "thou": ".",
    },
}

_BENEFIT_EL = {
    "inpatient": "Νοσοκομειακά", "outpatient": "Εξωνοσοκομειακές επισκέψεις", "cancer": "Ογκολογική φροντίδα",
    "chronic_conditions": "Χρόνιες παθήσεις", "mental_health": "Ψυχική υγεία", "maternity": "Μητρότητα",
    "dental": "Οδοντιατρικά", "optical": "Οφθαλμολογικά",
    "diagnostics_imaging": "Διαγνωστικές εξετάσεις και απεικόνιση",
    "preventive": "Πρόληψη και check-up", "evacuation_repatriation": "Διακομιδή και επαναπατρισμός",
}
_STATE_KEY = {COVERED: "covered", SUB_LIMIT: "sub_limit", ACTION: "action", NOT_COVERED: "not_covered",
              UNKNOWN: "unknown"}

CSS = """
:root{--bg:#151C27;--panel:#1B2432;--head:#111824;--ink:#ECE6DB;--muted:#B4BBC7;--line:#3C4A60;--gold:#D4A849;color-scheme:dark}
@media (prefers-color-scheme: light){:root:not([data-theme="dark"]){--bg:#F6F3EC;--panel:#FFFFFF;--head:#ECE6D8;--ink:#1B2432;--muted:#4C586A;--line:#CDC5B3;--gold:#8A6212;color-scheme:light}}
:root[data-theme="light"]{--bg:#F6F3EC;--panel:#FFFFFF;--head:#ECE6D8;--ink:#1B2432;--muted:#4C586A;--line:#CDC5B3;--gold:#8A6212;color-scheme:light}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.65 system-ui,-apple-system,"Segoe UI",sans-serif}
main{max-width:1100px;margin:auto;padding-left:max(16px,env(safe-area-inset-left,0px));padding-right:max(16px,env(safe-area-inset-right,0px))}
.page{padding-block:44px;border-bottom:1px solid var(--line);min-width:0}
h1,h2{font-family:Georgia,serif;font-weight:400;line-height:1.18;text-wrap:balance}h1{font-size:clamp(30px,5vw,48px);margin:12px 0 28px}h2{font-size:27px;margin:30px 0 14px}
.eyebrow{font:600 11px/1.5 ui-monospace,monospace;letter-spacing:.12em;color:var(--gold);text-transform:uppercase}
p{margin:0 0 18px;max-width:75ch}.note{font-size:13px;color:var(--muted);border-left:2px solid var(--gold);padding-left:15px}
.table-wrap{overflow-x:auto;margin:22px 0;max-width:100%}table{border-collapse:collapse;width:100%;background:var(--panel);font-size:14px}
th,td{border:1px solid var(--line);padding:14px;text-align:left;vertical-align:top}th{color:var(--gold);background:var(--head);font-size:12px}
td:first-child{font-weight:550}.num{font-variant-numeric:tabular-nums}.dim{color:var(--muted)}
footer{padding-block:24px;color:var(--muted);font-size:12px}
@media(max-width:650px){table{min-width:640px}.page{padding-block:32px}}
"""


def _money(value: Decimal | float, s: dict) -> str:
    text = f"{Decimal(str(value)):,.2f}"          # 4,847.06
    if s["dec"] == ",":
        text = text.replace(",", "\0").replace(".", ",").replace("\0", ".")
    return "€" + text


def _benefit(key: str, lang: str) -> str:
    return _BENEFIT_EL.get(key, BENEFITS.get(key, key)) if lang == "el" else BENEFITS.get(key, key)


def _fmt_date(d: date, lang: str) -> str:
    return d.strftime("%d/%m/%Y") if lang == "el" else d.strftime("%d %B %Y")


def _table(head: Sequence[str], rows: Sequence[Sequence[str]], numeric: Sequence[int] = ()) -> str:
    th = "".join(f"<th>{escape(h)}</th>" for h in head)
    body = "".join("<tr>" + "".join(
        f'<td class="{"num" if i in numeric else ""}">{c}</td>' for i, c in enumerate(r)) + "</tr>" for r in rows)
    return f'<div class="table-wrap"><table><thead><tr>{th}</tr></thead><tbody>{body}</tbody></table></div>'


def confirmations(outcome: Result, profiles: Sequence[Profile], lang: str) -> list[str]:
    s = _STRINGS[lang]
    lines: list[str] = []
    best = outcome.winner
    if best is None:
        return lines
    for offer_label, benefit in best.unconfirmed_must:
        lines.append(s["conf_must"].format(benefit=_benefit(benefit, lang), plan=offer_label))
    decisive = {(f.plan_key, f.benefit) for f in outcome.flips}
    for f in outcome.flips:
        lines.append(s["conf_decisive"].format(plan=f.plan_key, benefit=_benefit(f.benefit, lang),
                                               winner=f.new_winner))
    seen = set(best.unconfirmed_must)
    for offer_label, benefit in best.unknown:
        if (offer_label, benefit) in seen or (offer_label, benefit) in decisive:
            continue
        lines.append(s["conf_unknown"].format(benefit=_benefit(benefit, lang), plan=offer_label))
    if best.over_budget:
        lines.append(s["over"])
    return lines


def render_family_study(outcome: Result, profiles: Sequence[Profile], *, lang: str = "en",
                        client_name: str = "", on: date | None = None, top: int = 6,
                        riders: dict | None = None) -> str:
    """The study as one HTML page. ``outcome`` must have a winner."""
    if outcome.winner is None:
        raise ValueError("No winning combination to write up.")
    s = _STRINGS[lang]
    best: Selection = outcome.winner
    prof = {p.person: p for p in profiles}
    e = escape

    people_rows = []
    for offer in best.offers:
        for person in offer.persons:
            p = prof[person]
            people_rows.append([e(p.name), e(p.residence), e(offer.label)])
    covers = _table([s["person"], s["lives"], s["plan"]], people_rows)

    cost_rows = [[e(o.label + (f" ({', '.join(prof[x].name for x in o.persons)})" if len(best.offers) > 1 else "")),
                  _money(o.yearly, s), _money(o.yearly / 12, s)] for o in best.offers]
    cost_rows.append([f"<b>{e(s['total'])}</b>", f"<b>{_money(best.total, s)}</b>",
                      f"<b>{_money(best.total / 12, s)}</b>"])
    costs = _table([s["plan"], s["cost"], s["month"]], cost_rows, numeric=(1, 2))

    # benefits: one row per benefit someone needs, one column per person's plan
    needed: list[str] = []
    for p in profiles:
        for n in p.needs:
            if n.benefit not in needed:
                needed.append(n.benefit)
    columns = [(person, offer) for offer in best.offers for person in offer.persons]
    benefit_rows = []
    for key in needed:
        cells = [e(_benefit(key, lang))]
        for person, offer in columns:
            state = offer.benefits.get(key, UNKNOWN)
            need = next((n for n in prof[person].needs if n.benefit == key), None)
            label = s[_STATE_KEY[state]]
            if state == UNKNOWN:
                cells.append(f'<span class="dim">{e(label)}</span>')
            else:
                cells.append(e(label))
            if need is None:
                cells[-1] = f'<span class="dim">{cells[-1]}</span>' if state != UNKNOWN else cells[-1]
        benefit_rows.append(cells)
    heads = [s["benefit"]] + [f"{prof[person].name}: {offer.label}" for person, offer in columns]
    benefits = _table(heads, benefit_rows)

    other_rows = [[e(x.label), _money(x.total, s), f"{x.fit:.2f}"] for x in outcome.ranked[:top]]
    others = _table([s["combo"], s["cost"], s["fit"]], other_rows, numeric=(1, 2))

    reasons = "".join(f"<li>{e(line)}</li>" for line in _reasons(best, prof, lang))
    conf = confirmations(outcome, profiles, lang)
    conf_html = ("<ul>" + "".join(f"<li>{e(c)}</li>" for c in conf) + "</ul>") if conf else f"<p>{e(s['none_confirm'])}</p>"
    waiting_html = ""
    shown: list[str] = []
    for offer in best.offers:
        for key in waiting_periods.tables_for(offer.label, (riders or {}).get(offer.label, ())):
            if key in shown:
                continue
            shown.append(key)
            t = waiting_periods.TABLES[key]
            waiting_html += (f"<h2>{e(t['title'][lang])}</h2><p>{e(t['intro'][lang])}</p>"
                             + _table([s["condition"], s["covered_after"]],
                                      [[e(a), e(b)] for a, b in waiting_periods.rows(key, lang)]))
    if waiting_html:
        waiting_html = (f'<section class="page"><div class="eyebrow">{e(s["eyebrow"])} / 03</div>'
                        f'<h1>{e(s["waiting"])}</h1>{waiting_html}</section>')
    today = _fmt_date(on or date.today(), lang)
    who = f"<b>{e(client_name)}</b> | " if client_name else ""

    return f"""<!doctype html><html lang="{s['lang']}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{e(s['title'])}</title><style>{CSS}</style></head><body><main>
<section class="page"><div class="eyebrow">{e(s['eyebrow'])} / 01</div><h1>{e(s['title'])}</h1>
<p>{e(s['prepared'])} {who}{e(today)}</p><p>{e(s['intro'])}</p>
<h2>{e(s['people'])}</h2>{covers}
<h2>{e(s['chosen'])}</h2>{costs}
<p>{_money(best.total, s)} {e(s['per_year'])}, {_money(best.total / 12, s)} {e(s['per_month'])}.</p>
<h2>{e(s['why'])}</h2><ul>{reasons}</ul></section>
<section class="page"><div class="eyebrow">{e(s['eyebrow'])} / 02</div><h1>{e(s['benefits'])}</h1>{benefits}</section>
{waiting_html}<section class="page"><div class="eyebrow">{e(s['eyebrow'])} / 04</div><h1>{e(s['all'])}</h1>{others}<p class="note">{e(s['sorted'])}</p></section>
<section class="page"><div class="eyebrow">{e(s['eyebrow'])} / 05</div><h1>{e(s['confirm'])}</h1>{conf_html}
<p class="note">{e(s['fair1'])}</p><p class="note">{e(s['fair2'])}</p><p class="note">{e(s['fair3'])}</p></section>
<footer>Ashlar Assurance | {e(today)}</footer></main></body></html>"""


def _reasons(best: Selection, prof: dict, lang: str) -> list[str]:
    s = _STRINGS[lang]
    lines = []
    for offer in best.offers:
        for person in offer.persons:
            p = prof[person]
            parts = []
            for need in p.needs:
                state = offer.benefits.get(need.benefit, UNKNOWN)
                tag = f" ({s['must']})" if need.weight == MUST else ""
                parts.append(f"{_benefit(need.benefit, lang)}{tag}: {s[_STATE_KEY[state]].lower()}")
            lines.append(f"{p.name}: {offer.label}. " + "; ".join(parts) + ("." if parts else ""))
    return lines


def mix_record(outcome: Result, profiles: Sequence[Profile], *, lang: str = "en", budget_cap=None) -> dict:
    """The chosen combination as plain data for the case record. Needs a winner."""
    best = outcome.winner
    if best is None:
        raise ValueError("No winning combination to record.")
    name = {p.person: p.name for p in profiles}
    return {
        "version": 1,
        "saved_at": date.today().isoformat(),
        "language": lang,
        "label": best.label,
        "total_yearly": str(best.total),
        "total_monthly": str((best.total / 12).quantize(Decimal("0.01"))),
        "budget_cap": str(budget_cap) if budget_cap else None,
        "offers": [{"plan": o.label, "yearly": str(o.yearly), "persons": [name.get(x, x) for x in o.persons]}
                   for o in best.offers],
        "robust": bool(outcome.robust),
        "to_confirm": [f"{b} ({o})" for o, b in best.unknown],
        "flips": [{"plan": f.plan_key, "benefit": f.benefit, "winner_if_covered": f.new_winner} for f in outcome.flips],
        "broker_reviewed": False,
    }
