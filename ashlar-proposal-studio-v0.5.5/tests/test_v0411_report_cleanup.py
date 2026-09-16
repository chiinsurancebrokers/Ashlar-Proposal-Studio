import fitz

from core.client_analysis import (
    build_comparison_matrix,
    client_facing_pre_existing_conditions,
    find_plan_narrative,
    apply_client_report_rules,
)
from core.report_pdf import build_pdf_bytes


def _fmu_result(provider="CIGNA SILVER", plan="SILVER", pre="Not specified"):
    return {
        "provider": provider,
        "target_plan": plan,
        "analysis": {
            "provider": provider,
            "plan_name": plan,
            "premium": {"amount": "1000", "currency": "EUR", "frequency": "Annual"},
            "annual_limit": "€1,000,000",
            "deductible_or_excess": "€0 deductible",
            "area_of_cover": "Worldwide excluding USA",
            "underwriting": {"basis": "Full Medical Underwriting", "pre_existing_conditions": pre},
            "benefits": {"inpatient": "Covered", "outpatient": "Covered"},
        },
    }


def test_fmu_preexisting_wording_is_standardised_across_plans():
    results = [
        _fmu_result("Bupa Global", "SELECT", "Covered depending on underwriting"),
        _fmu_result("CIGNA", "Silver", "Not specified"),
        _fmu_result("IMG", "Silver", "Not specified"),
        _fmu_result("Now Health", "SimpleCare 250", "Excluded unless agreed in writing"),
    ]
    matrix = build_comparison_matrix(results)
    row = next(r for r in matrix if r["topic"] == "Pre-existing conditions")
    assert len(set(row["values"].values())) == 1
    only = next(iter(row["values"].values()))
    assert "underwriting approval" in only.lower()
    assert "unless specifically accepted" in only.lower()


def test_non_fmu_keeps_specific_preexisting_terms():
    a = _fmu_result()["analysis"]
    a["underwriting"] = {"basis": "CPME", "pre_existing_conditions": "Subject to CPME terms"}
    assert client_facing_pre_existing_conditions(a) == "Subject to CPME terms"


def test_narrative_matches_provider_label_that_contains_plan_name():
    plans = [{"provider": "CIGNA", "plan_name": "Silver", "summary": "Narrative found"}]
    result = _fmu_result("CIGNA SILVER", "SILVER")
    assert find_plan_narrative(plans, result)["summary"] == "Narrative found"


def test_age_health_inference_is_removed():
    report = {
        "executive_summary": "At age 17, he is unlikely to have significant pre-existing conditions. Strong outpatient cover.",
        "client_needs_summary": "At 17, he is unlikely to have significant pre-existing conditions, making underwriting manageable. He needs broad cover.",
        "plans": [], "key_differences": [],
        "ashlar_assessment": {"headline": "", "reasoning": ["For Ioannis's age and likely health profile, this is adequate."], "alternative_reason": "", "when_the_alternative_may_be_better": ""},
        "important_considerations": [], "next_steps": [],
    }
    out = apply_client_report_rules(report, results=[_fmu_result()], client_sex="Male", client_age=17)
    assert "unlikely to have" not in out["executive_summary"].lower()
    assert "unlikely to have" not in out["client_needs_summary"].lower()
    assert not out["ashlar_assessment"]["reasoning"]


def test_pdf_cover_does_not_repeat_executive_summary():
    results = [_fmu_result("CIGNA", "Silver")]
    matrix = build_comparison_matrix(results)
    analysis = {
        "report_title": "Comparative Health Insurance Analysis",
        "client_name": "Ioannis",
        "client_needs_summary": "Needs inpatient and outpatient cover.",
        "client_profile": "Student in Germany.",
        "executive_summary": "UNIQUE EXECUTIVE SUMMARY SENTENCE.",
        "plans": [{"provider": "CIGNA", "plan_name": "Silver", "summary": "Plan summary", "strengths": [], "considerations": []}],
        "comparison_matrix": matrix,
        "key_differences": [],
        "ashlar_assessment": {"recommended_provider": "", "recommended_plan": "", "headline": "", "reasoning": [], "alternative_provider": "", "alternative_plan": "", "alternative_reason": "", "when_the_alternative_may_be_better": ""},
        "important_considerations": [], "next_steps": [], "disclaimer": "Notice",
    }
    pdf = build_pdf_bytes(client_analysis=analysis, results=results)
    doc = fitz.open(stream=pdf, filetype="pdf")
    assert "UNIQUE EXECUTIVE SUMMARY SENTENCE" not in doc[0].get_text()
    assert "UNIQUE EXECUTIVE SUMMARY SENTENCE" in doc[1].get_text()
