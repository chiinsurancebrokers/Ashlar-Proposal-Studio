"""Greek travel-insurance proposal (έντυπο ταξιδιωτικής προσφοράς) in the Ashlar visual system.

Facts come from the quotation (TravelQuote); nothing is added that the insurer's documents do not say.
    from core.travel_proposal import ARUBA_DEMO, render_html, render_pdf
    render_pdf(render_html(ARUBA_DEMO, embed_fonts=True), "prosfora.pdf")
"""
from __future__ import annotations

import base64
import html as _html
from dataclasses import dataclass, field
from pathlib import Path

PAPER, FINE, MORTAR, INK, OX, VER, AMB = "#F2EDE4", "#F9F6EE", "#D7CDBC", "#1B2432", "#70181C", "#4A6E6B", "#B88A2B"
# Fraunces and Instrument Sans have no Greek glyphs, so the Greek edition uses Noto Serif, Inter and JetBrains Mono.
SERIF = "'Noto Serif',Georgia,'Times New Roman',serif"
SANS = "Inter,'Helvetica Neue',Arial,sans-serif"
MONO = "'JetBrains Mono','Courier New',monospace"
B = f"border:1px solid {MORTAR};"
E = _html.escape
FONT_DIR = Path(__file__).parent / "fonts" / "el"
GF = ("https://fonts.googleapis.com/css2?family=Noto+Serif:ital@0;1&family=Inter:wght@400;600"
      "&family=JetBrains+Mono&subset=greek&display=swap")


@dataclass
class TravelQuote:
    destination: str
    dates: str
    trip_type: str
    travellers: str
    plan: str
    price: str
    excess: str
    quote_no: str
    insurer: str
    benefits: list[tuple[str, list[tuple[str, str]]]]
    retrieve_dob: str = ""
    demo: bool = False
    assistance: dict = field(default_factory=dict)
    links: list[tuple[str, str, str]] = field(default_factory=list)  # label, note, url (url may be empty)
    addressee: str = ""      # e.g. "κυρία Γουμένου"; when set the document opens with a greeting
    prepared_for: str = ""   # full name shown in the header
    replies: list[tuple[str, str]] = field(default_factory=list)  # (her question, our answer)


def _grp(title: str, rows: list[tuple[str, str]]):
    return (title, rows)


