"""Generali waiting periods, taken from the policy wording. Each table is one wording document.

Hospital Premium Flexi: Article 5. Doctors & Exams Premium: Article 3. A table is shown only for a
plan it applies to. Nothing here is a price or an estimate.
"""
from __future__ import annotations

from typing import Iterable, Mapping, Sequence

HOSPITAL = "hospital_premium_flexi"
DOCTORS = "doctors_exams_premium"
STANDARD = "hospital_standard"
ETHNIKI = "ethniki_prosfora"
VUMI = "vumi_euro_health_vip"
ETHNIKI_TERMS = "ethniki_article10"

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
    STANDARD: {
        "title": {"en": "Generali Hospital Standard (Article 5)", "el": "Generali Νοσηλεία Standard (Άρθρο 5)"},
        "intro": {
            "en": "These conditions are covered only after the period shown. Cover applies only if the condition was not known to the insured at the start and was first diagnosed within or after that period.",
            "el": "Οι παρακάτω παθήσεις καλύπτονται μόνο μετά το διάστημα που αναγράφεται. Η κάλυψη ισχύει μόνο αν η πάθηση δεν ήταν γνωστή στην ασφαλισμένη κατά την έναρξη και διαγνώστηκε για πρώτη φορά μέσα ή μετά από αυτό το διάστημα.",
        },
        "rows": [
            ("Appendectomy", "Σκωληκοειδεκτομή", "After the first three (3) months of the first insurance year", "Μετά τους τρεις (3) πρώτους μήνες του πρώτου ασφαλιστικού έτους"),
            ("Nasal growths and tonsillectomy", "Εκβλαστήσεις της ρινικής κοιλότητας και αμυγδαλεκτομή", "After the first insurance year", "Μετά την συμπλήρωση του πρώτου ασφαλιστικού έτους"),
            ("Coronary artery disease", "Στεφανιαία νόσος", "After the first insurance year", "Μετά την συμπλήρωση του πρώτου ασφαλιστικού έτους"),
            ("Urinary tract stones", "Λιθιάσεις ουροποιητικού συστήματος", "After the first insurance year", "Μετά την συμπλήρωση του πρώτου ασφαλιστικού έτους"),
            ("Cholecystectomy", "Χολοκυστεκτομή", "After the first insurance year", "Μετά την συμπλήρωση του πρώτου ασφαλιστικού έτους"),
            ("Thyroid and parathyroid conditions, except malignancy", "Παθήσεις θυρεοειδούς και παραθυρεοειδούς αδένα, εκτός εάν αφορούν σε κακοήθεια", "After the first insurance year", "Μετά την συμπλήρωση του πρώτου ασφαλιστικού έτους"),
            ("Hernias", "Κήλες", "After the first insurance year", "Μετά την συμπλήρωση του πρώτου ασφαλιστικού έτους"),
            ("Knee conditions, except fractures and injuries proven to come from an accident", "Παθήσεις γονάτων, εκτός οστικών καταγμάτων και κακώσεων που αποδεικνύεται ότι προέρχονται από ατύχημα", "After the first insurance year", "Μετά την συμπλήρωση του πρώτου ασφαλιστικού έτους"),
            ("Benign mucosal growths", "Καλοήθη μορφώματα βλεννογόνων", "After the first insurance year", "Μετά την συμπλήρωση του πρώτου ασφαλιστικού έτους"),
            ("Bowel and anal conditions, except malignancy and infectious gastrointestinal disease", "Παθήσεις εντέρων και πρωκτού, εκτός αν αφορούν σε κακοήθεια ή λοιμώδεις ασθένειες γαστρεντερικού συστήματος", "After the first two (2) consecutive insurance years", "Μετά την συμπλήρωση των δύο (2) πρώτων συνεχόμενων ασφαλιστικών ετών"),
            ("Eye conditions of the cornea, cataract and glaucoma", "Παθήσεις οφθαλμών που αφορούν σε κερατοειδή χιτώνα, καταρράκτη και γλαύκωμα", "After the first two (2) consecutive insurance years", "Μετά την συμπλήρωση των δύο (2) πρώτων συνεχόμενων ασφαλιστικών ετών"),
            ("Coccyx cyst", "Κύστη κόκκυγος", "After the first two (2) consecutive insurance years", "Μετά την συμπλήρωση των δύο (2) πρώτων συνεχόμενων ασφαλιστικών ετών"),
            ("Knee and/or hip replacement", "Αρθροπλαστική γονάτων ή/και ισχίων", "After the first two (2) consecutive insurance years", "Μετά την συμπλήρωση των δύο (2) πρώτων συνεχόμενων ασφαλιστικών ετών"),
            ("Peripheral vascular disease", "Περιφερική αγγειοπάθεια", "After the first two (2) consecutive insurance years", "Μετά την συμπλήρωση των δύο (2) πρώτων συνεχόμενων ασφαλιστικών ετών"),
            ("Lower-limb vein conditions", "Παθήσεις φλεβών κάτω άκρων", "After the first two (2) consecutive insurance years", "Μετά την συμπλήρωση των δύο (2) πρώτων συνεχόμενων ασφαλιστικών ετών"),
            ("Genital conditions, except malignancy", "Παθήσεις γεννητικών οργάνων, εκτός αν αφορούν σε κακοήθεια", "After the first two (2) consecutive insurance years. The wait does not apply if an internal genital ultrasound and Pap test (women) or prostate ultrasound and PSA (men) were done with no abnormal findings in the year before the start", "Μετά την συμπλήρωση των δύο (2) πρώτων συνεχόμενων ασφαλιστικών ετών. Η αναμονή δεν ισχύει αν έχουν γίνει, χωρίς παθολογικά ευρήματα και μέσα στο έτος πριν από την έναρξη, υπέρηχος έσω γεννητικών οργάνων και test Παπανικολάου (γυναίκες) ή υπέρηχος προστάτη και PSA (άνδρες)"),
            ("Breast conditions, except malignancy", "Παθήσεις μαστών, εκτός αν αφορούν σε κακοήθεια", "After the first two (2) consecutive insurance years. The wait does not apply if a breast ultrasound and mammography (from age 35) were done with no abnormal findings in the year before the start", "Μετά την συμπλήρωση των δύο (2) πρώτων συνεχόμενων ασφαλιστικών ετών. Η αναμονή δεν ισχύει αν έχουν γίνει, χωρίς παθολογικά ευρήματα και μέσα στο έτος πριν από την έναρξη, υπέρηχος μαστών και μαστογραφία (από 35 ετών και άνω)"),
            ("Pregnancy complication, miscarriage or medically required termination", "Επιπλοκή εγκυμοσύνης, αποβολή ή διακοπή εγκυμοσύνης που επιβάλλεται για ιατρικούς λόγους", "After the first two (2) consecutive insurance years", "Μετά την συμπλήρωση των δύο (2) πρώτων συνεχόμενων ασφαλιστικών ετών"),
            ("Deviated nasal septum, ethmoidectomy, conchotomy", "Σκολίωση ρινικού διαφράγματος, ηθμοειδεκτομή, κογχοτομή", "After the first three (3) consecutive insurance years", "Μετά την συμπλήρωση των τριών (3) πρώτων συνεχόμενων ασφαλιστικών ετών"),
            ("Spinal conditions", "Παθήσεις σπονδυλικής στήλης", "After the first three (3) consecutive insurance years. The wait does not apply to an injury proven medically and by imaging", "Μετά την συμπλήρωση των τριών (3) πρώτων συνεχόμενων ασφαλιστικών ετών. Δεν ισχύει η αναμονή σε κάκωση αποδεδειγμένη ιατρικά και απεικονιστικά"),
            ("Treatment and surgical removal of moles and papillomas", "Θεραπεία και χειρουργική αφαίρεση σπίλων και θηλωμάτων", "After the first three (3) consecutive insurance years", "Μετά την συμπλήρωση των τριών (3) πρώτων συνεχόμενων ασφαλιστικών ετών"),
            ("Morbid obesity", "Νοσογόνος παχυσαρκία", "After the first three (3) consecutive insurance years", "Μετά την συμπλήρωση των τριών (3) πρώτων συνεχόμενων ασφαλιστικών ετών"),
            ("Alzheimer's disease and dementia", "Νόσος Alzheimer και άνοια", "After the first three (3) consecutive insurance years", "Μετά την συμπλήρωση των τριών (3) πρώτων συνεχόμενων ασφαλιστικών ετών"),
            ("Congenital conditions (Article 7)", "Συγγενείς παθήσεις (Άρθρο 7)", "Manifested or diagnosed after two (2) consecutive insurance years, and not known at the start. For a minor, after the 5th birthday. Congenital heart conditions: after ten (10) consecutive insurance years", "Εκδηλώθηκαν ή διαγνώστηκαν μετά από δύο (2) συνεχόμενα ασφαλιστικά έτη και δεν ήταν γνωστές κατά την έναρξη. Για ανήλικο, μετά το 5ο έτος της ηλικίας. Καρδιολογικές συγγενείς παθήσεις: μετά από δέκα (10) συνεχόμενα ασφαλιστικά έτη"),
        ],
    },
    ETHNIKI: {
        "title": {"en": "Εθνική Προνομιακή Προστασία (offer Υ2026_0170804)", "el": "Εθνική Προνομιακή Προστασία (προσφορά Υ2026_0170804)"},
        "intro": {
            "en": "Waiting periods stated in the offer. The policy wording prevails.",
            "el": "Περίοδοι αναμονής όπως αναγράφονται στην προσφορά. Το ασφαλιστήριο συμβόλαιο είναι η τελική πηγή.",
        },
        "rows": [
            ("Hospital treatment, surgery without hospital stay and urgent transport for an illness first appearing in the first 30 days (Article 5A)", "Νοσηλεία, χειρουργική επέμβαση χωρίς νοσηλεία και επείγουσα μεταφορά για ασθένεια που εκδηλώθηκε πρώτη φορά εντός των πρώτων 30 ημερών (Άρθρο 5Α)", "Covered only after the first 30 days of the insurance. Nothing is paid for those 30 days", "Καλύπτεται μόνο μετά τις πρώτες 30 ημέρες από την έναρξη. Για αυτό το διάστημα δεν καταβάλλεται καμία αποζημίωση"),
            ("Tonsils or adenoids, hernia, and women's genital organs. Also hospitals outside the European Union", "Αμυγδαλές ή αδενοειδείς εκβλαστήσεις, κήλη και γεννητικά όργανα της γυναίκας. Επίσης νοσοκομεία εκτός Ευρωπαϊκής Ένωσης", "After the first 6 months of the insurance", "Μετά τους πρώτους 6 μήνες ασφάλισης"),
            ("Pre-existing conditions known and declared on the application, unless excluded for longer by a special term", "Προϋπάρχουσες βλάβες ή ασθένειες που ήταν γνωστές και δηλώθηκαν στην αίτηση, εκτός αν έχουν εξαιρεθεί για μεγαλύτερο διάστημα με ειδικό όρο", "After the first insurance year", "Μετά το πρώτο ασφαλιστικό έτος"),
            ("Haemorrhoids, anal fissure, varicose veins, nasal septum", "Αιμορροΐδες, ραγάδα δακτυλίου, κιρσοί, ρινικό διάφραγμα", "After the first insurance year", "Μετά το πρώτο ασφαλιστικό έτος"),
            ("General investigative gynaecological surgery, only if disease is proven", "Γενικές ερευνητικές γυναικολογικές επεμβάσεις, μόνο εφόσον αποδειχθεί ασθένεια", "After the first insurance year", "Μετά το πρώτο ασφαλιστικό έτος"),
            ("Rheumatic and degenerative conditions of bones and joints, meniscus, knee ligament rupture, slipped disc", "Ρευματικές και εκφυλιστικές παθήσεις οστών και αρθρώσεων, μηνίσκοι, ρήξη συνδέσμων γονάτων, κήλη μεσοσπονδυλίου δίσκου", "After the first insurance year", "Μετά το πρώτο ασφαλιστικό έτος"),
            ("Congenital conditions", "Συγγενείς παθήσεις", "After the first two (2) insurance years. If known and not declared on the application, never covered", "Μετά τα δύο (2) πρώτα ασφαλιστικά έτη. Αν ήταν γνωστές και δεν δηλώθηκαν στην αίτηση, δεν καλύπτονται ποτέ"),
        ],
    },
    VUMI: {
        "title": {"en": "VUMI Euro Health VIP Priority (Table of Benefits)", "el": "VUMI Euro Health VIP Priority (Πίνακας Παροχών)"},
        "intro": {
            "en": "Waiting periods stated in the Table of Benefits. The policy wording prevails.",
            "el": "Περίοδοι αναμονής όπως αναγράφονται στον Πίνακα Παροχών. Το ασφαλιστήριο συμβόλαιο είναι η τελική πηγή.",
        },
        "rows": [
            ("General waiting period", "Γενική περίοδος αναμονής", "30 days", "30 ημέρες"),
            ("HIV-AIDS", "HIV-AIDS", "36 months", "36 μήνες"),
        ],
    },
    ETHNIKI_TERMS: {
        "title": {"en": "Εθνική: end of cover and right to continue (Article 10)", "el": "Εθνική: παύση ισχύος και δικαίωμα συνέχισης (Άρθρο 10)"},
        "intro": {
            "en": "From the policy wording, Article 10. The policy wording prevails.",
            "el": "Από το ασφαλιστήριο, Άρθρο 10. Το ασφαλιστήριο συμβόλαιο είναι η τελική πηγή.",
        },
        "rows": [
            ("Death of the insured", "Θάνατος του Ασφαλισμένου", "The policy ends. Premiums paid after it ends are refunded without interest", "Το ασφαλιστήριο παύει να ισχύει. Ασφάλιστρα που καταβλήθηκαν μετά τη λήξη επιστρέφονται άτοκα"),
            ("Dependent children", "Εξαρτώμενα παιδιά", "Cover ends at the policy anniversary closest to the 25th birthday, or on marriage if earlier", "Η κάλυψη παύει στην επέτειο του ασφαλιστηρίου που είναι πλησιέστερη στην 25η επέτειο γέννησης, ή με τον γάμο αν προηγηθεί"),
            ("Child reaching 25: right to continue", "Παιδί που συμπληρώνει τα 25: δικαίωμα συνέχισης", "Individual policy, no insurability check, same or similar programme on the terms of that date. Written request within 1 month of the end of cover", "Ατομικό ασφαλιστήριο, χωρίς έλεγχο ασφαλισιμότητας, με το ίδιο ή παρόμοιο πρόγραμμα και τους όρους της ημερομηνίας αυτής. Έγγραφη αίτηση εντός 1 μηνός από τη λήξη της κάλυψης"),
            ("Death of the insured: right of dependants (spouse, children) to continue", "Θάνατος του Ασφαλισμένου: δικαίωμα συνέχισης των εξαρτωμένων (σύζυγος, παιδιά)", "Individual policy, no insurability check, same or similar programme. Written request within 1 month of the date of death", "Ατομικό ασφαλιστήριο, χωρίς έλεγχο ασφαλισιμότητας, με το ίδιο ή παρόμοιο πρόγραμμα. Έγγραφη αίτηση εντός 1 μηνός από την ημερομηνία θανάτου"),
        ],
    },
}


