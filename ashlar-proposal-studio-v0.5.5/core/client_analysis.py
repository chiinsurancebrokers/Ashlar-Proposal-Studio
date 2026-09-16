"""Client-facing analysis generation for Ashlar Proposal Studio.

The module separates facts from narrative:
- comparison rows are built deterministically from structured plan extractions;
- the LLM writes client-facing synthesis only from that grounded payload;
- optional benefits are never promoted to included benefits unless the quote analysis says so.
"""
from __future__ import annotations

import json
import os
import re
from typing import Any


from .json_utils import parse_best_json_object, parse_json_objects
from .report_schema import ClientReportValidationError, validate_client_report


BENEFIT_ORDER = [
    ("inpatient", "In-patient treatment"),
    ("outpatient", "Out-patient treatment"),
    ("cancer", "Cancer / oncology"),
    ("chronic_conditions", "Chronic conditions"),
    ("mental_health", "Mental health"),
    ("maternity", "Maternity"),
    ("dental", "Dental"),
    ("optical", "Optical"),
    ("diagnostics_imaging", "Diagnostics / advanced imaging"),
    ("preventive", "Preventive / wellness"),
    ("evacuation_repatriation", "Evacuation / repatriation"),
]


def plan_display_name(result: dict) -> str:
    a = result.get("analysis") or {}
    provider = a.get("provider") or result.get("provider") or "Provider"
    plan = a.get("plan_name") or result.get("target_plan") or "Plan"
    return f"{provider} - {plan}"


def premium_display(analysis: dict) -> str:
    p = analysis.get("premium") or {}
    amount = p.get("amount")
    if amount in (None, "", "Not specified"):
        return "Not specified"
    currency = p.get("currency") or ""
    frequency = p.get("frequency") or ""
    pieces = [str(currency).strip(), str(amount).strip(), str(frequency).strip()]
    return " ".join(x for x in pieces if x)


def _safe_text(value: Any) -> str:
    if value is None:
        return "Not specified"
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    text = str(value).strip()
    return text or "Not specified"




def _normalise_sex(value: str | None) -> str:
    key = str(value or "").strip().casefold()
    if key in {"male", "m", "man", "boy", "αρρεν", "άρρεν", "ανδρας", "άνδρας"}:
        return "male"
    if key in {"female", "f", "woman", "girl", "θηλυ", "θήλυ", "γυναικα", "γυναίκα"}:
        return "female"
    return "unspecified"


def maternity_relevant(*, client_sex: str = "", client_priorities: str = "") -> bool:
    """Maternity is client-facing only for a female applicant.

    A partner's potential pregnancy is not an insured benefit of a male applicant's
    individual policy, so the report must not turn it into a recommendation factor.
    """
    return _normalise_sex(client_sex) == "female"


def client_facing_deductible(value: Any) -> str:
    """Keep the client-facing financial summary simple.

    Zero cost-share / zero out-of-pocket phrases add no decision value when there is no
    member participation. Non-zero co-insurance remains visible in the underlying
    benefit detail where it genuinely applies.
    """
    text = _safe_text(value)
    if text == "Not specified":
        return text
    parts = [p.strip() for p in re.split(r";|\|", text) if p.strip()]
    kept = []
    for part in parts:
        key = part.casefold()
        if re.search(r"\b0(?:\.0+)?%\s*(?:cost\s*share|co[- ]?insurance)", key):
            continue
        if re.search(r"(?:€|eur|\$|usd|£|gbp)\s*0(?:\.0+)?\s*out[- ]of[- ]pocket", key):
            continue
        kept.append(part)
    return "; ".join(kept) if kept else text


FMU_PRE_EXISTING_CLIENT_TEXT = "Subject to underwriting approval; pre-existing conditions are excluded unless specifically accepted by the insurer in writing."


def client_facing_pre_existing_conditions(analysis: dict) -> str:
    """Standardise the client-facing pre-existing-condition wording for FMU cases.

    Ashlar uses one consistent explanation across fully medically underwritten IPMI
    options so the comparison does not imply a material difference merely because
    one insurer's brochure phrases the underwriting rule differently. Other
    underwriting bases (CPME, MHD, moratorium, etc.) keep their extracted wording.
    """
    underwriting = analysis.get("underwriting") or {}
    basis = _normalise_underwriting_basis(underwriting.get("basis"))
    if basis == "fmu":
        return FMU_PRE_EXISTING_CLIENT_TEXT
    return _safe_text(underwriting.get("pre_existing_conditions"))


def _strip_age_health_inference(text: Any) -> str:
    """Remove unsupported health-risk assumptions derived only from age/profile."""
    raw = str(text or "").strip()
    if not raw:
        return raw
    parts = re.split(r"(?<=[.!?])\s+", raw)
    bad = [
        r"\b(?:at|because of) age \d+.*(?:unlikely|likely).*(?:pre-existing|chronic|health)",
        r"\bunlikely to have (?:significant )?pre-existing conditions",
        r"\blikely health profile\b",
        r"\bassuming (?:he|she|the applicant) remains in good (?:mental )?health\b",
        r"\bno anticipated chronic illness\b",
    ]
    kept=[]
    for part in parts:
        key=part.casefold()
        if any(re.search(p, key, re.I) for p in bad):
            continue
        kept.append(part)
    return " ".join(kept).strip()


def find_plan_narrative(plans: list[dict], result: dict) -> dict:
    """Match an LLM plan narrative back to a structured result robustly.

    Provider labels often contain the product name (e.g. 'CIGNA SILVER') while the
    narrative may use simply 'CIGNA'. Exact tuple matching left otherwise-valid
    plan pages blank, so we fall back to contained provider names with an exact
    normalised plan match.
    """
    a = result.get("analysis") or {}
    provider = str(a.get("provider") or result.get("provider") or "").strip()
    plan = str(a.get("plan_name") or result.get("target_plan") or "").strip()

    def norm(v: Any) -> str:
        return re.sub(r"[^a-z0-9]+", " ", str(v or "").casefold()).strip()

    rp, rn = norm(provider), norm(plan)
    for item in plans or []:
        if norm(item.get("provider")) == rp and norm(item.get("plan_name")) == rn:
            return item
    for item in plans or []:
        ip, inn = norm(item.get("provider")), norm(item.get("plan_name"))
        provider_match = bool(ip and rp and (ip in rp or rp in ip))
        plan_match = bool(inn and rn and (inn == rn or inn in rn or rn in inn))
        if provider_match and plan_match:
            return item
    return {}


def _has_nonzero_core_cost_share(results: list[dict]) -> bool:
    for result in results:
        value = str((result.get("analysis") or {}).get("deductible_or_excess") or "")
        for m in re.finditer(r"(\d{1,3}(?:\.\d+)?)%\s*(?:cost\s*share|co[- ]?insurance)", value, re.I):
            try:
                if float(m.group(1)) > 0:
                    return True
            except ValueError:
                pass
    return False


def _contains_maternity(text: Any) -> bool:
    return bool(re.search(r"\b(?:maternity|pregnan|childbirth|newborn|homebirth|family building)\b", str(text or ""), re.I))


def _strip_maternity_sentences(text: Any) -> str:
    raw = str(text or "").strip()
    if not raw:
        return raw
    parts = re.split(r"(?<=[.!?])\s+", raw)
    kept = [part for part in parts if not _contains_maternity(part)]
    return " ".join(kept).strip()


def _strip_zero_cost_share_phrases(text: Any) -> str:
    raw = str(text or "")
    raw = re.sub(r"\b(?:and\s+)?zero cost[- ]?sharing(?: across all selected modules)?\b", "", raw, flags=re.I)
    raw = re.sub(r"\bwithout cost[- ]?sharing\b", "", raw, flags=re.I)
    raw = re.sub(r"\bfree at point of use(?: within limits)?\b", "", raw, flags=re.I)
    raw = re.sub(r"\s{2,}", " ", raw)
    raw = re.sub(r"\s+([,.;:])", r"\1", raw)
    return raw.strip(" ,;")


