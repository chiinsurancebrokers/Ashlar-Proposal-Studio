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
from core import plan_quality, waiting_periods
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
        "compare": "How the options compare for {name}",
        "legend": "✓ Covered · ▲ Covered with a limit · ○ Covered, approval needed first · ✕ Not covered · – Not shown in the quote",
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
        "compare": "Σύγκριση επιλογών για {name}",
        "legend": "✓ Καλύπτεται · ▲ Καλύπτεται με όριο · ○ Με προηγούμενη έγκριση · ✕ Δεν καλύπτεται · – Δεν φαίνεται στην προσφορά",
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
:root{--bg:#151C27;--panel:#1B2432;--head:#111824;--ink:#ECE6DB;--muted:#B4BBC7;--line:#3C4A60;--gold:#D4A849;--ok:#5CC49A;--warn:#E0B24F;--bad:#E88377;color-scheme:dark}
@media (prefers-color-scheme: light){:root:not([data-theme="dark"]){--bg:#F6F3EC;--panel:#FFFFFF;--head:#ECE6D8;--ink:#1B2432;--muted:#4C586A;--line:#CDC5B3;--gold:#8A6212;--ok:#1F7A5A;--warn:#8A6212;--bad:#A33A2E;color-scheme:light}}
:root[data-theme="light"]{--bg:#F6F3EC;--panel:#FFFFFF;--head:#ECE6D8;--ink:#1B2432;--muted:#4C586A;--line:#CDC5B3;--gold:#8A6212;--ok:#1F7A5A;--warn:#8A6212;--bad:#A33A2E;color-scheme:light}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.65 system-ui,-apple-system,"Segoe UI",sans-serif}
main{max-width:1100px;margin:auto;padding-left:max(16px,env(safe-area-inset-left,0px));padding-right:max(16px,env(safe-area-inset-right,0px))}
.page{padding-block:44px;border-bottom:1px solid var(--line);min-width:0}
h1,h2{font-family:Georgia,serif;font-weight:400;line-height:1.18;text-wrap:balance}h1{font-size:clamp(30px,5vw,48px);margin:12px 0 28px}h2{font-size:27px;margin:30px 0 14px}
.eyebrow{font:600 11px/1.5 ui-monospace,monospace;letter-spacing:.12em;color:var(--gold);text-transform:uppercase}
p{margin:0 0 18px;max-width:75ch}.note{font-size:13px;color:var(--muted);border-left:2px solid var(--gold);padding-left:15px}
.table-wrap{overflow-x:auto;margin:22px 0;max-width:100%}table{border-collapse:collapse;width:100%;background:var(--panel);font-size:14px}
th,td{border:1px solid var(--line);padding:14px;text-align:left;vertical-align:top}th{color:var(--gold);background:var(--head);font-size:12px}
td:first-child{font-weight:550}.num{font-variant-numeric:tabular-nums}.dim{color:var(--muted)}
h3{font-size:17px;margin:22px 0 6px}.checks{list-style:none;padding:0;margin:0 0 14px}.checks li{padding:3px 0}.mk{display:inline-block;width:1.5em;font-weight:700}.mk.ok{color:var(--ok)}.mk.warn{color:var(--warn)}.mk.bad{color:var(--bad)}.mk.act,.mk.dim{color:var(--muted)}.legend{font-size:13px;color:var(--muted)}.tag{display:inline-block;margin-left:6px;padding:1px 8px;border:1px solid var(--muted);border-radius:99px;font-size:12px;color:var(--muted);white-space:nowrap}.tag.good{border-color:var(--ok);color:var(--ok);font-weight:600}
footer{padding-block:24px;color:var(--muted);font-size:12px}
@media(max-width:650px){table{min-width:640px}.page{padding-block:32px}}
"""


_MERIT = {
    "en": {
        "title": "Best plan on cover quality", "tag_merit": "Our recommendation: best on cover",
        "tag_budget": "Best for your budget", "plan": "Plan", "score": "Cover score",
        "best_merit": "On cover alone, whatever it costs, the strongest plan is {name}.",
        "best_budget": "For the budget and needs you stated, the best fit is {name}.",
        "same": "These are the same plan.",
        "intro": "This ranking looks only at what each plan gives: the annual limit, the participation you pay, the waiting periods, where you are covered and how wide the hospital network is. Price is not part of it. A plan can be the best on cover and still not be the one that fits your budget.",
        "dims": {"limit": "Annual limit", "deductible": "Participation", "waiting": "Waiting periods",
                 "area": "Area covered", "network": "Hospital network", "exclusions": "Exclusions"},
        "scored": "Scored on: {dims}. Each counts equally. Limit, participation, waiting periods and area come from the offers and the policy wordings.",
        "left_out": "Not scored, because not rated for every plan: {dims}.",
        "col_combo": "Combination", "legend_title": "Marks",
    },
    "el": {
        "title": "Το καλύτερο πρόγραμμα βάσει παροχών", "tag_merit": "Η σύστασή μας: καλύτερο βάσει παροχών",
        "tag_budget": "Καλύτερο για τον προϋπολογισμό σας", "plan": "Πρόγραμμα", "score": "Βαθμός παροχών",
        "best_merit": "Με βάση μόνο τις παροχές, ανεξάρτητα από το κόστος, το ισχυρότερο πρόγραμμα είναι {name}.",
        "best_budget": "Για τον προϋπολογισμό και τις ανάγκες που δηλώσατε, η καλύτερη επιλογή είναι {name}.",
        "same": "Πρόκειται για το ίδιο πρόγραμμα.",
        "intro": "Η κατάταξη αυτή εξετάζει μόνο όσα προσφέρει κάθε πρόγραμμα: το ετήσιο όριο, τη συμμετοχή που πληρώνετε, τις περιόδους αναμονής, την περιοχή κάλυψης και το πλήθος των νοσοκομείων του δικτύου. Η τιμή δεν συμμετέχει. Ένα πρόγραμμα μπορεί να είναι το καλύτερο σε παροχές και να μην είναι αυτό που ταιριάζει στον προϋπολογισμό σας.",
        "dims": {"limit": "Ετήσιο όριο", "deductible": "Συμμετοχή", "waiting": "Αναμονές",
                 "area": "Περιοχή κάλυψης", "network": "Δίκτυο νοσοκομείων", "exclusions": "Εξαιρέσεις"},
        "scored": "Βαθμολογήθηκαν: {dims}. Κάθε κριτήριο μετράει εξίσου. Όριο, συμμετοχή, αναμονές και περιοχή προέρχονται από τις προσφορές και τα ασφαλιστήρια.",
        "left_out": "Δεν βαθμολογήθηκαν, γιατί δεν έχουν αξιολογηθεί για όλα τα προγράμματα: {dims}.",
        "col_combo": "Συνδυασμός", "legend_title": "Σήμανση",
    },
}


def _merit(outcome: Result, quality, lang: str):
    """Merit of every plan and of every combination. Returns (plans ranked, dims, best combination, scores)."""
    plans = {}
    for sel in outcome.ranked:
        for o in sel.offers:
            if o.plan_key in quality:
                plans[o.plan_key] = quality[o.plan_key]
    ranked, dims = plan_quality.rank(plans)
    by_key = {m.key: m.score for m in ranked}
    combo = {}
    for sel in outcome.ranked:
        keys = [o.plan_key for o in sel.offers for _ in o.persons]
        combo[id(sel)] = plan_quality.combination_merit(keys, by_key)
    scored = [x for x in outcome.ranked if combo[id(x)] is not None]
    best = max(scored, key=lambda x: (combo[id(x)], -float(x.total))) if scored else None
    return ranked, dims, best, combo


def _merit_html(outcome: Result, prof: dict, quality, lang: str, ranked, dims, best) -> str:
    m = _MERIT[lang]
    e = escape
    labels = {o.plan_key: o.label for sel in outcome.ranked for o in sel.offers}
    rows = []
    for item in ranked:
        cells = [e(labels[item.key])]
        for d in plan_quality.DIMENSIONS:
            v = item.parts.get(d)
            cells.append("—" if v is None else f"{v:.2f}".replace(".", "," if lang == "el" else "."))
        cells.append("<b>" + f"{item.score:.2f}".replace(".", "," if lang == "el" else ".") + "</b>")
        rows.append(cells)
    head = [m["plan"]] + [m["dims"][d] for d in plan_quality.DIMENSIONS] + [m["score"]]
    table = _table(head, rows, numeric=tuple(range(1, len(head))))
    top_plan = labels[ranked[0].key]
    budget_plan = outcome.winner.label if len(outcome.winner.offers) == 1 else _combo_label(outcome.winner, prof)
    same = best is not None and best is outcome.winner
    out = (f"<p>{e(m['intro'])}</p><p><b>{e(m['best_merit'].format(name=_combo_label(best, prof) if best else top_plan))}</b></p>"
           f"<p>{e(m['best_budget'].format(name=budget_plan))}" + (f" {e(m['same'])}" if same else "") + "</p>" + table)
    used = ", ".join(m["dims"][d] for d in dims)
    rating = {"en": " Hospital network and exclusions are the broker's rating.", "el": " Το δίκτυο νοσοκομείων και οι εξαιρέσεις είναι εκτίμηση του συμβούλου."}[lang] \
        if {"network", "exclusions"} & set(dims) else ""
    out += f'<p class="note">{e(m["scored"].format(dims=used) + rating)}</p>'
    left = [d for d in plan_quality.DIMENSIONS if d not in dims]
    if left:
        out += f'<p class="note">{e(m["left_out"].format(dims=", ".join(m["dims"][d] for d in left)))}</p>'
    return out


_BASE = {
    "en": {"col": "Against today's plan", "line": "Today's plan: {name}, {price} a year.", "same": "today's plan",
           "less": "{x} less", "more": "{x} more"},
    "el": {"col": "Διαφορά από το σημερινό", "line": "Σημερινό πρόγραμμα: {name}, {price} τον χρόνο.", "same": "το σημερινό πρόγραμμα",
           "less": "{x} λιγότερο", "more": "{x} περισσότερο"},
}


def _vs_baseline(total: Decimal, baseline, lang: str, s: dict) -> str:
    b = _BASE[lang]
    diff = (total - baseline[1]).quantize(Decimal("0.01"))
    if diff == 0:
        return b["same"]
    return (b["less"] if diff < 0 else b["more"]).format(x=_money(abs(diff), s))


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


def _combo_label(sel: Selection, prof: dict) -> str:
    """Plan names with the people they cover, never the internal person keys."""
    if len(sel.offers) == 1:
        return sel.offers[0].label
    return " + ".join(o.label + " (" + ", ".join(prof[x].name for x in o.persons) + ")" for o in sel.offers)


def _fit(value: float, s: dict) -> str:
    return f"{value:.2f}".replace(".", s["dec"])


def _compare_section(outcome: Result, prof: dict, lang: str, s: dict, top: int) -> str:
    """For each person with more than one option in play: the options side by side, with the
    quoted text beside each state so limits and participations can be compared."""
    e = escape
    options: dict[str, list] = {}
    for sel in outcome.ranked[:top]:
        for o in sel.offers:
            for person in o.persons:
                bucket = options.setdefault(person, [])
                if o.label not in [x.label for x in bucket]:
                    bucket.append(o)
    html = ""
    for person, offers in options.items():
        if len(offers) < 2:
            continue
        p = prof[person]
        rows = [[e(s["cost"])] + [_money(o.yearly, s) for o in offers]]
        for need in p.needs:
            cells = [e(_benefit(need.benefit, lang))]
            for o in offers:
                state = o.benefits.get(need.benefit, UNKNOWN)
                text = f"<b>{e(s[_STATE_KEY[state]])}</b>"
                detail = o.details.get(need.benefit)
                if detail:
                    text += f'<br><span class="dim">{e(detail)}</span>'
                cells.append(text)
            rows.append(cells)
        html += f"<h2>{e(s['compare'].format(name=p.name))}</h2>" + _table(
            [s["benefit"]] + [o.label for o in offers], rows)
    return html


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
                        riders: dict | None = None, extra_points: Sequence[str] = (),
                        quality: dict | None = None, baseline: tuple | None = None) -> str:
    """The study as one HTML page. ``outcome`` must have a winner."""
    if outcome.winner is None:
        raise ValueError("No winning combination to write up.")
    s = dict(_STRINGS[lang])
    if len(profiles) == 1:       # one person: the page is not about a family
        s["title"] = {"en": "Health cover for you", "el": "Ασφάλιση υγείας για εσάς"}[lang]
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
    total_label = s["total"] if len(profiles) > 1 else {"en": "Total", "el": "Σύνολο"}[lang]
    cost_rows.append([f"<b>{e(total_label)}</b>", f"<b>{_money(best.total, s)}</b>",
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
            if state == UNKNOWN and need is None:
                cells.append('<span class="dim">—</span>')      # this person does not need it: neutral dash
            elif state == UNKNOWN:
                cells.append(f'<span class="dim">{e(label)}</span>')
            else:
                text = f"<b>{e(label)}</b>"
                detail = offer.details.get(key)
                if detail:                      # the limits and participations as the quote states them
                    text += f'<br><span class="dim">{e(detail)}</span>'
                cells.append(text)
            if need is None:
                cells[-1] = f'<span class="dim">{cells[-1]}</span>' if state != UNKNOWN else cells[-1]
        benefit_rows.append(cells)
    heads = [s["benefit"]] + [f"{prof[person].name}: {offer.label}" for person, offer in columns]
    benefits = _table(heads, benefit_rows)

    merit_ranked, merit_dims, merit_best, _combo = _merit(outcome, quality, lang) if quality else ([], (), None, {})
    mm = _MERIT[lang]

    def _tags(x: Selection) -> str:
        t = ""
        if merit_best is not None and x is merit_best:
            t += f' <span class="tag good">{e(mm["tag_merit"])}</span>'
        if x is outcome.winner:
            t += f' <span class="tag">{e(mm["tag_budget"])}</span>'
        return t

    other_rows = [[e(_combo_label(x, prof)) + (_tags(x) if quality else ""), _money(x.total, s), _fit(x.fit, s)]
                  for x in outcome.ranked[:top]]
    if baseline:
        for row, x in zip(other_rows, outcome.ranked[:top]):
            row.append(_vs_baseline(x.total, baseline, lang, s))
        others = _table([s["combo"], s["cost"], s["fit"], _BASE[lang]["col"]], other_rows, numeric=(1, 2))
        others = f'<p>{e(_BASE[lang]["line"].format(name=baseline[0], price=_money(baseline[1], s)))}</p>' + others
    else:
        others = _table([s["combo"], s["cost"], s["fit"]], other_rows, numeric=(1, 2))

    conf = confirmations(outcome, profiles, lang) + list(extra_points)
    conf_html = ("<ul>" + "".join(f"<li>{e(c)}</li>" for c in conf) + "</ul>") if conf else f"<p>{e(s['none_confirm'])}</p>"
    waiting_html = ""
    shown: list[str] = []
    for offer in [o for sel in [best] + list(outcome.ranked[:top]) for o in sel.offers]:
        for key in waiting_periods.tables_for(offer.label, (riders or {}).get(offer.label, ())):
            if key in shown:
                continue
            shown.append(key)
            t = waiting_periods.TABLES[key]
            waiting_html += (f"<h2>{e(t['title'][lang])}</h2><p>{e(t['intro'][lang])}</p>"
                             + _table([s["condition"], s["covered_after"]],
                                      [[e(a), e(b)] for a, b in waiting_periods.rows(key, lang)]))
    today = _fmt_date(on or date.today(), lang)
    who = f"<b>{e(client_name)}</b> | " if client_name else ""

    compare_html = _compare_section(outcome, prof, lang, s, top)
    sections = [
        (s["title"], f"<p>{e(s['prepared'])} {who}{e(today)}</p><p>{e(s['intro'])}</p>"
                     f"<h2>{e(s['people'])}</h2>{covers}<h2>{e(s['chosen'])}</h2>{costs}"
                     f"<p>{_money(best.total, s)} {e(s['per_year'])}, {_money(best.total / 12, s)} {e(s['per_month'])}.</p>"
                     f"<h2>{e(s['why'])}</h2>{_reasons_html(best, prof, lang)}"),
        (s["benefits"], benefits + compare_html),
    ]
    if waiting_html:
        sections.append((s["waiting"], waiting_html))
    if merit_ranked:
        sections.append((mm["title"], _merit_html(outcome, prof, quality, lang, merit_ranked, merit_dims, merit_best)))
    sections.append((s["all"], others + f'<p class="note">{e(s["sorted"])}</p>'))
    sections.append((s["confirm"], conf_html + f'<p class="note">{e(s["fair1"])}</p><p class="note">{e(s["fair2"])}</p>'
                                              f'<p class="note">{e(s["fair3"])}</p>'))
    body = "".join(f'<section class="page"><div class="eyebrow">{e(s["eyebrow"])} / {i:02d}</div><h1>{e(h)}</h1>{b}</section>'
                   for i, (h, b) in enumerate(sections, 1))
    return (f'<!doctype html><html lang="{s["lang"]}"><head><meta charset="utf-8"><meta name="viewport" '
            f'content="width=device-width,initial-scale=1"><title>{e(s["title"])}</title><style>{CSS}</style></head>'
            f'<body><main>{body}<footer>Ashlar Assurance | {e(today)}</footer></main></body></html>')


_MARK = {COVERED: ("✓", "ok"), SUB_LIMIT: ("▲", "warn"), ACTION: ("○", "act"), NOT_COVERED: ("✕", "bad"),
         UNKNOWN: ("–", "dim")}


def _reasons_html(best: Selection, prof: dict, lang: str) -> str:
    """One block per person: the plan, then one ticked line per need. The text stays beside every
    mark, so the state never rests on the colour or the shape alone."""
    s = _STRINGS[lang]
    e = escape
    out = ""
    for offer in best.offers:
        for person in offer.persons:
            p = prof[person]
            items = ""
            for need in p.needs:
                state = offer.benefits.get(need.benefit, UNKNOWN)
                mark, cls = _MARK[state]
                tag = f" ({s['must']})" if need.weight == MUST else ""
                items += (f'<li><span class="mk {cls}" aria-hidden="true">{mark}</span>'
                          f"{e(_benefit(need.benefit, lang))}{e(tag)}: {e(s[_STATE_KEY[state]])}</li>")
            out += f"<h3>{e(p.name)}: {e(offer.label)}</h3><ul class=\"checks\">{items}</ul>"
    return out + f'<p class="legend">{e(s["legend"])}</p>'


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