def tables_for(label: str, riders: Iterable[str] = ()) -> list[str]:
    """Table keys for an offer. A Generali plan named Standard gets the Hospital Standard table, any other Generali plan the Hospital Premium Flexi table; Εθνική gets its offer table;
    the Doctors & Exams table only when the broker has marked that add-on as part of the quote."""
    keys: list[str] = []
    name = label.lower()
    if "generali" in name:
        keys.append(STANDARD if "standard" in name else HOSPITAL)
    if "εθνική" in name or "ethniki" in name:
        keys += [ETHNIKI, ETHNIKI_TERMS]
    if "vumi" in name:
        keys.append(VUMI)
    keys += [r for r in riders if r in TABLES and r not in keys]
    return keys


def rows(key: str, lang: str) -> Sequence[tuple[str, str]]:
    i = 1 if lang == "el" else 0
    return [(r[i], r[i + 2]) for r in TABLES[key]["rows"]]


def register_table(key: str, title: Mapping[str, str], intro: Mapping[str, str], rows: Iterable[Sequence[str]]) -> str:
    """Add a waiting-period table at run time, for a plan the code does not know yet.

    Rows are ``(en_condition, el_condition, en_period, el_period)``. The key is returned. An existing
    built-in table is never replaced, so a reader cannot overwrite a table a broker already checked.
    """
    if key in TABLES and not key.startswith("read_"):
        raise ValueError(f"{key} is a built-in table and cannot be replaced.")
    TABLES[key] = {"title": dict(title), "intro": dict(intro), "rows": [tuple(r) for r in rows]}
    return key
