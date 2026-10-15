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