def _neutralise_module_architecture_bias(text: Any) -> str:
    """Do not let base-plan vs selected-module packaging drive the recommendation.

    Client comparisons should assess the final quoted configuration. Product architecture
    may still be described factually on plan pages, but it should not be framed as an
    intrinsic advantage once an optional module is confirmed selected and priced.
    """
    raw = str(text or "")
    replacements = [
        (r"within (?:its|the) base plan,? without requiring optional modules to reach that scope", "within the quoted configuration"),
        (r"within (?:its|the) base premium", "within the quoted premium"),
        (r"included in (?:its|the) base premium,? not an optional add-on", "included in the quoted cover"),
        (r"without needing optional modules", "within the quoted configuration"),
        (r"without requiring optional modules", "within the quoted configuration"),
    ]
    for pattern, repl in replacements:
        raw = re.sub(pattern, repl, raw, flags=re.I)
    raw = re.sub(r"\s{2,}", " ", raw)
    return raw.strip()


def _internal_consideration(text: Any) -> bool:
    """Filter broker-internal housekeeping from a client-facing report."""
    key = str(text or "").casefold()
    patterns = [
        r"broker\s+(?:must|should|needs? to)",
        r"clarify\s+(?:cigna|img|bupa|now health|the insurer)",
        r"underwriting basis.*not specified",
        r"request (?:a copy|the full|contact details|provider directories)",
        r"visa (?:type|status|category)",
        r"residency status",
        r"provider director",
        r"binding quotation",
        r"German statutory",
        r"current or likely gp",
        r"premium increases",
    ]
    return any(re.search(p, key) for p in patterns)


def _positive_waiting_period_or_usage(text: Any) -> bool:
    key = str(text or "").casefold()
    return any(token in key for token in (
        "waiting period", "annual limit", "sub-limit", "sublimit", "deductible",
        "not covered", "excluded", "limited to", "per visit", "per year",
        "pre-authorisation", "preauthorization", "network", "area of cover",
    ))



def _normalise_underwriting_basis(value: Any) -> str:
    key = str(value or "").strip().casefold()
    if not key:
        return "unknown"
    if key in {"fmu", "full medical underwriting", "full medical", "medical underwriting"} or "full medical underwriting" in key:
        return "fmu"
    if "cpme" in key or "continued personal medical exclusions" in key:
        return "cpme"
    if "medical history disregarded" in key or key == "mhd" or "mhd" in key:
        return "mhd"
    if "moratorium" in key:
        return "moratorium"
    return key


def _recommended_underwriting_basis(report: dict, results: list[dict]) -> str:
    """Resolve underwriting for the recommended plan, then fall back to a common case basis."""
    assessment = report.get("ashlar_assessment") or {}
    rec_provider = str(assessment.get("recommended_provider") or "").strip().casefold()
    rec_plan = str(assessment.get("recommended_plan") or "").strip().casefold()

    matched = []
    for result in results or []:
        analysis = result.get("analysis") or {}
        provider = str(analysis.get("provider") or result.get("provider") or "").strip().casefold()
        plan = str(analysis.get("plan_name") or result.get("target_plan") or "").strip().casefold()
        basis = _normalise_underwriting_basis((analysis.get("underwriting") or {}).get("basis"))
        if rec_provider and rec_provider in provider and (not rec_plan or rec_plan in plan):
            return basis
        if basis != "unknown":
            matched.append(basis)

    unique = {x for x in matched if x != "unknown"}
    if len(unique) == 1:
        return next(iter(unique))
    return "unknown"


def _underwriting_next_steps(basis: str, *, greek: bool = False) -> list[str]:
    """Deterministic client workflow for known underwriting methods."""
    basis = _normalise_underwriting_basis(basis)
    if greek:
        if basis == "fmu":
            return [
                "Συμπληρώστε την αίτηση ασφάλισης και την πλήρη δήλωση ιατρικού ιστορικού για το πρόγραμμα που θα επιλεγεί.",
                "Η αίτηση θα υποβληθεί για πλήρη ιατρική αξιολόγηση (Full Medical Underwriting). Η ασφαλιστική μπορεί, εφόσον χρειάζεται, να ζητήσει πρόσθετες ιατρικές πληροφορίες ή εξετάσεις.",
                "Ελέγξτε τους τελικούς όρους underwriting της ασφαλιστικής, συμπεριλαμβανομένων τυχόν εξατομικευμένων εξαιρέσεων ή ειδικών όρων, καθώς και το τελικό επιβεβαιωμένο ασφάλιστρο και την ημερομηνία έναρξης.",
                "Εφόσον οι τελικοί όροι γίνουν αποδεκτοί, ολοκληρώστε την αποδοχή και την ενεργοποίηση του συμβολαίου.",
            ]
        if basis == "moratorium":
            return [
                "Συμπληρώστε την αίτηση για το πρόγραμμα που θα επιλεγεί.",
                "Επιβεβαιώστε τους όρους moratorium που θα εφαρμοστούν σε προϋπάρχουσες παθήσεις και την περίοδο που απαιτείται πριν αυτές μπορούν να εξεταστούν για κάλυψη.",
                "Ελέγξτε το τελικό policy schedule, τους ειδικούς όρους, το τελικό ασφάλιστρο και την ημερομηνία έναρξης.",
                "Εφόσον οι τελικοί όροι γίνουν αποδεκτοί, ολοκληρώστε την αποδοχή και την ενεργοποίηση του συμβολαίου.",
            ]
        if basis == "cpme":
            return [
                "Συμπληρώστε την αίτηση για το πρόγραμμα που θα επιλεγεί και προσκομίστε τα στοιχεία προηγούμενης ασφάλισης που απαιτούνται για αξιολόγηση CPME.",
                "Η ασφαλιστική θα επιβεβαιώσει ποιοι υφιστάμενοι προσωπικοί ιατρικοί όροι ή εξαιρέσεις μεταφέρονται στη νέα κάλυψη.",
                "Ελέγξτε τους τελικούς όρους CPME, το τελικό ασφάλιστρο και την ημερομηνία έναρξης πριν από οποιαδήποτε αντικατάσταση υφιστάμενης κάλυψης.",
                "Εφόσον οι τελικοί όροι γίνουν αποδεκτοί, ολοκληρώστε την αποδοχή και την ενεργοποίηση του συμβολαίου.",
            ]
        if basis == "mhd":
            return [
                "Ολοκληρώστε την αίτηση/εγγραφή για το πρόγραμμα που θα επιλεγεί.",
                "Επιβεβαιώστε ότι εφαρμόζεται Medical History Disregarded (MHD) στην συγκεκριμένη ομάδα/κατηγορία μελών και ότι πληρούνται οι προϋποθέσεις ένταξης.",
                "Ελέγξτε το τελικό policy schedule, το ασφάλιστρο, την ημερομηνία έναρξης και τυχόν λοιπούς όρους του ομαδικού συμβολαίου.",
                "Εφόσον οι τελικοί όροι γίνουν αποδεκτοί, ολοκληρώστε την ενεργοποίηση της κάλυψης.",
            ]
    else:
        if basis == "fmu":
            return [
                "Complete the insurance application and full medical history declaration for the selected plan.",
                "The application will then be submitted for Full Medical Underwriting. The insurer may request additional medical information or supporting reports where required.",
                "Review the insurer's final underwriting terms, including any applicant-specific exclusions or special conditions, together with the final confirmed premium and effective date.",
                "If the final terms are acceptable, complete acceptance and activate the policy.",
            ]
        if basis == "moratorium":
            return [
                "Complete the application for the selected plan.",
                "Confirm the moratorium terms that will apply to pre-existing conditions and the qualifying period before those conditions may become eligible for cover.",
                "Review the final policy schedule, special terms, confirmed premium and effective date.",
                "If the final terms are acceptable, complete acceptance and activate the policy.",
            ]
        if basis == "cpme":
            return [
                "Complete the application for the selected plan and provide the prior-insurance evidence required for CPME assessment.",
                "The insurer will confirm which existing personal medical terms or exclusions are carried forward into the new cover.",
                "Review the final CPME terms, confirmed premium and effective date before replacing any existing cover.",
                "If the final terms are acceptable, complete acceptance and activate the policy.",
            ]
        if basis == "mhd":
            return [
                "Complete the enrolment/application for the selected plan.",
                "Confirm that Medical History Disregarded (MHD) applies to the relevant group/member category and that all eligibility requirements are met.",
                "Review the final policy schedule, premium, effective date and any other applicable group-policy conditions.",
                "If the final terms are acceptable, complete enrolment and activate cover.",
            ]
    return []

