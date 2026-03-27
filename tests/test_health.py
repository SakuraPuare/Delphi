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


def test_list_projects_empty():
    resp = client.get("/projects")
    assert resp.status_code == 200
    assert resp.json() == []


def test_create_and_delete_project():
    resp = client.post("/projects", json={"name": "test-proj"})
    assert resp.status_code == 201
    assert resp.json()["name"] == "test-proj"

    resp = client.delete("/projects/test-proj")
    assert resp.status_code == 204

    resp = client.get("/projects")
    assert resp.json() == []