ARUBA_DEMO = TravelQuote(
    destination="Αρούμπα", dates="Ταξίδι 6 ημερών. Οι ημερομηνίες θα οριστικοποιηθούν (δοκιμαστική προσφορά)",
    trip_type="Μεμονωμένο ταξίδι, 6 ημέρες",
    travellers="2 άτομα: η Zenovia και ο σύζυγός της Dimitris. Για την προσφορά χρησιμοποιήθηκαν οι ημερομηνίες γέννησης "
               "Zenovia 14/12/1990 και Dimitris 07/02/1990.",
    plan="Platinum", price="€73,74", excess="€100", quote_no="164521",
    insurer="SI International, μέλος του Sompo Holdings. Το Sompo Holdings έχει αξιολόγηση A+ σύμφωνα με τα στοιχεία που δημοσιεύει το ίδιο.",
    retrieve_dob="14/12/1990", demo=True,
    assistance={"name": "Cega Medical Assistance Team", "tel": "+44 (0) 1243 975 332", "email": "Assistance@cegagroup.com"},
    benefits=[
        _grp("Ακύρωση και διαταραχές ταξιδιού", [
            ("Ακύρωση ή διακοπή ταξιδιού", "€10.000"), ("Διαταραχή ταξιδιού", "€1.000"), ("Εναλλακτικό κατάλυμα", "€1.000"),
            ("Απώλεια αναχώρησης και εκτροπή μεταφορικού μέσου", "€750"), ("Επίδομα ταλαιπωρίας λόγω καθυστέρησης ταξιδιού", "€300"),
            ("Αλλαγή δρομολογίου", "€750")]),
        _grp("Ιατρική κάλυψη", [
            ("Έκτακτα ιατρικά έξοδα και επαναπατρισμός", "€10.000.000"), ("Έξοδα ταλαιπωρίας λόγω νοσηλείας", "€900"),
            ("Έξοδα κηδείας", "€5.000"), ("Φύλαξη κατοικίδιου (πρόσθετη διαμονή σε κέντρο φιλοξενίας)", "€500")]),
        _grp("Προσωπικό ατύχημα", [
            ("Προσωπικό ατύχημα", "€50.000"), ("Θάνατος από ατύχημα", "€50.000"), ("Απώλεια ενός άκρου ή ενός οφθαλμού", "€50.000"),
            ("Απώλεια δύο άκρων ή και των δύο οφθαλμών, ή ενός άκρου και ενός οφθαλμού", "€50.000"), ("Μόνιμη ολική ανικανότητα", "€50.000")]),
        _grp("Αποσκευές, χρήματα και έγγραφα", [
            ("Αποσκευές και προσωπικά αντικείμενα", "€7.500"), ("Όριο ανά αντικείμενο", "€450"), ("Όριο για αντικείμενα αξίας", "€450"),
            ("Καθυστέρηση αποσκευών", "€450"), ("Χρήματα και έγγραφα", "€900"), ("Όριο μετρητών", "€450"),
            ("Δόλια χρήση χαμένης πιστωτικής ή χρεωστικής κάρτας", "€450")]),
        _grp("Ευθύνη και νομικά", [
            ("Νομικά έξοδα", "€25.000"), ("Αστική ευθύνη", "€2.000.000"), ("Αεροπειρατεία και απαγωγή", "€2.000")]),
    ],
    links=[("Ανάκτηση προσφοράς", "Στη σελίδα της Europesure", "https://quote.europesuretravelinsurance.com/RetrieveQuote"),
           ("Ταξιδιωτική ασφάλιση στο Ashlar", "Επίπεδα κάλυψης", "https://ashlarassurance.com/travel-insurance/#levels"),
           ("Αξιολόγηση του ασφαλιστή", "Sompo Holdings, στα Αγγλικά", "https://www.sompo.com/about-us/financial-highlights-and-ratings")],
)


# ---- building blocks -----------------------------------------------------------------------------------------
def _eyebrow(t, color=INK):
    return (f'<div style="font-family:{MONO};font-size:10px;letter-spacing:.14em;text-transform:uppercase;color:{color};margin:0 0 8px;break-after:avoid">{E(t)}</div>')


def _h2(t, color=INK):
    return f'<div style="font-family:{SERIF};font-size:22px;line-height:1.25;font-weight:400;color:{color};margin:0 0 12px;break-after:avoid">{t}</div>'


def _p(t, color=INK, size=14, m="0 0 10px"):
    return f'<p style="font-family:{SANS};font-size:{size}px;line-height:1.65;color:{color};margin:{m}">{t}</p>'


def _a(t, u):
    return f'<a href="{u}" style="color:{INK};text-decoration:underline">{t}</a>'


def _block(inner, bg=FINE, pad="22px 28px"):
    return f'<div style="{B}background:{bg};padding:{pad};margin-top:-1px">{inner}</div>'


def _table(rows, w=170):
    r = "".join(f'<tr><td valign="top" width="{w}" style="{B}background:{PAPER};padding:11px 14px;font-family:{MONO};font-size:10px;'
                f'letter-spacing:.12em;text-transform:uppercase;color:{INK}">{k}</td><td valign="top" style="{B}background:{FINE};padding:11px 16px;'
                f'font-family:{SANS};font-size:14px;line-height:1.55;color:{INK}">{v}</td></tr>' for k, v in rows)
    return f'<table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%" style="border-collapse:collapse">{r}</table>'


def _benefit_table(rows):
    r = "".join(f'<tr><td style="{B}background:{FINE};padding:9px 14px;font-family:{SANS};font-size:13.5px;line-height:1.5;color:{INK}">{E(a)}</td>'
                f'<td width="120" align="right" style="{B}background:{FINE};padding:9px 14px;font-family:{MONO};font-size:12.5px;color:{INK};white-space:nowrap">{E(b)}</td></tr>'
                for a, b in rows)
    return f'<table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%" style="border-collapse:collapse;margin:0 0 16px">{r}</table>'