def apply_client_report_rules(
    report: dict,
    *,
    results: list[dict],
    client_sex: str = "",
    client_age: int | None = None,
    client_priorities: str = "",
    language: str = "English",
) -> dict:
    """Deterministic editorial guardrail after narrative generation.

    The LLM can write prose, but it cannot override applicant relevance or turn
    zero-cost-sharing into a material comparison point.
    """
    relevant_maternity = maternity_relevant(client_sex=client_sex, client_priorities=client_priorities)
    has_cost_share = _has_nonzero_core_cost_share(results)

    # Applicant relevance: remove maternity from a male applicant's client-facing narrative.
    if not relevant_maternity:
        for key in ("executive_summary", "client_needs_summary"):
            report[key] = _strip_maternity_sentences(report.get(key))
        for plan in report.get("plans") or []:
            for key in ("positioning", "summary", "best_suited_when"):
                plan[key] = _strip_maternity_sentences(plan.get(key))
            plan["strengths"] = [x for x in (plan.get("strengths") or []) if not _contains_maternity(x)]
            plan["considerations"] = [x for x in (plan.get("considerations") or []) if not _contains_maternity(x)]
        report["key_differences"] = [
            d for d in (report.get("key_differences") or [])
            if not _contains_maternity(" ".join(str(d.get(k) or "") for k in ("title", "analysis", "client_impact")))
        ]
        ass = report.get("ashlar_assessment") or {}
        for key in ("headline", "alternative_reason", "when_the_alternative_may_be_better"):
            ass[key] = _strip_maternity_sentences(ass.get(key))
        ass["reasoning"] = [x for x in (ass.get("reasoning") or []) if not _contains_maternity(x)]

    # Zero cost share is not a useful standalone comparison topic. Keep only deductible.
    if not has_cost_share:
        report["key_differences"] = [
            d for d in (report.get("key_differences") or [])
            if not re.search(r"cost[- ]?sharing|co[- ]?insurance|out[- ]of[- ]pocket friction", str(d.get("title") or ""), re.I)
        ]
        report["executive_summary"] = _strip_zero_cost_share_phrases(report.get("executive_summary"))
        for plan in report.get("plans") or []:
            plan["summary"] = _strip_zero_cost_share_phrases(plan.get("summary"))
            plan["strengths"] = [x for x in (plan.get("strengths") or []) if not re.search(r"zero cost[- ]?sharing|free at point of use", str(x), re.I)]
        ass = report.get("ashlar_assessment") or {}
        ass["headline"] = _strip_zero_cost_share_phrases(ass.get("headline"))
        ass["reasoning"] = [
            _strip_zero_cost_share_phrases(x) for x in (ass.get("reasoning") or [])
            if not re.search(r"zero cost[- ]?sharing|free at point of use", str(x), re.I)
        ]
        ass["alternative_reason"] = _strip_zero_cost_share_phrases(ass.get("alternative_reason"))
        ass["when_the_alternative_may_be_better"] = _strip_zero_cost_share_phrases(ass.get("when_the_alternative_may_be_better"))

    # Do not allow age alone to become a proxy for health or underwriting risk.
    for key in ("executive_summary", "client_needs_summary"):
        report[key] = _strip_age_health_inference(report.get(key))
    for plan in report.get("plans") or []:
        for key in ("positioning", "summary", "best_suited_when"):
            plan[key] = _strip_age_health_inference(plan.get(key))
        plan["strengths"] = [_strip_age_health_inference(x) for x in (plan.get("strengths") or []) if _strip_age_health_inference(x)]
        plan["considerations"] = [_strip_age_health_inference(x) for x in (plan.get("considerations") or []) if _strip_age_health_inference(x)]
    ass = report.get("ashlar_assessment") or {}
    ass["headline"] = _neutralise_module_architecture_bias(_strip_age_health_inference(ass.get("headline")))
    ass["reasoning"] = [
        _neutralise_module_architecture_bias(_strip_age_health_inference(x))
        for x in (ass.get("reasoning") or [])
        if _strip_age_health_inference(x)
    ]
    ass["alternative_reason"] = _neutralise_module_architecture_bias(_strip_age_health_inference(ass.get("alternative_reason")))
    ass["when_the_alternative_may_be_better"] = _neutralise_module_architecture_bias(_strip_age_health_inference(ass.get("when_the_alternative_may_be_better")))

    # Client-facing considerations: useful policy mechanics only, not internal broker housekeeping.
    considerations = []
    for item in report.get("important_considerations") or []:
        if _internal_consideration(item):
            continue
        if not relevant_maternity and _contains_maternity(item):
            continue
        if _positive_waiting_period_or_usage(item) or any(k in str(item).casefold() for k in ("mental health", "chronic", "dental", "optical", "usa")):
            considerations.append(str(item).strip())
        if len(considerations) >= 5:
            break
    report["important_considerations"] = [
        item for item in considerations if _waiting_period_claim_supported(item, results)
    ]

    # Deterministic prose sanity checks for easy-to-verify comparative superlatives.
    _sanitize_advisory_superlatives(report, results)

    # Underwriting-aware next steps are deterministic whenever the method is known.
    # This prevents an FMU case from omitting the application + medical history stage.
    basis = _recommended_underwriting_basis(report, results)
    greek = str(language or "").lower().startswith(("gr", "el")) or "greek" in str(language or "").lower()
    workflow_steps = _underwriting_next_steps(basis, greek=greek)
    if workflow_steps:
        report["next_steps"] = workflow_steps[:4]
    else:
        steps = []
        for item in report.get("next_steps") or []:
            if _internal_consideration(item):
                continue
            if not relevant_maternity and _contains_maternity(item):
                continue
            steps.append(str(item).strip())
            if len(steps) >= 4:
                break
        report["next_steps"] = steps

    ass = report.get("ashlar_assessment") or {}
    ass["reasoning"] = [x for x in (ass.get("reasoning") or []) if _waiting_period_claim_supported(x, results)]
    for key in ("alternative_reason", "when_the_alternative_may_be_better", "extras_reason", "budget_reason"):
        if ass.get(key) and not _waiting_period_claim_supported(ass.get(key), results):
            ass[key] = ""

    report["client_sex"] = _normalise_sex(client_sex)
    report["client_age"] = client_age
    return report


def build_comparison_matrix(
    results: list[dict],
    *,
    client_sex: str = "",
    client_age: int | None = None,
    client_priorities: str = "",
) -> list[dict]:
    """Build broker/client comparison rows without LLM interpretation."""
    plan_names = [plan_display_name(r) for r in results]
    rows: list[dict] = []

    def add_row(topic: str, getter, category: str = "Core") -> None:
        rows.append({
            "category": category,
            "topic": topic,
            "values": {
                name: _safe_text(getter((r.get("analysis") or {})))
                for name, r in zip(plan_names, results)
            },
        })

    add_row("Premium", premium_display, "Financial")
    add_row("Annual policy limit", lambda a: a.get("annual_limit"), "Financial")
    add_row("Deductible / excess", lambda a: client_facing_deductible(a.get("deductible_or_excess")), "Financial")
    add_row("Area of cover", lambda a: a.get("area_of_cover"), "Core")
    add_row("Underwriting basis", lambda a: (a.get("underwriting") or {}).get("basis"), "Underwriting")
    add_row(
        "Pre-existing conditions",
        client_facing_pre_existing_conditions,
        "Underwriting",
    )
    for key, label in BENEFIT_ORDER:
        if key == "maternity" and not maternity_relevant(client_sex=client_sex, client_priorities=client_priorities):
            continue
        add_row(label, lambda a, k=key: (a.get("benefits") or {}).get(k), "Benefits")
    return rows


