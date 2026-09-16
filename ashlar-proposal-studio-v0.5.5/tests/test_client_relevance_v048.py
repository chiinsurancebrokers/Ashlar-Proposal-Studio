from core.client_analysis import (
    apply_client_report_rules,
    build_comparison_matrix,
    client_facing_deductible,
    maternity_relevant,
)
from core.analyzer import _apply_deterministic_facts


def _results():
    return [
        {
            "provider": "CIGNA",
            "target_plan": "Silver",
            "analysis": {
                "provider": "CIGNA",
                "plan_name": "Silver",
                "premium": {"amount": "2389.83", "currency": "EUR", "frequency": "Annual"},
                "annual_limit": "€800,000",
                "deductible_or_excess": "€0 deductible; 0% cost share; €0 out-of-pocket maximum",
                "area_of_cover": "Worldwide excluding USA",
                "underwriting": {"basis": "Full Medical Underwriting"},
                "benefits": {
                    "inpatient": "Covered",
                    "outpatient": "€12,000",
                    "maternity": "Routine maternity with 12-month waiting period",
                    "preventive": "Routine physical examination and screenings",
                    "diagnostics_imaging": "Advanced Medical Imaging €7,400",
                },
            },
        },
        {
            "provider": "IMG",
            "target_plan": "Silver",
            "analysis": {
                "provider": "IMG",
                "plan_name": "Silver",
                "premium": {"amount": "1792.88", "currency": "EUR", "frequency": "Annual"},
                "annual_limit": "€3,000,000",
                "deductible_or_excess": "€0 deductible/excess",
                "area_of_cover": "Worldwide excluding USA",
                "underwriting": {"basis": "Full Medical Underwriting"},
                "benefits": {
                    "inpatient": "Covered",
                    "outpatient": "€10,000",
                    "maternity": "Optional",
                    "preventive": "Well-being benefit €250",
                    "diagnostics_imaging": "CT/PET/MRI covered; outpatient diagnostics within overall outpatient limit",
                },
            },
        },
    ]


def test_maternity_is_only_client_facing_for_female_applicant():
    assert not maternity_relevant(client_sex="Male")
    assert not maternity_relevant(client_sex="Not specified")
    assert maternity_relevant(client_sex="Female")


def test_zero_cost_share_is_removed_from_client_facing_deductible():
    assert client_facing_deductible("€0 deductible; 0% cost share; €0 out-of-pocket maximum") == "€0 deductible"


def test_male_matrix_omits_maternity_and_keeps_imaging_separate():
    matrix = build_comparison_matrix(_results(), client_sex="Male", client_age=17)
    topics = [r["topic"] for r in matrix]
    assert "Maternity" not in topics
    assert "Diagnostics / advanced imaging" in topics
    assert "Preventive / wellness" in topics
    ded = next(r for r in matrix if r["topic"] == "Deductible / excess")
    assert ded["values"]["CIGNA - Silver"] == "€0 deductible"


