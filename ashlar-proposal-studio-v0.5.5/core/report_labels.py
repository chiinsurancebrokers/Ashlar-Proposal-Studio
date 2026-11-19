"""The words every Ashlar client report uses, in both languages.

One dictionary, read by the PDF, the HTML and anything added later. When the
renderers each kept their own copy, a label corrected in one of them stayed
wrong in the other, and a client could be sent two documents about the same
case that disagreed on what a section was called.
"""
from __future__ import annotations


def is_greek(language: str) -> bool:
    key = str(language).lower()
    return key.startswith(("gr", "el")) or "greek" in key


def labels(language: str) -> dict:
    greek = is_greek(language)
    if greek:
        return {
            "subtitle": "Ανεξάρτητη συγκριτική ανάλυση και αιτιολογημένη συμβουλευτική άποψη",
            "footer": "Ανεξάρτητη συγκριτική ανάλυση", "context": "Πλαίσιο πελάτη", "profile": "Προφίλ / πλαίσιο",
            "exec": "Συνοπτική εικόνα", "strengths": "Πλεονεκτήματα", "consider": "Σημεία προσοχής",
            "compare": "Συγκριτικός πίνακας", "compare_note": "Ο πίνακας παρουσιάζει συνοπτικά τους όρους που εξήχθησαν από τα διαθέσιμα έγγραφα. Τα συμβατικά έγγραφα παραμένουν δεσμευτικά.",
            "benefit": "Κάλυψη / όρος", "diff": "Κύριες διαφορές", "assessment": "Πρόταση Ashlar", "our_view": "Η πρότασή μας",
            "preferred": "Προτεινόμενη επιλογή", "alternative": "Ισχυρή εναλλακτική", "extras": "Επιλογή με ευρύτερα πρόσθετα", "budget": "Οικονομικότερη επιλογή", "important_next": "Σημαντικές επισημάνσεις & επόμενα βήματα",
            "important": "Σημαντικές επισημάνσεις", "next": "Επόμενα βήματα", "notice": "Σημαντική σημείωση",
            "sources": "Επίσημα έγγραφα ασφαλιστικών εταιρειών", "sources_note": "Τα παρακάτω brochures / Tables of Benefits είναι τα έγγραφα των ασφαλιστικών εταιρειών που συνοδεύουν την ανάλυση. Οι προσωρινοί σύνδεσμοι ενδέχεται να λήξουν.", "open_doc": "Άνοιγμα εγγράφου",
        }
    return {
        "subtitle": "Independent plan comparison and reasoned advisory view", "footer": "Independent comparative analysis",
        "context": "Client context", "profile": "Profile / context", "exec": "Executive summary", "strengths": "Strengths",
        "consider": "Points to consider", "compare": "Side-by-side comparison", "compare_note": "The table below presents the extracted plan terms side by side. Long policy clauses are intentionally condensed for readability; governing documents remain controlling.",
        "benefit": "Benefit / term", "diff": "Key differences", "assessment": "Ashlar Recommendation", "our_view": "Our recommendation",
        "preferred": "Recommended option", "alternative": "Strong alternative", "extras": "Broader extras option", "budget": "Budget option", "important_next": "Important considerations & next steps",
        "important": "Important considerations", "next": "Next steps", "notice": "Important notice",
        "sources": "Official provider documents", "sources_note": "The brochures / Tables of Benefits below are the insurer documents supplied with this analysis. Temporary web links may expire.", "open_doc": "Open document",
    }