def _source_digest(result: dict) -> list[dict]:
    """Keep only material supporting references for the report writer.

    The extraction engine may retain dozens of rows for audit purposes. Sending all
    of them back to the narrative model made four-plan reports unnecessarily large
    and slow. The client writer needs the canonical facts plus a small evidence map,
    not the full extraction audit.
    """
    a = result.get("analysis") or {}
    evidence = []
    seen = set()

    material_fields = {
        "premium", "annual_limit", "deductible_or_excess", "area_of_cover",
        "underwriting", "inpatient", "outpatient", "mental_health",
        "diagnostics_imaging", "preventive", "dental", "optical",
        "evacuation_repatriation", "chronic_conditions", "cancer",
    }

    for item in (a.get("source_evidence") or []):
        if not isinstance(item, dict):
            continue
        field = str(item.get("field") or "").strip()
        if field and field not in material_fields and len(evidence) >= 5:
            continue
        key = (field, str(item.get("document") or ""), str(item.get("page") or ""))
        if key in seen:
            continue
        seen.add(key)
        evidence.append({
            "field": item.get("field"),
            "value": item.get("value"),
            "document": item.get("document"),
            "page": item.get("page"),
            "evidence": item.get("evidence"),
        })
        if len(evidence) >= 7:
            break

    # Add a handful of deterministic target-plan rows, prioritising material benefits.
    material_terms = (
        "outpatient", "inpatient", "mental", "diagnostic", "imaging", "chronic",
        "cancer", "dental", "optical", "evac", "wellness", "prevent", "annual",
    )
    focused = list(result.get("focused_rows") or [])
    focused.sort(key=lambda r: 0 if any(t in str(r.get("benefit") or "").casefold() for t in material_terms) else 1)
    for row in focused:
        key = (str(row.get("benefit") or ""), str(row.get("source_file") or ""), str(row.get("page") or ""))
        if key in seen:
            continue
        seen.add(key)
        evidence.append({
            "field": row.get("benefit"),
            "value": row.get("value"),
            "document": row.get("source_file"),
            "page": row.get("page"),
            "evidence": f"Target-plan table row ({row.get('evidence_type') or 'table'})",
        })
        if len(evidence) >= 14:
            break
    return evidence


def build_grounded_case_payload(
    *,
    case_reference: str,
    client_name: str,
    client_profile: str,
    client_priorities: str,
    client_sex: str = "",
    client_age: int | None = None,
    results: list[dict] = None,
) -> dict:
    results = results or []
    plans = []
    for result in results:
        a = result.get("analysis") or {}
        plans.append({
            "display_name": plan_display_name(result),
            "provider": a.get("provider") or result.get("provider"),
            "plan_name": a.get("plan_name") or result.get("target_plan"),
            "premium": a.get("premium"),
            "deductible_or_excess": a.get("deductible_or_excess"),
            "annual_limit": a.get("annual_limit"),
            "area_of_cover": a.get("area_of_cover"),
            "underwriting": {
                **(a.get("underwriting") or {}),
                "pre_existing_conditions": client_facing_pre_existing_conditions(a),
            },
            "benefits": a.get("benefits"),
            "waiting_periods": a.get("waiting_periods"),
            "optional_benefits": a.get("optional_benefits"),
            "critical_limitations": a.get("critical_limitations"),
            "confidence": a.get("confidence"),
            "source_evidence": _source_digest(result),
        })
    return {
        "case_reference": case_reference or "Unnamed case",
        "client_name": client_name or case_reference or "Client",
        "client_profile": client_profile or "Not supplied",
        "client_priorities": client_priorities or "Not supplied",
        "client_sex": _normalise_sex(client_sex),
        "client_age": client_age,
        "maternity_relevant": maternity_relevant(client_sex=client_sex, client_priorities=client_priorities),
        "plans": plans,
        "comparison_matrix": build_comparison_matrix(
            results,
            client_sex=client_sex,
            client_age=client_age,
            client_priorities=client_priorities,
        ),
    }


CLIENT_ANALYSIS_PROMPT = """You are the senior advisory-writing engine inside Ashlar Proposal Studio.
You are preparing a CLIENT-FACING comparative health-insurance analysis on behalf of an insurance broker.

Use ONLY the supplied structured case evidence. Do not add general product knowledge or facts that are not in the payload.

Core rules:
- This is an advisory comparison, not insurer underwriting or a guarantee of cover.
- Applicant-specific quote facts take priority over generic product material.
- "Optional" or "available" must NEVER be described as included unless the case evidence confirms selection.
- If evidence is incomplete or ambiguous, say so clearly and include it under important_considerations.
- Do not rank plans using an arbitrary numeric AI score.
- The recommendation must be reasoned from the CLIENT'S stated priorities and the actual material differences.
- Compare the FINAL QUOTED CONFIGURATION, not product architecture. Once an optional module is confirmed selected and included in the quoted premium, the fact that another insurer includes the same scope in its base plan is NOT, by itself, a reason to prefer that insurer.
- Do not reward "base plan simplicity" unless the client explicitly says simplicity/modularity matters. For a generic priority such as strong in-patient and out-patient cover, compare actual scope, annual/sub-limits, meaningful sub-limits, diagnostics, waiting periods, deductible and quoted premium.
- A higher headline annual limit is not automatically "better" if another feature matters more for this client, but do not dismiss it as secondary unless the client's stated priorities justify doing so.
- If two plans are materially close but win on different dimensions, do NOT force a single winner. Leave recommended_provider/recommended_plan empty and explain the two leading fits and their trade-off in the headline/reasoning.
- If you do make a single recommendation, explicitly explain why apparently stronger competing facts (for example lower premium, higher annual limit, higher out-patient limit, or fewer sub-limits) do not outweigh the recommended plan for this specific client.
- The alternative must be the strongest competing fit for the client's stated needs, not merely the plan with the next-highest out-patient ceiling.
- Avoid marketing superlatives such as "best policy" or "comprehensive" unless the evidence itself supports the wording.
- When useful, cite sources in plain text using document/page from the supplied evidence, e.g. "[IMG brochure, p.6]".
- Keep the tone professional, independent, concise and suitable to send directly to a private client.
- Do not mention Claude, AI, LLM, model, prompt, extraction engine, or internal broker tooling.
- CLIENT RELEVANCE IS MANDATORY. Use client_sex, client_age, client_profile and client_priorities before deciding which benefits deserve narrative emphasis.
- Maternity, pregnancy, childbirth, newborn and family-building benefits may be discussed ONLY when client_sex is female. Never make a male applicant's partner pregnancy a reason to prefer a plan.
- MRI, CT and PET are diagnostic / advanced imaging benefits, NOT preventive or wellness benefits. Keep them under diagnostics/outpatient/inpatient as supported by evidence.
- If diagnostics_imaging evidence says IMG diagnostics are covered within the outpatient limit, state that accurately; do not compare Cigna imaging against IMG's small well-being allowance.
- Never carry accommodation wording (for example "Private room") into a diagnostics/imaging row. Diagnostics must use only the exact diagnostic benefit evidence.
- If a structured preventive/wellness value says routine examinations or health screening are not covered, do not soften it to "Not mentioned" and do not invent a wellness benefit.
- When core selected cover has no non-zero co-insurance/cost share, discuss only the deductible/excess for simplicity. Do not create a Cost-Sharing key difference just to say both are zero.
- Missing broker-internal facts are not automatically client concerns. Do not write phrases such as "the broker must clarify" or suggest that the broker failed to complete work.
- important_considerations must be client-friendly and limited to material features the applicant may actually use: relevant waiting periods, meaningful limits/sub-limits, selected area, deductible/excess, confirmed exclusions, or use conditions. Maximum 5 items.
- next_steps are client-facing actions only. Do not ask the client to audit the broker, obtain provider directories, verify visa categories, or request internal underwriting documents. Maximum 4 items.
- If underwriting is stated as Full Medical Underwriting in the structured case, treat that as settled. Do not call it unknown or ask for clarification.
- For Full Medical Underwriting, describe pre-existing conditions consistently as: "Subject to underwriting approval; pre-existing conditions are excluded unless specifically accepted by the insurer in writing." Do not present different brochure phrasings as a plan advantage/disadvantage.
- Never infer that an applicant is healthier, less likely to have pre-existing conditions, or less likely to use a benefit because of age alone.
- For Full Medical Underwriting, the client workflow must include: application + full medical history declaration, insurer underwriting review, review of final applicant-specific underwriting terms, then acceptance/policy activation.
- Do not invent healthcare-cost scenarios, visit counts, probabilities, or claims-cost assumptions (for example "2-3 visits will exhaust the limit" or "a healthy student is unlikely to reach the annual maximum") unless that statement is explicitly supported by supplied evidence.
- Keep the report concise enough to fit reliably in one structured response: executive_summary <= 180 words; each plan summary <= 90 words; maximum 4 strengths and 4 considerations per plan; maximum 6 key_differences; each key-difference analysis <= 120 words and client_impact <= 70 words; Ashlar reasoning maximum 5 items; important_considerations maximum 5; next_steps maximum 4.

Return ONLY one valid JSON object with this schema:
{
  "report_title": "",
  "executive_summary": "",
  "client_needs_summary": "",
  "plans": [
    {
      "provider": "",
      "plan_name": "",
      "positioning": "one sentence describing where this plan sits in this comparison",
      "summary": "2-4 client-facing sentences",
      "strengths": ["", ""],
      "considerations": ["", ""],
      "best_suited_when": "",
      "source_notes": [""]
    }
  ],
  "key_differences": [
    {
      "title": "",
      "analysis": "",
      "client_impact": ""
    }
  ],
  "ashlar_assessment": {
    "recommended_provider": "",
    "recommended_plan": "",
    "headline": "",
    "reasoning": ["", "", ""],
    "alternative_provider": "",
    "alternative_plan": "",
    "alternative_reason": "",
    "when_the_alternative_may_be_better": "",
    "extras_provider": "",
    "extras_plan": "",
    "extras_reason": "",
    "budget_provider": "",
    "budget_plan": "",
    "budget_reason": ""
  },
  "important_considerations": [""],
  "next_steps": [""],
  "disclaimer": ""
}

If the evidence is insufficient for a responsible single recommendation, leave recommended_provider/recommended_plan empty and explain in headline/reasoning what must be confirmed first.
"""


