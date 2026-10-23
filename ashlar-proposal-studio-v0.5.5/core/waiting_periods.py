"""Generali waiting periods, taken from the policy wording. Each table is one wording document.

Hospital Premium Flexi: Article 5. Doctors & Exams Premium: Article 3. A table is shown only for a
plan it applies to. Nothing here is a price or an estimate.
"""
from __future__ import annotations

from typing import Iterable, Sequence

HOSPITAL = "hospital_premium_flexi"
DOCTORS = "doctors_exams_premium"
ON_DEMAND = "doctors_exams_on_demand"

TABLES = {
    HOSPITAL: {
        "title": {"en": "Generali Hospital Premium Flexi (Article 5)", "el": "Generali Hospital Premium Flexi (Άρθρο 5)"},
        "intro": {
            "en": "These conditions are covered only after the period shown. Cover applies only if the condition was not known to the insured at the start and was first diagnosed within that period.",
            "el": "Οι παρακάτω παθήσεις καλύπτονται μόνο μετά το διάστημα που αναγράφεται. Η κάλυψη ισχύει μόνο αν η πάθηση δεν ήταν γνωστή στην ασφαλισμένη κατά την έναρξη και διαγνώστηκε για πρώτη φορά μέσα σε αυτό το διάστημα.",
        },
        "rows": [
            ("Appendectomy", "Σκωληκοειδεκτομή", "The first three (3) months of the first insurance year", "Τους τρεις (3) πρώτους μήνες του πρώτου ασφαλιστικού έτους"),
            ("Nasal growths and tonsillectomy", "Εκβλαστήσεις της ρινικής κοιλότητας και αμυγδαλεκτομή", "The first insurance year", "Το πρώτο ασφαλιστικό έτος"),
            ("Bowel conditions, except malignancy and infectious gastrointestinal disease", "Παθήσεις εντέρων, εκτός από κακοήθεια και λοιμώδεις ασθένειες του γαστρεντερικού συστήματος", "The first two (2) consecutive insurance years", "Τα δύο (2) πρώτα συνεχόμενα ασφαλιστικά έτη"),
            ("Genital conditions, except malignancy", "Παθήσεις γεννητικών οργάνων, εκτός από κακοήθεια", "The first two (2) consecutive insurance years. The wait does not apply if a genital ultrasound and Pap test (women) or prostate ultrasound and PSA (men) were done with no abnormal findings in the year before the start", "Τα δύο (2) πρώτα συνεχόμενα ασφαλιστικά έτη. Η αναμονή δεν ισχύει αν έχουν γίνει, χωρίς παθολογικά ευρήματα και μέσα στο έτος πριν από την έναρξη, υπέρηχος γεννητικών οργάνων και test Παπανικολάου (για γυναίκες) ή υπέρηχος προστάτη και PSA (για άνδρες)"),
            ("Pregnancy complication, miscarriage or medically required termination", "Επιπλοκή εγκυμοσύνης, αποβολή ή διακοπή εγκυμοσύνης που επιβάλλεται για ιατρικούς λόγους", "The first two (2) consecutive insurance years", "Τα δύο (2) πρώτα συνεχόμενα ασφαλιστικά έτη"),
            ("Deviated nasal septum", "Σκολίωση ρινικού διαφράγματος", "The first three (3) consecutive insurance years", "Τα τρία (3) πρώτα συνεχόμενα ασφαλιστικά έτη"),
            ("Spinal conditions", "Παθήσεις σπονδυλικής στήλης", "The first three (3) consecutive insurance years. The wait does not apply to an injury proven medically and by imaging", "Τα τρία (3) πρώτα συνεχόμενα ασφαλιστικά έτη. Δεν ισχύει η αναμονή σε κάκωση που αποδεικνύεται ιατρικά και απεικονιστικά"),
            ("Treatment and surgical removal of moles and papillomas", "Θεραπεία και χειρουργική αφαίρεση σπίλων και θηλωμάτων", "The first three (3) consecutive insurance years", "Τα τρία (3) πρώτα συνεχόμενα ασφαλιστικά έτη"),
        ],
    },
    DOCTORS: {
        "title": {"en": "Generali Doctors & Exams Premium (Article 3)", "el": "Generali Γιατροί & Εξετάσεις Premium (Άρθρο 3)"},
        "intro": {
            "en": "These conditions are covered only after the first insurance year, and only if they were not known at the start and were first diagnosed within that period.",
            "el": "Οι παρακάτω παθήσεις καλύπτονται μόνο μετά την συμπλήρωση του πρώτου ασφαλιστικού έτους και μόνο αν δεν ήταν γνωστές κατά την έναρξη και διαγνώστηκαν για πρώτη φορά μέσα σε αυτό το διάστημα.",
        },
        "rows": [
            ("Spinal conditions and complications", "Παθήσεις σπονδυλικής στήλης και επιπλοκές", "After the first (1) insurance year", "Μετά την συμπλήρωση του πρώτου (1) ασφαλιστικού έτους"),
            ("Knee conditions and accidents, and complications", "Παθήσεις και ατυχήματα γόνατος και επιπλοκές", "After the first (1) insurance year", "Μετά την συμπλήρωση του πρώτου (1) ασφαλιστικού έτους"),
        ],
    },
    ON_DEMAND: {
        "title": {"en": "Generali Doctors & Exams On Demand (Article 1)", "el": "Generali Γιατροί & Εξετάσεις On Demand (Άρθρο 1)"},
        "intro": {
            "en": "These covers start only after the period shown, counted from the start, reinstatement or change of the cover, or from the date the insured member is added. Prescription lenses can be claimed once every two consecutive insurance years.",
            "el": "Οι παρακάτω καλύψεις ξεκινούν μόνο μετά το διάστημα που αναγράφεται, από την έναρξη, επαναφορά ή τροποποίηση της παροχής ή από την προσθήκη του ασφαλισμένου μέλους. Τα γυαλιά οράσεως μπορούν να αποζημιωθούν μία φορά κάθε δύο συνεχόμενα ασφαλιστικά έτη.",
        },
        "rows": [
            ("Dental therapies (fillings, extractions, root canals)", "Οδοντιατρικές θεραπείες (σφραγίσματα, εξαγωγές, απονευρώσεις)", "After two (2) consecutive insurance years", "Μετά από δύο (2) συνεχόμενα ασφαλιστικά έτη"),
            ("Aesthetic medicine (scheduled procedures)", "Αισθητική ιατρική (προγραμματισμένες πράξεις)", "After three (3) consecutive insurance years", "Μετά από τρία (3) συνεχόμενα ασφαλιστικά έτη"),
        ],
    },
}


def tables_for(label: str, riders: Iterable[str] = ()) -> list[str]:
    """Table keys for an offer. Hospital Premium Flexi applies to any Generali plan in the study;
    the Doctors & Exams table only when the broker has marked that add-on as part of the quote."""
    keys: list[str] = []
    if "generali" in label.lower():
        keys.append(HOSPITAL)
    keys += [r for r in riders if r in TABLES and r not in keys]
    return keys


def rows(key: str, lang: str) -> Sequence[tuple[str, str]]:
    i = 1 if lang == "el" else 0
    return [(r[i], r[i + 2]) for r in TABLES[key]["rows"]]