def _ul(items, color=INK):
    m = VER if color == INK else "#9db5b2"
    r = "".join(f'<tr><td valign="top" style="font-family:{MONO};font-size:12px;color:{m};padding:3px 10px 3px 0;width:18px">&mdash;</td>'
                f'<td style="font-family:{SANS};font-size:14px;line-height:1.6;color:{color};padding:3px 0">{i}</td></tr>' for i in items)
    return f'<table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%">{r}</table>'


def _badge(label, dot):
    return (f'<span style="display:inline-block;{B}padding:2px 8px;font-family:{MONO};font-size:10px;letter-spacing:.1em;text-transform:uppercase;'
            f'color:{INK};background:{FINE}"><span style="color:{dot}">&#9679;</span>&nbsp;{E(label)}</span>')


def embedded_fonts_css() -> str:
    faces = [("Noto Serif", "normal", 400, "noto-serif-%s-400-normal"), ("Noto Serif", "italic", 400, "noto-serif-%s-400-italic"),
             ("Noto Serif", "normal", 600, "noto-serif-%s-600-normal"), ("Inter", "normal", 400, "inter-%s-400-normal"),
             ("Inter", "normal", 600, "inter-%s-600-normal"), ("JetBrains Mono", "normal", 400, "jetbrains-mono-%s-400-normal")]
    ranges = {"latin": "U+0000-00FF,U+0131,U+0152-0153,U+02BB-02BC,U+02C6,U+02DA,U+02DC,U+2000-206F,U+20AC,U+2122,U+2191,U+2193,U+2212,U+2215,U+FEFF,U+FFFD",
              "greek": "U+0370-03FF"}
    css = []
    for fam, style, wt, pat in faces:
        for sub in ("latin", "greek"):
            fp = FONT_DIR / (pat % sub + ".woff2")
            if fp.exists():
                b64 = base64.b64encode(fp.read_bytes()).decode()
                css.append(f"@font-face{{font-family:'{fam}';font-style:{style};font-weight:{wt};unicode-range:{ranges[sub]};"
                           f"src:url(data:font/woff2;base64,{b64}) format('woff2')}}")
    return "".join(css)


def email_subject(q: TravelQuote) -> str:
    return f"Ταξιδιωτική ασφάλιση {q.destination}: προσφορά {q.plan}"