def _fallback_analysis(payload: dict, language: str) -> dict:
    greek = language.lower().startswith("el") or language.lower().startswith("gr") or "greek" in language.lower()
    plans = []
    for p in payload.get("plans", []):
        plans.append({
            "provider": p.get("provider") or "",
            "plan_name": p.get("plan_name") or "",
            "positioning": "",
            "summary": "",
            "strengths": [],
            "considerations": ["AI narrative unavailable; review the comparison facts directly." if not greek else "Η αφηγηματική ανάλυση δεν είναι διαθέσιμη· ελέγξτε απευθείας τα συγκριτικά στοιχεία."],
            "best_suited_when": "",
            "source_notes": [],
        })
    return {
        "report_title": "Συγκριτική Ανάλυση Ασφάλισης Υγείας" if greek else "Health Insurance Comparative Analysis",
        "executive_summary": "",
        "client_needs_summary": payload.get("client_priorities") or "",
        "plans": plans,
        "key_differences": [],
        "ashlar_assessment": {
            "recommended_provider": "",
            "recommended_plan": "",
            "headline": "Απαιτείται αξιολόγηση broker." if greek else "Broker assessment required.",
            "reasoning": [],
            "alternative_provider": "",
            "alternative_plan": "",
            "alternative_reason": "",
            "when_the_alternative_may_be_better": "",
        },
        "important_considerations": [],
        "next_steps": [],
        "disclaimer": "Η τελική κάλυψη και αποδοχή υπόκεινται στους όρους και την επιβεβαίωση της ασφαλιστικής." if greek else "Final cover and acceptance remain subject to the insurer's current terms and confirmation.",
    }



_REPORT_REQUIRED_KEYS = (
    "report_title",
    "executive_summary",
    "plans",
    "ashlar_assessment",
    "next_steps",
    "disclaimer",
)


def _recommended_report_max_tokens(plan_count: int) -> int:
    """Output budget sized for the number of compared plans.

    v0.5.0 reduced the legacy report budget from 7,000 to 4,500 tokens. Four-plan
    reports can legitimately exceed that, causing Claude to stop at ``max_tokens``
    and leaving only nested partial JSON objects parseable. Keep one/two-plan jobs
    economical while giving larger comparisons enough room to finish cleanly.
    """
    if plan_count <= 1:
        return 5200
    if plan_count == 2:
        return 6500
    if plan_count == 3:
        return 7800
    return 9200


def _complete_report_object(raw: str) -> dict:
    """Select only a complete top-level ClientReport-like object.

    A truncated outer JSON document may still contain valid nested plan objects.
    ``parse_best_json_object`` can otherwise select one of those nested objects and
    turn a token-limit truncation into a confusing schema error. Here we require
    every structural top-level key before accepting a candidate.
    """
    candidates = parse_json_objects(raw)
    complete = [obj for obj in candidates if all(k in obj for k in _REPORT_REQUIRED_KEYS)]
    if not complete:
        raise ClientReportValidationError(
            "Model response did not contain one complete client-report JSON object."
        )
    return max(
        complete,
        key=lambda obj: (
            sum(1 for k in _REPORT_REQUIRED_KEYS if obj.get(k) not in (None, "", [], {})),
            len(obj),
        ),
    )


def _compact_repair_payload(payload: dict) -> dict:
    """Shrink the repair prompt without removing canonical plan facts."""
    compact = {
        "case_reference": payload.get("case_reference"),
        "client_name": payload.get("client_name"),
        "client_profile": payload.get("client_profile"),
        "client_priorities": payload.get("client_priorities"),
        "client_sex": payload.get("client_sex"),
        "client_age": payload.get("client_age"),
        "maternity_relevant": payload.get("maternity_relevant"),
        "derived_facts": _derived_decision_facts(payload),
        "plans": [],
    }
    for plan in payload.get("plans") or []:
        benefits = plan.get("benefits") or {}
        compact["plans"].append({
            "provider": plan.get("provider"),
            "plan_name": plan.get("plan_name"),
            "premium": plan.get("premium"),
            "annual_limit": plan.get("annual_limit"),
            "deductible_or_excess": plan.get("deductible_or_excess"),
            "area_of_cover": plan.get("area_of_cover"),
            "underwriting": plan.get("underwriting"),
            "benefits": benefits,
            "waiting_periods": (plan.get("waiting_periods") or [])[:12] if isinstance(plan.get("waiting_periods"), list) else plan.get("waiting_periods"),
            "optional_benefits": (plan.get("optional_benefits") or [])[:10] if isinstance(plan.get("optional_benefits"), list) else plan.get("optional_benefits"),
            "critical_limitations": (plan.get("critical_limitations") or [])[:10] if isinstance(plan.get("critical_limitations"), list) else plan.get("critical_limitations"),
            "source_evidence": (plan.get("source_evidence") or [])[:5],
        })
    return compact


def _response_text(response) -> str:
    return "".join(
        block.text for block in response.content
        if getattr(block, "type", None) == "text"
    ).strip()


def _call_report_model(*, client, model: str, prompt: str, max_tokens: int):
    """Call Claude and fail explicitly when the response was token-truncated."""
    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = _response_text(response)
    if getattr(response, "stop_reason", None) == "max_tokens":
        raise ClientReportValidationError(
            f"Client report output reached the {max_tokens}-token limit before completion."
        )
    return raw, response


def _repair_client_report_with_model(
    *,
    client,
    model: str,
    payload: dict,
    language_instruction: str,
    partial_report: dict,
    validation_error: Exception,
    max_tokens: int,
) -> dict:
    """Ask the model once to repair an incomplete report into the exact schema.

    The worker keeps the previous validated report until this repaired object passes
    Pydantic validation, so a failed repair can never replace good client output.
    """
    repair_prompt = f"""You previously returned an incomplete JSON object for an Ashlar client report.
Repair it now. Return ONLY one complete JSON object and nothing else.

{language_instruction}

The object MUST contain ALL of these top-level keys exactly:
report_title, executive_summary, client_needs_summary, plans, key_differences,
ashlar_assessment, important_considerations, next_steps, disclaimer.

Every analyzed plan in GROUNDED CASE PAYLOAD must appear exactly once in plans.
Do not invent facts. Use only the supplied grounded payload.

VALIDATION ERROR TO FIX:
{str(validation_error)}

PARTIAL / WRONG OBJECT RETURNED PREVIOUSLY:
{json.dumps(partial_report, ensure_ascii=False, indent=2, default=str)[:12000]}

GROUNDED CASE PAYLOAD:
{json.dumps(_compact_repair_payload(payload), ensure_ascii=False, indent=2, default=str)}

Required JSON schema shape:
{{
  "report_title": "",
  "executive_summary": "",
  "client_needs_summary": "",
  "plans": [{{
    "provider": "", "plan_name": "", "positioning": "", "summary": "",
    "strengths": [], "considerations": [], "best_suited_when": "", "source_notes": []
  }}],
  "key_differences": [{{"title": "", "analysis": "", "client_impact": ""}}],
  "ashlar_assessment": {{
    "recommended_provider": "", "recommended_plan": "", "headline": "",
    "reasoning": [], "alternative_provider": "", "alternative_plan": "",
    "alternative_reason": "", "when_the_alternative_may_be_better": ""
  }},
  "important_considerations": [],
  "next_steps": [],
  "disclaimer": ""
}}
"""
    raw, _response = _call_report_model(
        client=client,
        model=model,
        prompt=repair_prompt,
        max_tokens=max_tokens,
    )
    return _complete_report_object(raw)



