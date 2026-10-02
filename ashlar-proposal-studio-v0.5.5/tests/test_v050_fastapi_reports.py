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


def test_current_policy_upload_endpoint_returns_structured_facts(monkeypatch):
    from fastapi.testclient import TestClient
    import api.main as api_main

    monkeypatch.setenv("HAL_BRIDGE_API_KEY", "secret")
    monkeypatch.setattr(
        api_main,
        "extract_document",
        lambda *_args, **_kwargs: type("X", (), {
            "ok": True, "text": "Policy wording sample with enough usable text for extraction.",
            "error": "", "content_hash": "abc", "pages": 3
        })(),
    )
    monkeypatch.setattr(api_main, "identify_selected_plan", lambda *_a, **_k: {"plan_name": "Current Silver"})
    monkeypatch.setattr(
        api_main, "_supporting_wording_for",
        lambda *_a, **_k: ("Official supporting wording text", "", [{
            "id": "doc1", "provider": "Current insurer", "product": "Current Silver",
            "version": "2026", "doc_type": "policy wording",
            "filename": "wording.pdf", "url": "https://example.test/wording.pdf",
            "evidence_role": "policy_wording",
        }]),
    )
    monkeypatch.setattr(
        api_main,
        "analyze_target_plan",
        lambda **_k: {
            "provider": "Current insurer", "plan_name": "Current Silver",
            "premium": {"amount": 2400, "currency": "EUR", "frequency": "Annual"},
            "deductible_or_excess": "€500", "annual_limit": "€1,000,000",
            "area_of_cover": "Europe", "underwriting": {"basis": "FMU"},
            "benefits": {"inpatient": "Covered", "outpatient": "€3,000"},
            "critical_limitations": [], "waiting_periods": [], "source_evidence": [],
            "confidence": "high",
        },
    )
    client = TestClient(api_main.app)
    response = client.post(
        "/api/v1/current-policy/analyze",
        headers={"x-hal-bridge-key": "secret"},
        files={"file": ("policy.pdf", b"%PDF fake content", "application/pdf")},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["plan_name"] == "Current Silver"
    assert body["premium"]["amount"] == 2400
    assert body["benefits"]["outpatient"] == "€3,000"
    assert body["policy_wording_status"] == "attached"
    assert body["supporting_documents"][0]["doc_type"] == "policy wording"


def test_current_policy_upload_rejects_unsupported_type(monkeypatch):
    from fastapi.testclient import TestClient
    import api.main as api_main
    monkeypatch.setenv("HAL_BRIDGE_API_KEY", "secret")
    response = TestClient(api_main.app).post(
        "/api/v1/current-policy/analyze",
        headers={"x-hal-bridge-key": "secret"},
        files={"file": ("policy.exe", b"abc", "application/octet-stream")},
    )
    assert response.status_code == 400


def test_supporting_wording_lookup_prefers_bupa_provider_library(monkeypatch):
    import api.main as api_main

    class Doc:
        def __init__(self, provider, product, doc_type, filename, text, uploaded_at):
            self.id = filename
            self.provider = provider
            self.product = product
            self.version = "2026"
            self.doc_type = doc_type
            self.original_filename = filename
            self.extracted_text = text
            self.uploaded_at = uploaded_at

    monkeypatch.setattr(api_main, "list_documents", lambda: [
        Doc("Bupa Global", "Worldwide Health Options", "membership guide", "bupa-guide.pdf", "Bupa benefit wording", "2026-09-01"),
        Doc("Other", "Other", "policy wording", "other.pdf", "Other wording", "2026-10-01"),
    ])
    monkeypatch.setattr(api_main, "create_document_signed_url", lambda doc, expires_in_seconds=0: "https://signed.test/" + doc.original_filename)

    wording, supporting, docs = api_main._supporting_wording_for("Bupa", "bupa")
    assert "Bupa benefit wording" in wording
    assert supporting == ""
    assert len(docs) == 1
    assert docs[0]["filename"] == "bupa-guide.pdf"
    assert docs[0]["url"].endswith("bupa-guide.pdf")


def test_supporting_brochure_is_not_mislabelled_as_policy_wording(monkeypatch):
    import api.main as api_main

    class Doc:
        def __init__(self):
            self.id = "brochure.pdf"
            self.provider = "Bupa Global"
            self.product = "Worldwide Health Options"
            self.version = "2026"
            self.doc_type = "brochure"
            self.original_filename = "BWHO-product-summary.pdf"
            self.extracted_text = "Bupa summary of benefits"
            self.uploaded_at = "2026-09-01"

    monkeypatch.setattr(api_main, "list_documents", lambda: [Doc()])
    monkeypatch.setattr(api_main, "create_document_signed_url", lambda doc, expires_in_seconds=0: "https://signed.test/brochure.pdf")

    wording, supporting, docs = api_main._supporting_wording_for("Bupa", "bupa")
    assert wording == ""
    assert "Bupa summary of benefits" in supporting
    assert docs[0]["evidence_role"] == "supporting"
