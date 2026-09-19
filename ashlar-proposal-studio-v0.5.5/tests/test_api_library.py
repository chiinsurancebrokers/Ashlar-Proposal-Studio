from types import SimpleNamespace

from fastapi.testclient import TestClient

import api.main as api_main


client = TestClient(api_main.app)


def test_library_catalog_requires_adviser_key(monkeypatch):
    monkeypatch.setenv("ADVISER_OS_LIBRARY_KEY", "test-adviser-key")
    monkeypatch.setattr(api_main, "list_catalog", lambda: [
        {"provider": "IMG", "product": "Global Prima", "version": "2026", "document_count": 2}
    ])

    denied = client.get("/api/v1/library/catalog")
    assert denied.status_code == 401

    response = client.get(
        "/api/v1/library/catalog",
        headers={"x-ashlar-api-key": "test-adviser-key"},
    )
    assert response.status_code == 200
    assert response.json()["catalog"][0]["provider"] == "IMG"


def test_library_plan_context_returns_cached_provider_evidence(monkeypatch):
    monkeypatch.setenv("ADVISER_OS_LIBRARY_KEY", "test-adviser-key")
    doc = SimpleNamespace(
        id="doc-1",
        provider="Cigna",
        product="Inspire",
        version="2026",
        doc_type="wording",
        original_filename="inspire-wording.txt",
        effective_from="2026-01-01",
        effective_to=None,
        extracted_text="ExecutiveCare verified provider-library text.",
    )
    monkeypatch.setattr(api_main, "get_documents", lambda provider, product, version: [doc])

    response = client.post(
        "/api/v1/library/plan-context",
        headers={"x-ashlar-api-key": "test-adviser-key"},
        json={
            "provider": "Cigna",
            "product": "Inspire",
            "version": "2026",
            "target_plan": "ExecutiveCare",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["target_plan"] == "ExecutiveCare"
    assert data["documents"][0]["extracted_text"].startswith("ExecutiveCare")