def _clip_words(value: Any, max_words: int) -> str:
    """Compact long extracted clauses without changing their substantive wording."""
    text = re.sub(r"\s+", " ", str(value or "").strip())
    if not text:
        return ""
    words = text.split()
    if len(words) <= max_words:
        return text
    return " ".join(words[:max_words]).rstrip(" ,;:") + "…"


def _usable_fact(value: Any) -> bool:
    text = str(value or "").strip().casefold()
    return bool(text and text not in {"not specified", "not mentioned", "unclear", "—", "-", "none", "null"})


def _plan_narrative_from_verified_facts(plan: dict, *, language: str = "English") -> dict:
    """Build the plan page from verified structured facts, not another LLM pass.

    v0.5.4 deliberately removes four verbose plan narratives from the report-model
    output. The report writer already has canonical plan facts; asking the model to
    rewrite every plan was the main cause of 10k+ token responses.
    """
    greek = str(language or "").lower().startswith(("gr", "el")) or "greek" in str(language or "").lower()
    provider = str(plan.get("provider") or "Provider")
    plan_name = str(plan.get("plan_name") or "Plan")
    premium = premium_display(plan)
    annual = _safe_text(plan.get("annual_limit"))
    deductible = client_facing_deductible(plan.get("deductible_or_excess"))
    area = _safe_text(plan.get("area_of_cover"))
    benefits = plan.get("benefits") or {}

    if greek:
        positioning = f"{plan_name}: ετήσιο όριο {annual}, με quoted premium {premium}."
        summary_bits = [
            f"Περιοχή κάλυψης: {area}.",
            f"Απαλλαγή/excess: {deductible}.",
        ]
        if _usable_fact(benefits.get("inpatient")):
            summary_bits.append("Νοσοκομειακή κάλυψη: " + _clip_words(benefits.get("inpatient"), 28))
        if _usable_fact(benefits.get("outpatient")):
            summary_bits.append("Εξωνοσοκομειακή κάλυψη: " + _clip_words(benefits.get("outpatient"), 30))
    else:
        positioning = f"{plan_name}: {annual} annual policy limit with a quoted premium of {premium}."
        summary_bits = [
            f"Area of cover: {area}.",
            f"Deductible/excess: {deductible}.",
        ]
        if _usable_fact(benefits.get("inpatient")):
            summary_bits.append("In-patient: " + _clip_words(benefits.get("inpatient"), 28))
        if _usable_fact(benefits.get("outpatient")):
            summary_bits.append("Out-patient: " + _clip_words(benefits.get("outpatient"), 30))

    # Strength bullets are factual positive cover features, not a model-created score.
    strengths: list[str] = []
    if _usable_fact(annual):
        strengths.append(("Ετήσιο όριο συμβολαίου: " if greek else "Annual policy limit: ") + annual)
    for key, label_en, label_gr in (
        ("inpatient", "In-patient", "Νοσοκομειακά"),
        ("outpatient", "Out-patient", "Εξωνοσοκομειακά"),
        ("diagnostics_imaging", "Diagnostics / imaging", "Διαγνωστικά / απεικονιστικές"),
        ("evacuation_repatriation", "Evacuation / repatriation", "Αεροδιακομιδή / επαναπατρισμός"),
    ):
        value = benefits.get(key)
        if _usable_fact(value) and not re.search(r"\bnot covered\b|\bexcluded\b", str(value), re.I):
            strengths.append(f"{label_gr if greek else label_en}: {_clip_words(value, 24)}")
        if len(strengths) >= 4:
            break

    considerations: list[str] = []
    # Prefer explicit critical limitations from extraction.
    for item in plan.get("critical_limitations") or []:
        if isinstance(item, dict):
            detail = item.get("detail") or item.get("topic")
        else:
            detail = item
        if _usable_fact(detail):
            considerations.append(_clip_words(detail, 28))
        if len(considerations) >= 4:
            break
    # Then add material negative/limited benefits not already represented.
    if len(considerations) < 4:
        for key in ("outpatient", "mental_health", "dental", "optical", "preventive", "chronic_conditions"):
            value = str(benefits.get(key) or "")
            if not _usable_fact(value):
                continue
            if re.search(r"\bnot covered\b|\bexcluded\b|\blimited\b|waiting|\bcap(?:ped)?\b|sub[- ]?limit", value, re.I):
                bullet = _clip_words(value, 28)
                if bullet and bullet not in considerations:
                    considerations.append(bullet)
            if len(considerations) >= 4:
                break

    return {
        "provider": provider,
        "plan_name": plan_name,
        "positioning": _clip_words(positioning, 32),
        "summary": _clip_words(" ".join(summary_bits), 90),
        "strengths": strengths[:4],
        "considerations": considerations[:4],
        "best_suited_when": "",
        "source_notes": [],
    }


def _plan_identity(plan: dict) -> str:
    return f"{str(plan.get('provider') or '').strip()} - {str(plan.get('plan_name') or '').strip()}".strip(" -")


def _number_from_text(value: Any) -> float | None:
    text = str(value or "")
    # keep the first plausible money/limit number; separators may be commas or spaces
    m = re.search(r"(?<!\d)(\d{1,3}(?:[ ,.']\d{3})+(?:[.,]\d+)?|\d+(?:[.,]\d+)?)", text)
    if not m:
        return None
    raw = m.group(1).replace(" ", "").replace("'", "")
    # Thousands commas are much more common in the extracted IPMI limits/premiums.
    if raw.count(',') and raw.count('.') == 0:
        bits = raw.split(',')
        if len(bits[-1]) == 3:
            raw = ''.join(bits)
        else:
            raw = raw.replace(',', '.')
    elif raw.count(',') and raw.count('.'):
        raw = raw.replace(',', '')
    try:
        return float(raw)
    except ValueError:
        return None


def _premium_value(plan: dict) -> tuple[str, float] | None:
    premium = plan.get("premium") or {}
    if not isinstance(premium, dict):
        return None
    amount = _number_from_text(premium.get("amount"))
    currency = str(premium.get("currency") or "").strip().upper()
    if amount is None or not currency:
        return None
    return currency, amount


def _derived_decision_facts(payload: dict) -> dict:
    """Deterministic comparison facts supplied to the adviser model.

    These facts prevent simple superlative errors such as calling Bupa the highest
    premium when Cigna is actually the most expensive quote. Premium ranking is only
    produced when all comparable quotes use the same currency.
    """
    plans = payload.get("plans") or []
    out: dict[str, Any] = {}
    premium_rows=[]
    for plan in plans:
        pv=_premium_value(plan)
        if pv:
            premium_rows.append((plan, pv[0], pv[1]))
    currencies={r[1] for r in premium_rows}
    if len(premium_rows) == len(plans) and len(currencies)==1 and premium_rows:
        ordered=sorted(premium_rows, key=lambda r:r[2])
        out["premium_currency"] = ordered[0][1]
        out["lowest_premium"] = {"plan":_plan_identity(ordered[0][0]), "amount":ordered[0][2]}
        out["highest_premium"] = {"plan":_plan_identity(ordered[-1][0]), "amount":ordered[-1][2]}
        out["premium_order_low_to_high"] = [_plan_identity(r[0]) for r in ordered]

    limit_rows=[]
    for plan in plans:
        value=_number_from_text(plan.get("annual_limit"))
        if value is not None:
            limit_rows.append((plan,value))
    if len(limit_rows)==len(plans) and limit_rows:
        ordered=sorted(limit_rows, key=lambda r:r[1])
        out["highest_stated_annual_limit"]={"plan":_plan_identity(ordered[-1][0]), "amount":ordered[-1][1]}
        out["lowest_stated_annual_limit"]={"plan":_plan_identity(ordered[0][0]), "amount":ordered[0][1]}
    return out