# ---- the document --------------------------------------------------------------------------------------------
def render_html(q: TravelQuote, embed_fonts: bool = False) -> str:
    ox = f'<i style="color:{OX}">προσφορά</i>'
    head = (f'<div style="background:{INK};border:1px solid {INK};padding:18px 28px"><span style="font-family:{MONO};font-size:11px;'
            f'letter-spacing:.2em;text-transform:uppercase;color:{FINE}">Ashlar Assurance</span>'
            f'<span style="font-family:{MONO};font-size:10px;letter-spacing:.14em;text-transform:uppercase;color:#9db5b2;float:right">{E(q.prepared_for) if q.prepared_for else "ashlarassurance.com"}</span></div>')
    hero = (_eyebrow("Ταξιδιωτική ασφάλιση" + (" · Δοκιμαστική προσφορά" if q.demo else ""))
            + f'<div style="font-family:{SERIF};font-size:34px;line-height:1.15;font-weight:400;letter-spacing:-.01em;color:{INK};margin:0 0 18px">'
              f'Ταξιδιωτική {ox} για {E(q.destination)}</div>'
            + _table([("Προορισμός", E(q.destination)), ("Ημερομηνίες", E(q.dates)), ("Τύπος ταξιδιού", E(q.trip_type)),
                      ("Ασφαλιζόμενοι", E(q.travellers))]))
    personal = ""
    if q.replies:
        ans = "".join(f'<div style="font-family:{MONO};font-size:10px;letter-spacing:.12em;text-transform:uppercase;color:{INK};margin:14px 0 6px;break-after:avoid">{E(k)}</div>'
                      + _p(v, m="0") for k, v in q.replies)
        personal = (_eyebrow("Απαντήσεις στο email σας") + _h2("Οι ερωτήσεις σας")
                    + _p(f"Αγαπητή {E(q.addressee)}, σας ευχαριστούμε για το μήνυμά σας. Παρακάτω θα βρείτε απαντήσεις σε όσα μας ρωτήσατε.", m="0 0 4px") + ans)
    price = (_eyebrow(f"Πρόγραμμα {q.plan} · {q.trip_type}") + _h2("Η προσφορά σας")
             + _table([("Συνολικό ασφάλιστρο", f"<b>{E(q.price)}</b> για 2 άτομα"), ("Απαλλαγή", f"{E(q.excess)} ανά αίτημα"),
                       ("Αριθμός προσφοράς", f'<span style="font-family:{MONO}">{E(q.quote_no)}</span>' + (" (δοκιμαστικός)" if q.demo else "")),
                       ("Ασφαλιστική εταιρία", E(q.insurer))])
             + '<div style="height:12px"></div>'
             + _p(f"Πρόκειται για προσφορά ταξιδιωτικής ασφάλισης για το ταξίδι στην {E(q.destination)}. Το πρόγραμμα {E(q.plan)} είναι το "
                  "υψηλότερο επίπεδο κάλυψης που διατίθεται σε αυτή την προσφορά.", m="0"))
    bens = "".join(f'<div style="font-family:{MONO};font-size:10px;letter-spacing:.12em;text-transform:uppercase;color:{INK};margin:0 0 6px">{E(t)}</div>'
                   + _benefit_table(r) for t, r in q.benefits)
    benefits = (_eyebrow("Παροχές ανά ασφαλιζόμενο") + _h2("Τι καλύπτει το πρόγραμμα") + bens
                + _p("Ενδέχεται να διατίθενται προαιρετικές επεκτάσεις, όπως παράταση ταξιδιού, κάλυψη ηλεκτρονικών συσκευών και αθλητικών "
                     "δραστηριοτήτων, με την επιφύλαξη των όρων και της αποδοχής από την ασφαλιστική εταιρία.", m="0"))
    pre = (_eyebrow("Σημαντικό") + _h2("Προϋπάρχουσες παθήσεις")
           + _ul(["Η ταξιδιωτική ασφάλιση γενικά δεν καλύπτει προϋπάρχουσα πάθηση που είναι γνωστή κατά την έναρξη της κάλυψης, "
                  "εκτός αν το επιτρέπει ρητά το ασφαλιστήριο συμβόλαιο.",
                  "Σύμφωνα με το άρθρο 28 του ασφαλιστηρίου, ορισμένες προϋπάρχουσες παθήσεις μπορεί να καλύπτονται εφόσον ο ασφαλισμένος δεν έχει "
                  "λάβει τελική πρόγνωση και η πάθηση είτε περιλαμβάνεται στον κατάλογο αποδεκτών παθήσεων με τις αναφερόμενες προϋποθέσεις, "
                  "είτε είναι σταθερή και ελεγχόμενη τους τελευταίους 24 μήνες με φαρμακευτική αγωγή από ιατρό, χωρίς νοσηλεία ή παραπομπή "
                  "σε ειδικό λόγω επιδείνωσης.",
                  "Για αναπνευστικές παθήσεις (πνεύμονες και αναπνοή), καρδιακές παθήσεις, εγκεφαλικό, νόσο του Crohn, επιληψία ή καρκίνο, "
                  "η περίοδος σταθερότητας είναι 60 μήνες."])
           + _p("Η παρούσα περίληψη δεν αντικαθιστά το ασφαλιστήριο συμβόλαιο. Οι ταξιδιώτες πρέπει να διαβάσουν το πλήρες ασφαλιστήριο, "
                "το Ενημερωτικό Έγγραφο Ασφαλιστικού Προϊόντος (IPID) και τους Όρους Συνεργασίας πριν από την αγορά.", m="12px 0 0"))
    a = q.assistance
    med = (_eyebrow("Ιατρική βοήθεια") + _h2("Αν χρειαστείτε βοήθεια στο ταξίδι")
           + _p("Σε περίπτωση σοβαρής ασθένειας, σωματικής βλάβης ή εισαγωγής σε νοσοκομείο κατά τη διάρκεια του ταξιδιού, ο ασφαλισμένος πρέπει να "
                "επικοινωνήσει με την ομάδα βοήθειας που αναγράφεται στα έγγραφα του ασφαλιστηρίου όσο το δυνατόν συντομότερα και, όπου είναι εφικτό, "
                "πριν κάνει εναλλακτικές ταξιδιωτικές ή νοσοκομειακές ρυθμίσεις.")
           + _table([("Ομάδα βοήθειας", E(a.get("name", ""))), ("Τηλέφωνο (24 ώρες)", E(a.get("tel", ""))),
                     ("Email", _a(E(a.get("email", "")), "mailto:" + a.get("email", "")))])
           + '<div style="height:10px"></div>' + _p("Δηλώστε ότι έχετε ταξιδιωτικό ασφαλιστήριο Europesure και δώστε το όνομα του ασφαλισμένου.", m="0"))
    links = (_eyebrow("Πρόσβαση στην προσφορά και στα έγγραφα") + _h2("Σύνδεσμοι και αναφορές")
             + _ul([f"{_a(E(l), u)} ({E(n)})" for l, n, u in q.links if u]
                   + ["Ασφαλιστήριο συμβόλαιο, Ενημερωτικό Έγγραφο Ασφαλιστικού Προϊόντος (IPID) και Όροι Συνεργασίας: επισυνάπτονται στην προσφορά"])
             + '<div style="height:10px"></div>'
             + _table([("Αριθμός προσφοράς", E(q.quote_no))] + ([("Ημερομηνία γέννησης για την ανάκτηση", E(q.retrieve_dob))] if q.retrieve_dob else [])))
    steps = [("Ανοίξτε την προσφορά", f"Μπείτε στον σύνδεσμο ανάκτησης προσφοράς και πληκτρολογήστε τον αριθμό {E(q.quote_no)}"
              + (f". Ως ημερομηνία γέννησης χρησιμοποιήστε {E(q.retrieve_dob)} (της Zenovia)" if q.retrieve_dob else "") + ". Πατήστε «Purchase»."),
             ("Ελέγξτε την προσφορά", "Βεβαιωθείτε ότι ο προορισμός, η διάρκεια, ο αριθμός των ασφαλιζομένων, το επίπεδο προγράμματος και το συνολικό κόστος ταιριάζουν με την παρούσα προσφορά."),
             ("Επιβεβαιώστε τις δηλώσεις", "Τσεκάρετε τα πεδία των δηλώσεων μόνο αφού διαβάσετε και αποδεχθείτε τις διατυπώσεις. Αν κάποιος ταξιδιώτης έχει πρόβλημα υγείας "
              "ή δεν είναι βέβαιος για την ιατρική δήλωση, πρέπει να ελέγξει το ασφαλιστήριο πριν συνεχίσει."),
             ("Συμπληρώστε τα στοιχεία επικοινωνίας", "Πληκτρολογήστε προσεκτικά το email και τα στοιχεία σας. Όλα τα έγγραφα του ασφαλιστηρίου θα εκδοθούν ηλεκτρονικά στο email που θα δηλώσετε."),
             ("Διαβάστε τους όρους και τα έγγραφα", "Διαβάστε το ασφαλιστήριο, το IPID και τους Όρους Συνεργασίας. Συνεχίστε μόνο αν η κάλυψη ταιριάζει στο ταξίδι σας."),
             ("Πληρωμή", f"Συμπληρώστε τα στοιχεία κάρτας, επιβεβαιώστε ότι το συνολικό ασφάλιστρο είναι {E(q.price)}{' για αυτή τη δοκιμαστική προσφορά' if q.demo else ''} "
              "και ολοκληρώστε τυχόν έλεγχο ταυτότητας από την τράπεζά σας.")]
    rows = "".join(f'<tr><td valign="top" width="50" style="{B}background:{PAPER};padding:12px 14px;font-family:{MONO};font-size:11px;letter-spacing:.1em;color:{INK}">'
                   f'{["I","II","III","IV","V","VI"][i]}.</td><td style="{B}background:{FINE};padding:12px 16px;font-family:{SANS};font-size:14px;line-height:1.6;color:{INK}">'
                   f'<b>{t}</b><br>{d}</td></tr>' for i, (t, d) in enumerate(steps))
    guide = (_eyebrow("Οδηγός αγοράς") + _h2("Έξι βήματα για να αγοράσετε το ασφαλιστήριο")
             + f'<table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%" style="border-collapse:collapse">{rows}</table>'
             + '<div style="height:14px"></div>'
             + _p("<b>Μετά την πληρωμή.</b> Τα έγγραφα του ασφαλιστηρίου αποστέλλονται με email. Αν δεν τα βρείτε στα εισερχόμενα, ελέγξτε τα ανεπιθύμητα (Spam/Junk).", m="0 0 10px")
             + _p("<b>Χρειάζεστε βοήθεια;</b> Μπορούμε να σας βοηθήσουμε να επιλέξετε το σωστό επίπεδο προγράμματος, να εξετάσετε τις προαιρετικές επεκτάσεις "
                  "και να ελέγξουμε αν χρειάζεται νέα προσφορά με τα πραγματικά στοιχεία των ταξιδιωτών.", m="0"))
    cta = ('<div style="height:16px"></div><a href="mailto:c.iatropoulos@ashlarassurance.com?subject=Ταξιδιωτική%20ασφάλιση%20-%20ερώτηση" '
           f'style="display:inline-block;background:{INK};color:{FINE};border:1px solid {INK};padding:12px 20px;font-family:{SANS};font-size:14px;text-decoration:none">'
           f'Γράψτε μας για την προσφορά&nbsp;<span style="font-family:{MONO}">&rarr;</span></a>')
    foot = (f'<div style="{B}background:{PAPER};padding:18px 28px;margin-top:-1px;font-family:{SANS};font-size:12.5px;line-height:1.7;color:{INK}">'
            f'Ashlar Assurance · Κομνηνών 3, Αθήνα 15342 · {_a("ashlarassurance.com", "https://ashlarassurance.com")}<br>'
            "Η προσφορά βασίζεται στα έγγραφα της ασφαλιστικής εταιρίας. Το ασφαλιστήριο συμβόλαιο είναι η τελική πηγή, και η ασφαλιστική εταιρία "
            "επιβεβαιώνει τους τελικούς όρους και το ασφάλιστρο.</div>")
    body = (head + _block(hero, PAPER, "30px 28px") + (_block(personal) if personal else "") + _block(price) + _block(benefits) + _block(pre) + _block(med)
            + _block(links) + _block(guide + cta) + foot)
    fonts = f"<style>{embedded_fonts_css()}</style>" if embed_fonts else f'<link href="{GF}" rel="stylesheet">'
    return (f'<!doctype html><html lang="el"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<meta name="color-scheme" content="light"><title>{E(email_subject(q))}</title>{fonts}<style>table tr{{break-inside:avoid}}</style></head>'
            f'<body style="margin:0;padding:16px;background:{PAPER}"><div style="max-width:680px;margin:0 auto">{body}</div>'
            f'</body></html>')


