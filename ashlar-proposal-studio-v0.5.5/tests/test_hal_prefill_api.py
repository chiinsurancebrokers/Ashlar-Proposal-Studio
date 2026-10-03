from fastapi.testclient import TestClient
from api import main

client = TestClient(main.app)


def test_hal_prefill_preserves_reference(monkeypatch):
    monkeypatch.setenv("HAL_BRIDGE_API_KEY", "test-key")
    captured = {}
    def fake_save_case_snapshot(**kwargs):
        captured.update(kwargs)
        return {"id": kwargs["case_id"], "case_reference": kwargs["case_reference"]}
    monkeypatch.setattr(main, "save_case_snapshot", fake_save_case_snapshot)
    response = client.post(
        "/api/v1/hal/prefill",
        headers={"X-HAL-Bridge-Key": "test-key"},
        json={"external_reference": "HALS-TEST123", "source": "hal", "fact_find": {"age": 40}},
    )
    assert response.status_code == 200
    assert response.json()["case_reference"] == "HALS-TEST123"
    assert captured["case_id"] == "HALS-TEST123"
