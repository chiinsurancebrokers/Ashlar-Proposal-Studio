from core.client_analysis import build_comparison_matrix
from core.presentation import build_pptx_bytes
from core.report_pdf import build_pdf_bytes


def sample_results():
    return [
        {
            "provider": "IMG",
            "target_plan": "Silver",
            "analysis": {
                "provider": "IMG",
                "plan_name": "Silver",
                "premium": {"amount": "2400", "currency": "EUR", "frequency": "annual"},
                "annual_limit": "EUR 3,000,000",
                "deductible_or_excess": "EUR 500",
                "area_of_cover": "Worldwide excluding USA",
                "underwriting": {"basis": "FMU", "pre_existing_conditions": "Subject to underwriting"},
                "benefits": {"inpatient": "Covered", "outpatient": "EUR 10,000", "cancer": "Within overall policy limit"},
            },
        },
        {
            "provider": "Cigna",
            "target_plan": "Silver",
            "analysis": {
                "provider": "Cigna",
                "plan_name": "Silver",
                "premium": {"amount": "2389.83", "currency": "EUR", "frequency": "annual"},
                "annual_limit": "EUR 800,000",
                "deductible_or_excess": "EUR 0",
                "area_of_cover": "Worldwide excluding USA",
                "underwriting": {"basis": "CPME", "pre_existing_conditions": "Subject to CPME terms"},
                "benefits": {"inpatient": "Covered", "outpatient": "EUR 12,000", "cancer": "Covered"},
            },
        },
    ]


def sample_analysis(results):
    return {
        "report_title": "International Health Insurance Comparison",
        "client_name": "Test Client",
        "client_needs_summary": "Priority is strong outpatient and continuity.",
        "client_profile": "Resident in Greece.",
        "executive_summary": "Two international plans have been compared on benefits and policy structure.",
        "plans": [
            {"provider": "IMG", "plan_name": "Silver", "positioning": "Higher headline annual limit.", "summary": "IMG offers a high overall limit.", "strengths": ["EUR 3m annual limit"], "considerations": ["FMU applies"]},
            {"provider": "Cigna", "plan_name": "Silver", "positioning": "Lower limit with stronger outpatient amount in this comparison.", "summary": "Cigna has a lower headline annual limit.", "strengths": ["EUR 12k outpatient"], "considerations": ["CPME terms require confirmation"]},
        ],
        "comparison_matrix": build_comparison_matrix(results),
        "key_differences": [{"title": "Annual limit vs outpatient", "analysis": "IMG has the higher annual limit while Cigna shows the higher outpatient amount.", "client_impact": "Relevant if outpatient use is a priority."}],
        "ashlar_assessment": {"recommended_provider": "Cigna", "recommended_plan": "Silver", "headline": "Cigna is the closer fit to the stated outpatient priority.", "reasoning": ["Higher stated outpatient amount", "Nil stated excess"], "alternative_provider": "IMG", "alternative_plan": "Silver", "alternative_reason": "Higher headline annual limit.", "when_the_alternative_may_be_better": "If the client prioritises maximum overall annual cover."},
        "important_considerations": ["Underwriting terms require insurer confirmation."],
        "next_steps": ["Confirm underwriting outcome before replacement of existing cover."],
        "disclaimer": "Final cover remains subject to insurer terms and underwriting.",
    }


def test_matrix_and_exports_are_nonempty():
    results = sample_results()
    matrix = build_comparison_matrix(results)
    assert matrix[0]["topic"] == "Premium"
    analysis = sample_analysis(results)
    pptx = build_pptx_bytes(client_analysis=analysis, results=results)
    pdf = build_pdf_bytes(client_analysis=analysis, results=results)
    assert pptx[:2] == b"PK"
    assert pdf[:4] == b"%PDF"
    assert len(pptx) > 10000
    assert len(pdf) > 5000
