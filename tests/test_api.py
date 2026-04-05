"""HTTP integration tests using FastAPI's TestClient.

The tests build a fresh FastAPI app with its dependency overridden so the
service runs against a temp directory rather than the default env-based
settings.
"""

from __future__ import annotations

import copy

from fastapi.testclient import TestClient

from agent.api.routes import _svc as svc_dep
from agent.main import create_app


def _client(service):
    app = create_app()
    app.dependency_overrides[svc_dep] = lambda: service
    return TestClient(app)


def test_health(service):
    resp = _client(service).get("/api/v1/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_full_revision_flow(service, valid_config):
    client = _client(service)

    # create
    resp = client.post(
        "/api/v1/revisions",
        json={"config": valid_config, "author": "alice", "note": "initial"},
    )
    assert resp.status_code == 200, resp.text
    rid = resp.json()["revision_id"]
    assert resp.json()["validation_status"] == "valid"

    # list
    resp = client.get("/api/v1/revisions")
    assert resp.status_code == 200
    assert any(r["id"] == rid for r in resp.json())

    # apply
    resp = client.post(f"/api/v1/revisions/{rid}/apply")
    assert resp.status_code == 200
    assert resp.json()["status"] == "success"

    # current
    resp = client.get("/api/v1/config/current")
    assert resp.status_code == 200
    assert resp.json()["active"]["id"] == rid


def test_diff_endpoint(service, valid_config):
    client = _client(service)
    r1 = client.post(
        "/api/v1/revisions",
        json={"config": valid_config, "author": "a"},
    ).json()["revision_id"]
    client.post(f"/api/v1/revisions/{r1}/apply")

    modified = copy.deepcopy(valid_config)
    modified["telemetry"]["interval_seconds"] = 120
    r2 = client.post(
        "/api/v1/revisions",
        json={"config": modified, "author": "a"},
    ).json()["revision_id"]

    resp = client.get(f"/api/v1/revisions/{r2}/diff?against=active")
    assert resp.status_code == 200
    data = resp.json()
    assert data["from_revision"] == r1
    assert data["to_revision"] == r2
    assert any("interval_seconds" in e["path"] for e in data["entries"])


def test_schema_endpoint(service):
    client = _client(service)
    resp = client.get("/api/v1/config/schema")
    assert resp.status_code == 200
    assert "network" in resp.json()["properties"]

    resp = client.get("/api/v1/config/schema?module=network")
    assert resp.status_code == 200
    assert resp.json()["title"] == "Network"

    resp = client.get("/api/v1/config/schema?module=unknown")
    assert resp.status_code == 404


def test_rollback_endpoint(service, valid_config):
    client = _client(service)
    r1 = client.post("/api/v1/revisions", json={"config": valid_config}).json()["revision_id"]
    client.post(f"/api/v1/revisions/{r1}/apply")

    modified = copy.deepcopy(valid_config)
    modified["system"]["hostname"] = "gateway-99"
    r2 = client.post("/api/v1/revisions", json={"config": modified}).json()["revision_id"]
    client.post(f"/api/v1/revisions/{r2}/apply")

    resp = client.post(f"/api/v1/revisions/{r1}/rollback")
    assert resp.status_code == 200
    assert resp.json()["status"] == "success"

    active = client.get("/api/v1/config/current").json()["active"]
    assert active["id"] == r1