_EXTRA_EN = {
    "scope_warning": "Before you compare the premiums",
    "marks_key": "How to read the marks",
    "mark_covered": "Covered",
    "mark_action": "Action needed first",
    "mark_sub_limit": "Covered with a limit",
    "mark_not_covered": "Not covered",
    "mark_unknown": "Not specified in the documents supplied",
    "broker_review": "A licensed Ashlar broker reviews every recommendation before anything is placed.",
    "prepared_for": "Prepared for",
    "prepared_on": "Prepared on",
    "f_premium": "Premium",
    "f_limit": "Annual limit",
    "f_deductible": "Deductible / excess",
    "f_area": "Area of cover",
    "plans_compared": "Plans compared",
    "cost_title": "What a year costs if you claim",
    "cost_intro": "This adds each plan's deductible to its yearly premium for a year in which one insured person has one in-patient claim. It shows what the family pays itself before the insurer pays, on top of the premium. The dark bar is the premium; the light bar is the deductible.",
    "cost_col_plan": "Plan",
    "cost_col_premium": "Premium for a year",
    "cost_col_deductible": "Deductible",
    "cost_col_total": "Total in a year with one claim",
    "cost_col_note": "Worth knowing",
    "cost_outpatient": "Plus a separate out-patient deductible of {x} if out-patient care is also claimed ({t} in total).",
    "cost_family": "If several members claim: {t} (at most {n} deductibles per family).",
    "cost_unknown": "No total shown: the deductible is not stated as one amount in the premium's currency.",
    "cost_rank_changed": "On premium alone, {a} is the lowest. Once the deductible is added, {b} is the lowest ({t}).",
    "cost_rank_same": "{b} is the lowest both on premium alone and once the deductible is added ({t}).",
    "cost_caveat": "Totals are a full year's premium plus one deductible. They leave out amounts above a plan's limits, treatment that is not covered, co-insurance and later changes in premium. Where a quote does not say whether the deductible applies per person or per family, one deductible is assumed; confirm this with the insurer before deciding.",
    # Carried over from the inline copy this module replaced, so the shared
    # dictionary is not missing keys the PDF already renders.
    "members": "Insured members",
    "member_cols": ("Name", "Relationship", "Date of birth", "Age", "Nationality"),
    "doc_types": {"brochure": "Brochure", "tob": "Table of Benefits", "wording": "Policy wording",
                  "underwriting": "Underwriting guide", "supporting": "Supporting document"},
}

_EXTRA_EL = {
    "scope_warning": "Πριν συγκρίνετε τα ασφάλιστρα",
    "marks_key": "Πώς διαβάζονται οι ενδείξεις",
    "mark_covered": "Καλύπτεται",
    "mark_action": "Απαιτείται ενέργεια πρώτα",
    "mark_sub_limit": "Καλύπτεται με όριο",
    "mark_not_covered": "Δεν καλύπτεται",
    "mark_unknown": "Δεν προσδιορίζεται στα έγγραφα που δόθηκαν",
    "broker_review": "Κάθε πρόταση ελέγχεται από αδειοδοτημένο ασφαλιστικό διαμεσολαβητή πριν την τοποθέτηση.",
    "prepared_for": "Για",
    "prepared_on": "Ημερομηνία",
    "f_premium": "Ασφάλιστρο",
    "f_limit": "Ετήσιο όριο κάλυψης",
    "f_deductible": "Απαλλαγή",
    "f_area": "Γεωγραφική κάλυψη",
    "plans_compared": "Προγράμματα",
    "cost_title": "Πόσο κοστίζει ένα έτος με αποζημίωση",
    "cost_intro": "Προστίθεται η απαλλαγή κάθε προγράμματος στο ετήσιο ασφάλιστρο, για ένα έτος στο οποίο ένα ασφαλισμένο μέλος έχει μία νοσοκομειακή αποζημίωση. Δείχνει τι πληρώνει η ίδια η οικογένεια πριν πληρώσει ο ασφαλιστής, επιπλέον του ασφαλίστρου. Η σκούρα γραμμή είναι το ασφάλιστρο, η ανοιχτή η απαλλαγή.",
    "cost_col_plan": "Πρόγραμμα",
    "cost_col_premium": "Ασφάλιστρο έτους",
    "cost_col_deductible": "Απαλλαγή",
    "cost_col_total": "Σύνολο έτους με μία αποζημίωση",
    "cost_col_note": "Καλό είναι να γνωρίζετε",
    "cost_outpatient": "Επιπλέον χωριστή απαλλαγή εξωνοσοκομειακών {x}, αν διεκδικηθούν και εξωνοσοκομειακά (σύνολο {t}).",
    "cost_family": "Αν αποζημιωθούν περισσότερα μέλη: {t} (έως {n} απαλλαγές ανά οικογένεια).",
    "cost_unknown": "Δεν εμφανίζεται σύνολο: η απαλλαγή δεν αναφέρεται ως ένα ποσό στο νόμισμα του ασφαλίστρου.",
    "cost_rank_changed": "Μόνο με βάση το ασφάλιστρο, χαμηλότερο είναι το {a}. Μετά την προσθήκη της απαλλαγής, χαμηλότερο είναι το {b} ({t}).",
    "cost_rank_same": "Το {b} είναι το χαμηλότερο, τόσο στο ασφάλιστρο όσο και μετά την προσθήκη της απαλλαγής ({t}).",
    "cost_caveat": "Τα σύνολα είναι το ασφάλιστρο ενός πλήρους έτους συν μία απαλλαγή. Δεν περιλαμβάνουν ποσά πάνω από τα όρια του προγράμματος, θεραπείες που δεν καλύπτονται, συμμετοχή στο κόστος ή μεταγενέστερες αλλαγές ασφαλίστρου. Όπου η προσφορά δεν διευκρινίζει αν η απαλλαγή ισχύει ανά άτομο ή ανά οικογένεια, θεωρείται μία απαλλαγή· επιβεβαιώστε το με την ασφαλιστική πριν αποφασίσετε.",
    "members": "Ασφαλιζόμενα μέλη",
    "member_cols": ("Όνομα", "Σχέση", "Ημ. γέννησης", "Ηλικία", "Υπηκοότητα"),
    "doc_types": {"brochure": "Φυλλάδιο", "tob": "Πίνακας παροχών", "wording": "Όροι ασφάλισης",
                  "underwriting": "Οδηγός ανάληψης κινδύνου", "supporting": "Συνοδευτικό έγγραφο"},
}