def test_postprocessor_removes_irrelevant_and_internal_narrative():
    report = {
        "executive_summary": "Strong outpatient. Maternity is included with a waiting period.",
        "client_needs_summary": "Student wants inpatient and outpatient.",
        "plans": [
            {
                "provider": "CIGNA",
                "plan_name": "Silver",
                "summary": "Zero cost-sharing and good cover. Maternity is included.",
                "strengths": ["Zero cost-sharing across all selected modules", "Strong outpatient"],
                "considerations": ["Maternity has a 12-month waiting period", "Dental has a 12-month waiting period"],
            }
        ],
        "key_differences": [
            {"title": "Maternity and Newborn Coverage", "analysis": "Different maternity terms", "client_impact": "Not relevant"},
            {"title": "Cost-Sharing and Out-of-Pocket Friction", "analysis": "Both are zero", "client_impact": "None"},
            {"title": "Advanced imaging", "analysis": "MRI/CT/PET terms differ", "client_impact": "Relevant diagnostics"},
        ],
        "ashlar_assessment": {
            "headline": "CIGNA is a close fit.",
            "reasoning": ["Strong outpatient", "Maternity is stronger"],
            "alternative_reason": "IMG maternity is optional.",
            "when_the_alternative_may_be_better": "If maternity is not needed.",
        },
        "important_considerations": [
            "The broker must clarify CIGNA's underwriting basis.",
            "Dental major restorative treatment has a 12-month waiting period.",
            "Maternity has a 12-month waiting period.",
            "The student should verify visa type and residency status.",
        ],
        "next_steps": [
            "Request a copy of the full policy wording.",
            "Review the dental waiting period if dental treatment is expected.",
        ],
    }
    out = apply_client_report_rules(report, results=_results(), client_sex="Male", client_age=17)
    titles = [d["title"] for d in out["key_differences"]]
    assert "Maternity and Newborn Coverage" not in titles
    assert "Cost-Sharing and Out-of-Pocket Friction" not in titles
    assert "Advanced imaging" in titles
    assert all("maternity" not in x.lower() for x in out["important_considerations"])
    assert all("broker must" not in x.lower() for x in out["important_considerations"])
    # v0.5.5 rejects a waiting-period claim if the same benefit/category is not grounded.
    assert out["important_considerations"] == []


def test_img_diagnostic_imaging_is_locked_separately_from_wellbeing():
    result = {
        "provider": "IMG",
        "plan_name": "Silver",
        "premium": {"amount": "1792.88", "currency": "EUR", "frequency": "Annual"},
        "benefits": {"diagnostics_imaging": "Not mentioned", "preventive": "Well-being benefit €250"},
    }
    focused = """[Page 4] Diagnostics - For example CT, PET and MRI => Covered (table checkmark)\n[Page 6] Diagnostic => Within overall out-patient limit\n"""
    out = _apply_deterministic_facts(result, "IMG", "Worldwide excluding USA", focused)
    assert "CT/PET/MRI" in out["benefits"]["diagnostics_imaging"]
    assert "outpatient" in out["benefits"]["diagnostics_imaging"].lower()
    assert out["benefits"]["preventive"] == "Well-being benefit €250"


def test_fmu_next_steps_are_deterministic_and_start_with_application_medical_history():
    report = {
        "executive_summary": "",
        "client_needs_summary": "",
        "plans": [],
        "key_differences": [],
        "ashlar_assessment": {
            "recommended_provider": "CIGNA",
            "recommended_plan": "Silver",
            "headline": "",
            "reasoning": [],
            "alternative_provider": "",
            "alternative_plan": "",
            "alternative_reason": "",
            "when_the_alternative_may_be_better": "",
        },
        "important_considerations": [],
        "next_steps": ["Generic AI step that should be replaced."],
    }
    out = apply_client_report_rules(
        report,
        results=_results(),
        client_sex="Male",
        client_age=17,
        language="English",
    )
    assert len(out["next_steps"]) == 4
    assert "application" in out["next_steps"][0].lower()
    assert "medical history" in out["next_steps"][0].lower()
    assert "full medical underwriting" in out["next_steps"][1].lower()
    assert "final underwriting terms" in out["next_steps"][2].lower()
    assert "activate the policy" in out["next_steps"][3].lower()


def test_fmu_next_steps_support_greek_output():
    report = {
        "executive_summary": "",
        "client_needs_summary": "",
        "plans": [],
        "key_differences": [],
        "ashlar_assessment": {
            "recommended_provider": "IMG",
            "recommended_plan": "Silver",
            "headline": "",
            "reasoning": [],
            "alternative_provider": "",
            "alternative_plan": "",
            "alternative_reason": "",
            "when_the_alternative_may_be_better": "",
        },
        "important_considerations": [],
        "next_steps": [],
    }
    out = apply_client_report_rules(
        report,
        results=_results(),
        client_sex="Male",
        client_age=17,
        language="Greek",
    )
    assert "ιατρικού ιστορικού" in out["next_steps"][0].lower()
    assert "full medical underwriting" in out["next_steps"][1].lower()
