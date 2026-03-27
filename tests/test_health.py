from fastapi.testclient import TestClient

from delphi.api.app import app

client = TestClient(app)


def test_health():
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "version" in data


def test_status():
    resp = client.get("/status")
    assert resp.status_code == 200
    data = resp.json()
    assert "vllm" in data
    assert "qdrant" in data
    assert "embedding" in data
