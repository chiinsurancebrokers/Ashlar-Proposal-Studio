from core.client_analysis import CLIENT_ANALYSIS_PROMPT, apply_client_report_rules


def _results():
    return [
        {"provider": "Bupa Global", "target_plan": "SELECT", "analysis": {
            "provider": "Bupa Global", "plan_name": "SELECT",
            "underwriting": {"basis": "Full Medical Underwriting"},
            "deductible_or_excess": "€0 deductible",
        }},
        {"provider": "IMG", "target_plan": "SILVER", "analysis": {
            "provider": "IMG", "plan_name": "SILVER",
            "underwriting": {"basis": "Full Medical Underwriting"},
            "deductible_or_excess": "€0 deductible",
        }},
    ]


def test_recommendation_prompt_compares_final_quoted_configuration():
    assert "FINAL QUOTED CONFIGURATION" in CLIENT_ANALYSIS_PROMPT
    assert "do NOT force a single winner" in CLIENT_ANALYSIS_PROMPT
    assert "base plan" in CLIENT_ANALYSIS_PROMPT


def test_assessment_neutralises_base_plan_packaging_bias():
    report = {
        "executive_summary": "Summary.",
        "client_needs_summary": "Strong inpatient and outpatient cover.",
        "plans": [],
        "key_differences": [],
        "ashlar_assessment": {
            "recommended_provider": "Bupa Global",
            "recommended_plan": "SELECT",
            "headline": "SELECT aligns by including both benefits within the base plan, without requiring optional modules to reach that scope.",
            "reasoning": ["Bupa delivers both within its base premium."],
            "alternative_reason": "",
            "when_the_alternative_may_be_better": "",
        },
        "important_considerations": [],
        "next_steps": [],
    }
    cleaned = apply_client_report_rules(
        report, results=_results(), client_sex="male", client_age=18,
        client_priorities="strong inpatient and outpatient cover", language="English"
    )
    assessment = cleaned["ashlar_assessment"]
    assert "optional modules" not in assessment["headline"].casefold()
    assert "quoted configuration" in assessment["headline"].casefold()
    assert "base premium" not in " ".join(assessment["reasoning"]).casefold()
    assert "quoted premium" in " ".join(assessment["reasoning"]).casefold()
