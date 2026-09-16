import pytest

from core.client_analysis import _source_digest
from core.report_schema import ClientReportValidationError, validate_client_report


def _result(provider="Carrier", plan="Silver"):
    return {"provider": provider, "target_plan": plan, "analysis": {"provider": provider, "plan_name": plan}}


def _valid_report(provider="Carrier", plan="Silver"):
    return {
        "report_title": "Comparison",
        "executive_summary": "A complete executive summary.",
        "client_needs_summary": "Needs",
        "plans": [{
            "provider": provider,
            "plan_name": plan,
            "positioning": "",
            "summary": "A usable plan summary.",
            "strengths": ["A"],
            "considerations": ["B"],
            "best_suited_when": "",
            "source_notes": [],
        }],
        "key_differences": [],
        "ashlar_assessment": {
            "recommended_provider": provider,
            "recommended_plan": plan,
            "headline": "Ashlar view",
            "reasoning": ["Grounded reason"],
            "alternative_provider": "",
            "alternative_plan": "",
            "alternative_reason": "",
            "when_the_alternative_may_be_better": "",
        },
        "important_considerations": [],
        "next_steps": ["Complete application"],
        "disclaimer": "Subject to underwriting.",
    }


def test_report_validator_accepts_complete_single_plan_report():
    report = _valid_report()
    assert validate_client_report(report, [_result()]) is report


def test_report_validator_rejects_empty_plan_list():
    report = _valid_report()
    report["plans"] = []
    with pytest.raises(ClientReportValidationError):
        validate_client_report(report, [_result()])


def test_report_validator_rejects_missing_expected_plan():
    report = _valid_report("Other", "Gold")
    with pytest.raises(ClientReportValidationError, match="Missing plan"):
        validate_client_report(report, [_result("Carrier", "Silver")])


def test_comparative_report_requires_key_differences():
    report = _valid_report("Carrier", "Silver")
    report["plans"].append({**report["plans"][0], "provider": "Other", "plan_name": "Gold"})
    with pytest.raises(ClientReportValidationError, match="no key differences"):
        validate_client_report(report, [_result("Carrier", "Silver"), _result("Other", "Gold")])


def test_source_digest_is_bounded_for_large_extraction():
    result = {
        "analysis": {
            "source_evidence": [
                {"field": "premium", "value": i, "document": "q.pdf", "page": i, "evidence": "x"}
                for i in range(50)
            ]
        },
        "focused_rows": [
            {"benefit": f"Outpatient {i}", "value": str(i), "source_file": "b.pdf", "page": i, "evidence_type": "table"}
            for i in range(100)
        ],
    }
    digest = _source_digest(result)
    assert 1 <= len(digest) <= 14

def test_fastapi_health_endpoint():
    from fastapi.testclient import TestClient
    from api.main import app
    response = TestClient(app).get('/health')
    assert response.status_code == 200
    assert response.json()['status'] == 'ok'