def _benefit_topic_words(text: str) -> set[str]:
    key=str(text or '').casefold()
    groups={
        'dental': ('dental','orthodont','tooth','teeth','implant'),
        'surgery': ('surgery','surgical','operation','elective'),
        'maternity': ('maternity','pregnan','childbirth','newborn'),
        'wellness': ('wellness','well-being','health screening','preventive','vaccination'),
        'mental': ('mental','psychiatr','psycholog'),
        'imaging': ('mri','ct','pet','imaging','scan'),
        'chronic': ('chronic','routine management'),
    }
    found=set()
    for label, toks in groups.items():
        if any(tok in key for tok in toks):
            found.add(label)
    return found


def _waiting_period_claim_supported(text: str, results: list[dict]) -> bool:
    """Reject a waiting-period statement if month + benefit topic are not grounded.

    This prevents cross-benefit leakage such as turning a 9-month dental waiting
    period into a waiting period for elective surgery.
    """
    raw=str(text or '')
    months={int(x) for x in re.findall(r"(\d{1,2})[- ]?month", raw, flags=re.I)}
    if not months:
        return True
    claim_topics=_benefit_topic_words(raw)
    candidates=[]
    for result in results or []:
        analysis=result.get('analysis') or {}
        for item in analysis.get('waiting_periods') or []:
            if isinstance(item, dict):
                candidates.append(str(item.get('detail') or item.get('topic') or ''))
            else:
                candidates.append(str(item or ''))
        for item in analysis.get('critical_limitations') or []:
            if isinstance(item, dict):
                candidates.append(str(item.get('detail') or item.get('topic') or ''))
            else:
                candidates.append(str(item or ''))
        for benefit_key, value in (analysis.get('benefits') or {}).items():
            candidates.append(f"{benefit_key}: {value or ''}")
    for candidate in candidates:
        cand_months={int(x) for x in re.findall(r"(\d{1,2})[- ]?month", candidate, flags=re.I)}
        if not months.intersection(cand_months):
            continue
        cand_topics=_benefit_topic_words(candidate)
        if not claim_topics or not cand_topics or claim_topics.intersection(cand_topics):
            return True
    return False


def _sanitize_advisory_superlatives(report: dict, results: list[dict]) -> None:
    """Keep premium superlatives deterministic even when prose generation slips."""
    payload={"plans":[]}
    for result in results or []:
        a=result.get('analysis') or {}
        payload['plans'].append({
            'provider':a.get('provider') or result.get('provider'),
            'plan_name':a.get('plan_name') or result.get('target_plan'),
            'premium':a.get('premium'),
            'annual_limit':a.get('annual_limit'),
        })
    facts=_derived_decision_facts(payload)
    highest=str((facts.get('highest_premium') or {}).get('plan') or '').casefold()
    if not highest:
        return
    def clean(text: Any) -> str:
        raw=str(text or '')
        # A bare/highly localised "highest premium" claim can be wrong after model synthesis.
        # Keep the comparison directional unless the same text clearly names the true highest plan.
        if re.search(r"\bhighest (?:quoted |total )?premium\b", raw, re.I) and not any(tok in raw.casefold() for tok in highest.split() if len(tok)>3):
            raw=re.sub(r"\b(?:the )?highest (?:quoted |total )?premium\b", "a higher premium", raw, flags=re.I)
        return raw
    report['executive_summary']=clean(report.get('executive_summary'))
    ass=report.get('ashlar_assessment') or {}
    ass['headline']=clean(ass.get('headline'))
    ass['reasoning']=[clean(x) for x in ass.get('reasoning') or []]
    ass['alternative_reason']=clean(ass.get('alternative_reason'))
    ass['when_the_alternative_may_be_better']=clean(ass.get('when_the_alternative_may_be_better'))
    ass['extras_reason']=clean(ass.get('extras_reason'))
    ass['budget_reason']=clean(ass.get('budget_reason'))
    for d in report.get('key_differences') or []:
        d['analysis']=clean(d.get('analysis'))
        d['client_impact']=clean(d.get('client_impact'))


def _compact_decision_payload(payload: dict) -> dict:
    """Small, decision-focused payload for the only LLM synthesis call."""
    out = {
        "case_reference": payload.get("case_reference"),
        "client_name": payload.get("client_name"),
        "client_profile": _clip_words(payload.get("client_profile"), 80),
        "client_priorities": _clip_words(payload.get("client_priorities"), 80),
        "client_sex": payload.get("client_sex"),
        "client_age": payload.get("client_age"),
        "maternity_relevant": payload.get("maternity_relevant"),
        "derived_facts": _derived_decision_facts(payload),
        "plans": [],
    }
    for plan in payload.get("plans") or []:
        benefits = plan.get("benefits") or {}
        out["plans"].append({
            "provider": plan.get("provider"),
            "plan_name": plan.get("plan_name"),
            "premium": plan.get("premium"),
            "annual_limit": plan.get("annual_limit"),
            "deductible_or_excess": client_facing_deductible(plan.get("deductible_or_excess")),
            "area_of_cover": plan.get("area_of_cover"),
            "underwriting": plan.get("underwriting"),
            "benefits": {
                key: _clip_words(benefits.get(key), 34)
                for key in (
                    "inpatient", "outpatient", "cancer", "chronic_conditions",
                    "mental_health", "dental", "optical", "diagnostics_imaging",
                    "preventive", "evacuation_repatriation"
                )
                if _usable_fact(benefits.get(key))
            },
            "waiting_periods": [
                _clip_words(x.get("detail") if isinstance(x, dict) else x, 22)
                for x in (plan.get("waiting_periods") or [])[:5]
            ],
            "critical_limitations": [
                _clip_words((x.get("detail") or x.get("topic")) if isinstance(x, dict) else x, 26)
                for x in (plan.get("critical_limitations") or [])[:5]
            ],
        })
    return out


_SYNTHESIS_REQUIRED_KEYS = (
    "executive_summary", "client_needs_summary", "key_differences",
    "ashlar_assessment", "important_considerations",
)


def _complete_synthesis_object(raw: str) -> dict:
    candidates = parse_json_objects(raw)
    complete = [obj for obj in candidates if all(k in obj for k in _SYNTHESIS_REQUIRED_KEYS)]
    if not complete:
        raise ClientReportValidationError("Model response did not contain one complete decision-synthesis JSON object.")
    return max(complete, key=lambda obj: (sum(bool(obj.get(k)) for k in _SYNTHESIS_REQUIRED_KEYS), len(obj)))


MODULAR_SYNTHESIS_PROMPT = """You are the senior advisory-writing engine inside Ashlar Proposal Studio.
You are NOT writing the whole report. Verified plan pages, comparison matrix, underwriting workflow, next steps and disclaimer are built deterministically elsewhere.

Your task is ONLY to write the compact decision synthesis from the supplied verified case facts:
1) executive_summary (max 130 words)
2) client_needs_summary (max 55 words)
3) up to 4 key_differences; each analysis max 85 words and client_impact max 45 words
4) ashlar_assessment with max 4 reasoning bullets
5) up to 5 client-friendly important_considerations

Non-negotiable rules:
- Use ONLY supplied case facts. Do not add product knowledge.
- Compare the FINAL QUOTED CONFIGURATION. A selected optional module is not inferior merely because another insurer bundles the same benefit in its base plan.
- Ashlar is acting as the client's broker-adviser, not merely a comparison engine. When the verified facts and stated priorities are sufficient, GIVE ONE CLEAR PRIMARY RECOMMENDATION. Do not hide behind "no single plan wins".
- Leave recommended_provider/recommended_plan empty only when a material fact needed for the decision is genuinely missing; explain that blocker explicitly.
- The recommendation must explain why the chosen plan fits THIS client better than the strongest competing option, and must address material competing advantages such as lower premium, higher annual limit, higher outpatient limit, diagnostics, waiting periods or fewer sub-limits.
- Also identify: (a) the strongest alternative, (b) the broader-extras option when relevant, and (c) the budget option when relevant. These are not rankings; they are practical routes for different priorities.
- Applicant relevance is mandatory. Maternity/pregnancy/newborn may be discussed only for a female applicant.
- Do not create a cost-sharing comparison when core quoted cover has no non-zero cost share.
- MRI/CT/PET belong to diagnostics/imaging, never wellness.
- Do not imply broker work is incomplete. Important considerations are client usage/benefit issues only.
- Never infer health status from age.
- Do not invent visit counts, healthcare costs, probabilities or claims assumptions.
- Treat derived_facts as deterministic truth for premium/annual-limit superlatives. Never contradict them.
- Never attach a waiting period to a different benefit. A waiting period may be mentioned only for the same benefit/category evidenced in the payload.
- Keep wording concise enough for client PDF/PPTX cards.

Return ONLY this JSON shape:
{
  "executive_summary": "",
  "client_needs_summary": "",
  "key_differences": [
    {"title": "", "analysis": "", "client_impact": ""}
  ],
  "ashlar_assessment": {
    "recommended_provider": "",
    "recommended_plan": "",
    "headline": "",
    "reasoning": [""],
    "alternative_provider": "",
    "alternative_plan": "",
    "alternative_reason": "",
    "when_the_alternative_may_be_better": "",
    "extras_provider": "",
    "extras_plan": "",
    "extras_reason": "",
    "budget_provider": "",
    "budget_plan": "",
    "budget_reason": ""
  },
  "important_considerations": [""]
}
"""


