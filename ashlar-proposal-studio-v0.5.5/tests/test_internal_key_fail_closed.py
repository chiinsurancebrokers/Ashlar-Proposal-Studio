from fastapi.testclient import TestClient

from api.main import app

client = TestClient(app)


def test_job_routes_closed_when_key_unset(monkeypatch):
    monkeypatch.delenv("ASHLAR_INTERNAL_API_KEY", raising=False)
    assert client.get("/api/v1/jobs/abc").status_code == 401
    assert client.post("/api/v1/jobs/report", json={"case_id": "x"}).status_code == 401


def test_job_routes_reject_wrong_key_and_accept_right_one(monkeypatch):
    monkeypatch.setenv("ASHLAR_INTERNAL_API_KEY", "s3cret")
    assert client.get("/api/v1/jobs/abc", headers={"x-ashlar-api-key": "nope"}).status_code == 401
    assert client.get("/api/v1/jobs/abc", headers={"x-ashlar-api-key": "s3cret"}).status_code != 401


def test_hal_bridge_closed_when_key_unset(monkeypatch):
    monkeypatch.delenv("HAL_BRIDGE_API_KEY", raising=False)
    r = client.post("/api/v1/hal/prefill", json={"external_reference": "HALS-1"})
    assert r.status_code == 401