def _with_extras(language: str) -> dict:
    out = labels(language)
    out.update(_EXTRA_EL if is_greek(language) else _EXTRA_EN)
    return out


all_labels = _with_extras


# The comparison matrix is built in one language -- it is structured data, not
# prose -- so the renderers translate its category bands at the point of
# display. A Greek client report should not have English band labels running
# down the middle of its only table.
_CATEGORY_EL = {
    "financial": "Οικονομικά στοιχεία",
    "core": "Βασικοί όροι",
    "underwriting": "Ανάληψη κινδύνου",
    "benefits": "Παροχές",
}


def category_label(category: str, language: str) -> str:
    """The band label for a comparison category, in the report's language."""
    text = str(category or "").strip()
    if not text or not is_greek(language):
        return text
    return _CATEGORY_EL.get(text.casefold(), text)


# The row labels of the comparison matrix, for the same reason as the bands:
# the matrix is built once, in English, and translated where it is displayed.
# The VALUES in those rows are not translated -- they are what the insurer's
# own document says, and a translated benefit term is no longer a quotation.
_TOPIC_EL = {
    "premium": "Ασφάλιστρο",
    "annual policy limit": "Ετήσιο όριο κάλυψης",
    "deductible / excess": "Απαλλαγή",
    "area of cover": "Γεωγραφική κάλυψη",
    "underwriting basis": "Βάση ανάληψης κινδύνου",
    "pre-existing conditions": "Προϋπάρχουσες παθήσεις",
    "in-patient treatment": "Νοσοκομειακά",
    "out-patient treatment": "Εξωνοσοκομειακά",
    "cancer / oncology": "Ογκολογικά",
    "chronic conditions": "Χρόνιες παθήσεις",
    "mental health": "Ψυχική υγεία",
    "maternity": "Μητρότητα",
    "dental": "Οδοντιατρικά",
    "optical": "Οφθαλμολογικά",
    "diagnostics / advanced imaging": "Διαγνωστικές εξετάσεις",
    "preventive / wellness": "Προληπτικός έλεγχος",
    "evacuation / repatriation": "Διακομιδή / επαναπατρισμός",
}


def topic_label(topic: str, language: str) -> str:
    """The comparison row's label, in the report's language."""
    text = str(topic or "").strip()
    if not text or not is_greek(language):
        return text
    return _TOPIC_EL.get(text.casefold(), text)