def _deterministic_title(payload: dict, *, language: str) -> str:
    name = str(payload.get("client_name") or payload.get("case_reference") or "Client").strip()
    greek = str(language or "").lower().startswith(("gr", "el")) or "greek" in str(language or "").lower()
    if len(payload.get("plans") or []) <= 1:
        return f"Ανάλυση Ασφάλισης Υγείας για {name}" if greek else f"Health Insurance Analysis for {name}"
    return f"Σύγκριση Ασφάλισης Υγείας για {name}" if greek else f"Health Insurance Comparison for {name}"


def _deterministic_disclaimer(*, language: str) -> str:
    greek = str(language or "").lower().startswith(("gr", "el")) or "greek" in str(language or "").lower()
    if greek:
        return (
            "Η παρούσα ανάλυση έχει συνταχθεί για να υποστηρίξει την κατανόηση και σύγκριση των ασφαλιστικών επιλογών. "
            "Η τελική αποδοχή, οι εξατομικευμένοι όροι, οι εξαιρέσεις, το ασφάλιστρο και η κάλυψη διέπονται από την τελική αξιολόγηση και τα επίσημα έγγραφα της ασφαλιστικής."
        )
    return (
        "This analysis is intended to support understanding and comparison of the insurance options presented. "
        "Final acceptance, applicant-specific terms, exclusions, premium and cover remain subject to the insurer's final underwriting decision and governing policy documents."
    )


def _assemble_modular_report(*, payload: dict, synthesis: dict, language: str) -> dict:
    plans = [_plan_narrative_from_verified_facts(p, language=language) for p in payload.get("plans") or []]
    report = {
        "report_title": _deterministic_title(payload, language=language),
        "executive_summary": _clip_words(synthesis.get("executive_summary"), 130),
        "client_needs_summary": _clip_words(synthesis.get("client_needs_summary"), 55),
        "plans": plans,
        "key_differences": [],
        "ashlar_assessment": synthesis.get("ashlar_assessment") or {},
        "important_considerations": [
            _clip_words(x, 34) for x in (synthesis.get("important_considerations") or [])[:5] if str(x or "").strip()
        ],
        "next_steps": ["Proceed to the appropriate underwriting workflow."],
        "disclaimer": _deterministic_disclaimer(language=language),
    }
    for item in (synthesis.get("key_differences") or [])[:4]:
        if not isinstance(item, dict) or not str(item.get("title") or "").strip():
            continue
        report["key_differences"].append({
            "title": _clip_words(item.get("title"), 14),
            "analysis": _clip_words(item.get("analysis"), 85),
            "client_impact": _clip_words(item.get("client_impact"), 45),
        })
    return report


def generate_client_analysis(
    *,
    case_reference: str,
    client_name: str,
    client_profile: str,
    client_priorities: str,
    client_sex: str = "",
    client_age: int | None = None,
    results: list[dict] = None,
    language: str = "English",
    strict: bool = False,
) -> dict:
    """v0.5.4 modular report generator.

    Only the concise decision synthesis is generated by the LLM. Plan pages, matrix,
    underwriting workflow, next steps and disclaimer are assembled from verified case
    data. This keeps four-plan output well below model output limits.
    """
    results = results or []
    payload = build_grounded_case_payload(
        case_reference=case_reference,
        client_name=client_name,
        client_profile=client_profile,
        client_priorities=client_priorities,
        client_sex=client_sex,
        client_age=client_age,
        results=results,
    )
    api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        if strict:
            raise ClientReportValidationError("ANTHROPIC_API_KEY is not configured for client report generation.")
        out = _fallback_analysis(payload, language)
        out["comparison_matrix"] = payload["comparison_matrix"]
        out["client_name"] = payload["client_name"]
        out["case_reference"] = payload["case_reference"]
        return apply_client_report_rules(
            out, results=results, client_sex=client_sex, client_age=client_age,
            client_priorities=client_priorities, language=language
        )

    model = os.getenv("CLIENT_ANALYSIS_MODEL", os.getenv("CLAUDE_MODEL", "claude-sonnet-5"))
    language_instruction = (
        "Write every client-facing field in Greek. Keep provider/product names and standard insurance acronyms as stated in source evidence."
        if language.lower().startswith(("gr", "el")) or "greek" in language.lower()
        else "Write every client-facing field in professional English."
    )
    decision_payload = _compact_decision_payload(payload)
    prompt = f"""{MODULAR_SYNTHESIS_PROMPT}\nLANGUAGE REQUIREMENT:\n{language_instruction}\n\nVERIFIED DECISION PAYLOAD:\n{json.dumps(decision_payload, ensure_ascii=False, indent=2, default=str)}"""

    import anthropic
    timeout_seconds = float(os.getenv("CLIENT_ANALYSIS_TIMEOUT_SECONDS", "120"))
    configured_budget = os.getenv("CLIENT_ANALYSIS_MAX_TOKENS", "").strip()
    # A modular synthesis should fit comfortably below this ceiling. A legacy env var
    # may be larger; cap it to prevent another 10k-token monolithic response.
    max_tokens = int(configured_budget) if configured_budget else 3600
    max_tokens = min(max(max_tokens, 2600), 4800)
    try:
        client = anthropic.Anthropic(api_key=api_key, timeout=timeout_seconds)
        try:
            response = client.messages.create(
                model=model,
                max_tokens=max_tokens,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = _response_text(response)
            if getattr(response, "stop_reason", None) == "max_tokens":
                raise ClientReportValidationError(
                    f"Decision synthesis reached the {max_tokens}-token limit before completion."
                )
            synthesis = _complete_synthesis_object(raw)
        except ClientReportValidationError:
            retry_prompt = prompt + "\n\nRETRY: Be substantially more concise. Return the complete JSON object only; maximum 4 key differences and 4 assessment bullets."
            response = client.messages.create(
                model=model,
                max_tokens=4800,
                messages=[{"role": "user", "content": retry_prompt}],
            )
            raw = _response_text(response)
            if getattr(response, "stop_reason", None) == "max_tokens":
                raise ClientReportValidationError("Decision synthesis was still incomplete after one concise retry.")
            synthesis = _complete_synthesis_object(raw)
        out = _assemble_modular_report(payload=payload, synthesis=synthesis, language=language)
    except (json.JSONDecodeError, anthropic.APIError, anthropic.APIConnectionError) as exc:
        if strict:
            raise ClientReportValidationError(f"Client decision synthesis failed: {exc}") from exc
        out = _fallback_analysis(payload, language)
        out["generation_warning"] = f"Client decision synthesis failed: {exc}"
        out["raw_response_excerpt"] = locals().get("raw", "")[:1800]

    out["comparison_matrix"] = payload["comparison_matrix"]
    out["client_name"] = payload["client_name"]
    out["case_reference"] = payload["case_reference"]
    out["client_profile"] = payload["client_profile"]
    out["client_priorities"] = payload["client_priorities"]
    out = apply_client_report_rules(
        out,
        results=results,
        client_sex=client_sex,
        client_age=client_age,
        client_priorities=client_priorities,
        language=language,
    )
    if strict:
        validate_client_report(out, results)
    return out