def render_pdf(html: str, out_path) -> Path:
    from core.lead_email import render_pdf as _pdf
    return _pdf(html, out_path)


from dataclasses import replace as _replace

ZENOVIA = _replace(
    ARUBA_DEMO, demo=False, quote_no="165318", addressee="κυρία Γουμένου", prepared_for="Προσφορά για την κυρία Ζηνοβία Γουμένου",
    dates="Ταξίδι 6 ημερών. Οι ακριβείς ημερομηνίες επιβεβαιώνονται πριν από την αγορά (βλ. απαντήσεις παρακάτω)",
    replies=[
        ("Διάρκεια της ασφάλισης",
         "Σας προτείνουμε η κάλυψη να ξεκινά από την ημέρα που φεύγετε από την Ελλάδα, στις 12 Νοεμβρίου, και να διαρκεί μέχρι την επιστροφή σας, "
         "ώστε να περιλαμβάνει και τις ενδιάμεσες στάσεις και όχι μόνο τις ημέρες στην Αρούμπα. Η προσφορά είναι για 6 ημέρες, "
         "που αντιστοιχεί στο διάστημα 12 έως 17 Νοεμβρίου. Αν η επιστροφή σας στην Ελλάδα ολοκληρώνεται μετά τις 17 Νοεμβρίου, "
         "πείτε μας την ημερομηνία άφιξης και θα ζητήσουμε νέα προσφορά για τις σωστές ημέρες, επειδή το ασφάλιστρο αλλάζει με τη διάρκεια. "
         "Τον ακριβή ορισμό της έναρξης και της λήξης της κάλυψης τον δίνει το ασφαλιστήριο, και θα τον ελέγξουμε μαζί πριν από την αγορά."),
        ("Ενδιάμεσες στάσεις σε Γαλλία και Νέα Υόρκη",
         "Η προσφορά έχει εκδοθεί με προορισμό την Αρούμπα. Θα επιβεβαιώσουμε γραπτά με την ασφαλιστική ότι οι στάσεις σε Γαλλία και Νέα Υόρκη "
         "καλύπτονται ως μέρος του ίδιου ταξιδιού, και θα σας ενημερώσουμε πριν πληρώσετε."),
        ("Το quote δεν ανοίγει",
         f"Μπείτε στον σύνδεσμο «Ανάκτηση προσφοράς» παρακάτω, πληκτρολογήστε τον αριθμό 165318 και ως ημερομηνία γέννησης 14/12/1990. "
         "Αν δεν ανοίγει ούτε έτσι, γράψτε μας και θα σας στείλουμε τα στοιχεία της προσφοράς με άλλον τρόπο."),
        ("Πληρωμή",
         "Η πληρωμή γίνεται ηλεκτρονικά με κάρτα, μέσα από την προσφορά (βήμα VI του οδηγού παρακάτω), και ενδέχεται να ζητηθεί έλεγχος ταυτότητας από την τράπεζά σας. "
         "Δεν χρειάζεται να μας στείλετε αποδεικτικό πληρωμής για την έκδοση: τα έγγραφα του ασφαλιστηρίου αποστέλλονται ηλεκτρονικά στο email που θα δηλώσετε."),
        ("Προθεσμία και παραλαβή του ασφαλιστηρίου",
         "Η αγορά πρέπει να ολοκληρωθεί πριν από την αναχώρησή σας, στις 12 Νοεμβρίου. Το ασφαλιστήριο αποστέλλεται με email μετά την πληρωμή. "
         "Σας συνιστούμε να ολοκληρώσετε την αγορά νωρίτερα από την τελευταία εβδομάδα, ώστε να προλάβετε να ελέγξετε τα έγγραφα και, αν χρειαστεί, να τα διορθώσουμε."),
        ("Απαιτήσεις της Αρούμπα",
         "Η Αρούμπα ζητά ιατρική ασφάλιση με κάλυψη ιατρικών εξόδων τουλάχιστον 15.000 δολαρίων ΗΠΑ, που να περιλαμβάνει νοσοκομειακή περίθαλψη, "
         "επείγουσα ιατρική φροντίδα και επαναπατρισμό, ακόμη και σε περίπτωση θανάτου. Το πρόγραμμα Platinum προβλέπει για έκτακτα ιατρικά έξοδα και επαναπατρισμό "
         "όριο €10.000.000 ανά άτομο, πολύ πάνω από το ελάχιστο. Για τον επαναπατρισμό σε περίπτωση θανάτου θα ελέγξουμε τη σχετική διατύπωση του ασφαλιστηρίου και θα σας την επιβεβαιώσουμε γραπτά πριν από την αγορά."),
    ],
)
