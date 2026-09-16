from core.client_analysis import (
    MODULAR_SYNTHESIS_PROMPT,
    _compact_decision_payload,
    _waiting_period_claim_supported,
    apply_client_report_rules,
)
from core.report_schema import ClientReportValidationError, validate_client_report


def _results():
    return [
        {"provider":"Bupa Global","target_plan":"SELECT","analysis":{
            "provider":"Bupa Global","plan_name":"SELECT",
            "premium":{"amount":"2165.08","currency":"EUR","frequency":"Annual"},
            "annual_limit":"€1,250,000","deductible_or_excess":"€0 deductible",
            "underwriting":{"basis":"Full Medical Underwriting"},
            "benefits":{"outpatient":"€9,400/year","dental":"Not covered"},
            "waiting_periods":[],"critical_limitations":[]}},
        {"provider":"Cigna","target_plan":"Silver","analysis":{
            "provider":"Cigna","plan_name":"Silver",
            "premium":{"amount":"2389.83","currency":"EUR","frequency":"Annual"},
            "annual_limit":"€800,000","deductible_or_excess":"€0 deductible",
            "underwriting":{"basis":"Full Medical Underwriting"},
            "benefits":{"outpatient":"€12,000/year","dental":"€930 selected"},
            "waiting_periods":[],"critical_limitations":[]}},
        {"provider":"IMG","target_plan":"Silver","analysis":{
            "provider":"IMG","plan_name":"Silver",
            "premium":{"amount":"1792.88","currency":"EUR","frequency":"Annual"},
            "annual_limit":"€3,000,000","deductible_or_excess":"€0 deductible",
            "underwriting":{"basis":"Full Medical Underwriting"},
            "benefits":{"outpatient":"€10,000/year","chronic_conditions":"routine management €1,000/year"},
            "waiting_periods":[],"critical_limitations":[]}},
        {"provider":"Now Health","target_plan":"SimpleCare 250","analysis":{
            "provider":"Now Health","plan_name":"SimpleCare 250",
            "premium":{"amount":"1092.07","currency":"EUR","frequency":"Annual"},
            "annual_limit":"€1,200,000","deductible_or_excess":"€0 deductible",
            "underwriting":{"basis":"Full Medical Underwriting"},
            "benefits":{"outpatient":"€2,000/year","dental":"€240; 9-month waiting period"},
            "waiting_periods":[{"detail":"Dental treatment: 9-month waiting period"}],"critical_limitations":[]}},
    ]


def _payload():
    return {"case_reference":"T","client_name":"Client","client_profile":"Student","client_priorities":"Strong inpatient and outpatient cover","client_sex":"male","client_age":17,"maternity_relevant":False,
            "plans":[{**(r["analysis"]), "provider":r["analysis"]["provider"], "plan_name":r["analysis"]["plan_name"]} for r in _results()]}


def test_prompt_requires_clear_broker_recommendation_and_routes():
    assert "GIVE ONE CLEAR PRIMARY RECOMMENDATION" in MODULAR_SYNTHESIS_PROMPT
    assert "Broader" in MODULAR_SYNTHESIS_PROMPT or "broader-extras" in MODULAR_SYNTHESIS_PROMPT
    assert '"budget_provider"' in MODULAR_SYNTHESIS_PROMPT


def test_compact_payload_contains_deterministic_premium_order():
    compact=_compact_decision_payload(_payload())
    facts=compact["derived_facts"]
    assert facts["highest_premium"]["plan"].startswith("Cigna")
    assert facts["lowest_premium"]["plan"].startswith("Now Health")
    assert facts["highest_stated_annual_limit"]["plan"].startswith("IMG")


def test_wrong_cross_benefit_waiting_period_is_rejected():
    assert not _waiting_period_claim_supported("Now Health applies a 9-month waiting period for major elective surgery.", _results())
    assert _waiting_period_claim_supported("Now Health dental treatment has a 9-month waiting period.", _results())


def test_wrong_highest_premium_claim_is_softened_by_guardrail():
    report={"executive_summary":"Bupa is at the highest premium.","client_needs_summary":"","plans":[],"key_differences":[],
            "ashlar_assessment":{"recommended_provider":"Bupa Global","recommended_plan":"SELECT","headline":"Bupa at the highest premium","reasoning":["Bupa carries the highest premium."],"alternative_provider":"IMG","alternative_plan":"Silver","alternative_reason":"","when_the_alternative_may_be_better":""},
            "important_considerations":[],"next_steps":[]}
    out=apply_client_report_rules(report,results=_results(),client_sex="Male",client_age=17)
    assert "highest premium" not in out["executive_summary"].lower()
    assert "highest premium" not in out["ashlar_assessment"]["reasoning"][0].lower()


def test_comparative_report_requires_primary_recommendation():
    report={"report_title":"Test","executive_summary":"Summary","client_needs_summary":"Needs","plans":[
        {"provider":"Bupa Global","plan_name":"SELECT","summary":"x"},
        {"provider":"IMG","plan_name":"Silver","summary":"x"}],
        "key_differences":[{"title":"x","analysis":"y","client_impact":"z"}],
        "ashlar_assessment":{"recommended_provider":"","recommended_plan":"","headline":"Trade off","reasoning":["reason"]},
        "important_considerations":[],"next_steps":["step"],"disclaimer":"notice"}
    try:
        validate_client_report(report,_results()[:1]+[_results()[2]])
    except ClientReportValidationError as exc:
        assert "clear recommended option" in str(exc)
    else:
        raise AssertionError("Expected recommendation validation error")
