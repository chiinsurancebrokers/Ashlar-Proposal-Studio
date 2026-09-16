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
    report["important_considerations"] = considerations

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
    "when_the_alternative_may_be_better": ""
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
    payload = build_grounded_case_payload(
        case_reference=case_reference,
        client_name=client_name,
        client_profile=client_profile,
        client_priorities=client_priorities,
        client_sex=client_sex,
        client_age=client_age,
        results=results or [],
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
            out, results=results or [], client_sex=client_sex, client_age=client_age, client_priorities=client_priorities, language=language
        )

    model = os.getenv("CLIENT_ANALYSIS_MODEL", os.getenv("CLAUDE_MODEL", "claude-sonnet-5"))
    language_instruction = (
        "Write every client-facing field in Greek. Keep provider/product names and standard insurance acronyms as stated in source evidence."
        if language.lower().startswith(("gr", "el")) or "greek" in language.lower()
        else "Write every client-facing field in professional English."
    )
    user_prompt = f"""{CLIENT_ANALYSIS_PROMPT}

LANGUAGE REQUIREMENT:
{language_instruction}

=== GROUNDED CASE PAYLOAD ===
{json.dumps(payload, ensure_ascii=False, indent=2, default=str)}
"""
    import anthropic
    timeout_seconds = float(os.getenv("CLIENT_ANALYSIS_TIMEOUT_SECONDS", "120"))
    configured_budget = os.getenv("CLIENT_ANALYSIS_MAX_TOKENS", "").strip()
    max_tokens = int(configured_budget) if configured_budget else _recommended_report_max_tokens(len(results or []))
    try:
        client = anthropic.Anthropic(api_key=api_key, timeout=timeout_seconds)
        try:
            raw, response = _call_report_model(
                client=client,
                model=model,
                prompt=user_prompt,
                max_tokens=max_tokens,
            )
            out = _complete_report_object(raw)
        except ClientReportValidationError as first_generation_error:
            # A four-plan report can exceed a small configured output budget. Retry
            # once with a larger ceiling before invoking schema repair.
            retry_tokens = max(max_tokens + 2500, _recommended_report_max_tokens(len(results or [])))
            retry_tokens = min(retry_tokens, 12000)
            retry_prompt = user_prompt + "\n\nIMPORTANT RETRY: Return the complete JSON object in a concise form. Do not omit any required section or analyzed plan."
            raw, response = _call_report_model(
                client=client,
                model=model,
                prompt=retry_prompt,
                max_tokens=retry_tokens,
            )
            out = _complete_report_object(raw)
            max_tokens = retry_tokens
    except (json.JSONDecodeError, anthropic.APIError, anthropic.APIConnectionError) as exc:
        if strict:
            raise ClientReportValidationError(f"Client narrative generation failed: {exc}") from exc
        out = _fallback_analysis(payload, language)
        out["generation_warning"] = f"Client narrative generation failed: {exc}"
        out["raw_response_excerpt"] = locals().get("raw", "")[:1800]

    out["comparison_matrix"] = payload["comparison_matrix"]
    out["client_name"] = payload["client_name"]
    out["case_reference"] = payload["case_reference"]
    out["client_profile"] = payload["client_profile"]
    out["client_priorities"] = payload["client_priorities"]
    out = apply_client_report_rules(
        out,
        results=results or [],
        client_sex=client_sex,
        client_age=client_age,
        client_priorities=client_priorities,
        language=language,
    )
    if strict:
        try:
            validate_client_report(out, results or [])
        except ClientReportValidationError as first_error:
            # One automatic repair attempt. This specifically handles cases where the
            # model emitted a valid but partial/wrong JSON object.
            try:
                repaired = _repair_client_report_with_model(
                    client=client,
                    model=model,
                    payload=payload,
                    language_instruction=language_instruction,
                    partial_report=out,
                    validation_error=first_error,
                    max_tokens=max(max_tokens, 9000),
                )
                repaired["comparison_matrix"] = payload["comparison_matrix"]
                repaired["client_name"] = payload["client_name"]
                repaired["case_reference"] = payload["case_reference"]
                repaired["client_profile"] = payload["client_profile"]
                repaired["client_priorities"] = payload["client_priorities"]
                repaired = apply_client_report_rules(
                    repaired,
                    results=results or [],
                    client_sex=client_sex,
                    client_age=client_age,
                    client_priorities=client_priorities,
                    language=language,
                )
                validate_client_report(repaired, results or [])
                out = repaired
            except Exception as repair_error:
                raise ClientReportValidationError(
                    "The client report returned an incomplete structure after an automatic retry. "
                    "The previous validated report has been preserved. Please generate the report again."
                ) from repair_error
    return out
