from core.client_analysis import (
    MODULAR_SYNTHESIS_PROMPT,
    _compact_decision_payload,
    _plan_narrative_from_verified_facts,
    _assemble_modular_report,
)
from core.report_schema import validate_client_report


def _payload():
    return {
        "case_reference": "TEST",
        "client_name": "Test Client",
        "client_profile": "Student in Germany",
        "client_priorities": "Strong inpatient and outpatient cover",
        "client_sex": "male",
        "client_age": 18,
        "maternity_relevant": False,
        "comparison_matrix": [],
        "plans": [
            {
                "provider": "IMG",
                "plan_name": "Silver",
                "premium": {"amount":"1792.88","currency":"EUR","frequency":"Annual"},
                "annual_limit": "€3,000,000",
                "deductible_or_excess": "€0 deductible",
                "area_of_cover": "Worldwide excluding USA",
                "underwriting": {"basis":"Full Medical Underwriting"},
                "benefits": {"inpatient":"Covered", "outpatient":"€10,000/year", "diagnostics_imaging":"MRI/CT/PET covered"},
                "waiting_periods": [], "critical_limitations": [],
            },
            {
                "provider": "Bupa Global",
                "plan_name": "SELECT",
                "premium": {"amount":"2165.08","currency":"EUR","frequency":"Annual"},
                "annual_limit": "€1,250,000",
                "deductible_or_excess": "€0 deductible",
                "area_of_cover": "Worldwide excluding USA",
                "underwriting": {"basis":"Full Medical Underwriting"},
                "benefits": {"inpatient":"Paid in full", "outpatient":"€9,400/year", "diagnostics_imaging":"Advanced imaging paid in full subject to pre-authorisation"},
                "waiting_periods": [], "critical_limitations": [],
            },
        ],
    }


def test_modular_prompt_does_not_request_plan_narratives():
    assert "NOT writing the whole report" in MODULAR_SYNTHESIS_PROMPT
    assert "up to 4 key_differences" in MODULAR_SYNTHESIS_PROMPT


def test_compact_payload_has_no_comparison_matrix_or_source_audit():
    compact = _compact_decision_payload(_payload())
    assert "comparison_matrix" not in compact
    assert all("source_evidence" not in p for p in compact["plans"])


def test_plan_narrative_is_deterministic_and_concise():
    narrative = _plan_narrative_from_verified_facts(_payload()["plans"][0], language="English")
    assert narrative["provider"] == "IMG"
    assert "€3,000,000" in narrative["positioning"]
    assert len(narrative["summary"].split()) <= 90
    assert len(narrative["strengths"]) <= 4


def test_assembled_report_can_validate_after_rules_supply_workflow():
    payload = _payload()
    synthesis = {
        "executive_summary":"Two plans are compared against the stated inpatient and outpatient priority.",
        "client_needs_summary":"Strong inpatient and outpatient cover.",
        "key_differences":[{"title":"Outpatient structure","analysis":"IMG has €10,000 while Bupa has €9,400.","client_impact":"Both are material to the stated priority."}],
        "ashlar_assessment":{"recommended_provider":"Bupa Global","recommended_plan":"SELECT","headline":"Bupa is the primary recommendation, with IMG as the strongest value alternative.","reasoning":["Bupa closely matches the stated inpatient/outpatient priority.","IMG has a higher overall limit and lower premium."],"alternative_provider":"IMG","alternative_plan":"Silver","alternative_reason":"Higher overall limit and lower premium.","when_the_alternative_may_be_better":"If value and overall protection ceiling matter more."},
        "important_considerations":["Bupa advanced imaging requires pre-authorisation."],
    }
    report = _assemble_modular_report(payload=payload, synthesis=synthesis, language="English")
    # workflow gets normalised later by apply_client_report_rules; placeholder is valid
    results=[]
    for p in payload["plans"]:
        results.append({"provider":p["provider"],"target_plan":p["plan_name"],"analysis":{"provider":p["provider"],"plan_name":p["plan_name"]}})
    validate_client_report(report, results)
