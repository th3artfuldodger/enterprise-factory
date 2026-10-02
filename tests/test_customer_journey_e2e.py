"""HTTP journey: register → login → demo-notes CRUD → logout (+ telemetry evolution signal)."""

from __future__ import annotations

import json

import pytest

from web.backend.services.commerce import CommerceService


@pytest.fixture
def journey_commerce(tmp_path, monkeypatch):
    monkeypatch.setenv("CUSTOMER_JWT_SECRET", "test-customer-jwt-secret-ci-only-do-not-use-prod")
    svc = CommerceService(base_dir=str(tmp_path / "store"))
    import web.backend.api.customer as cust

    monkeypatch.setattr(cust, "commerce", svc)
    return svc


@pytest.fixture
def client(journey_commerce):
    from fastapi.testclient import TestClient

    from web.backend.main import app

    with TestClient(app) as c:
        root = journey_commerce.base.parent / "telemetry_root"
        root.mkdir(parents=True, exist_ok=True)
        c.app.state.telemetry.data_root = root
        yield c


def test_customer_journey_register_login_crud_logout(client):
    email = "journey-e2e@example.test"
    password = "password123"

    r = client.post("/api/customer/register", json={"email": email, "password": password})
    assert r.status_code == 200
    reg = r.json()
    token_register = reg["access_token"]

    r = client.post("/api/customer/login", json={"email": email, "password": password})
    assert r.status_code == 200
    token_login = r.json()["access_token"]
    assert isinstance(token_login, str) and len(token_login) > 10

    auth_reg = {"Authorization": f"Bearer {token_register}"}
    auth_login = {"Authorization": f"Bearer {token_login}"}

    r = client.get("/api/customer/me", headers=auth_reg)
    assert r.status_code == 200
    assert r.json().get("email") == email

    r = client.post("/api/customer/demo-notes", headers=auth_reg, json={"title": "First", "body": "alpha"})
    assert r.status_code == 200
    note_id = r.json()["note"]["id"]

    r = client.get("/api/customer/demo-notes", headers=auth_login)
    assert r.status_code == 200
    assert r.json()["count"] == 1
    assert r.json()["notes"][0]["title"] == "First"

    r = client.patch(
        f"/api/customer/demo-notes/{note_id}",
        headers=auth_login,
        json={"title": "Updated", "body": "beta"},
    )
    assert r.status_code == 200
    assert r.json()["note"]["title"] == "Updated"

    r = client.delete(f"/api/customer/demo-notes/{note_id}", headers=auth_reg)
    assert r.status_code == 200

    r = client.get("/api/customer/demo-notes", headers=auth_login)
    assert r.status_code == 200
    assert r.json()["count"] == 0

    r = client.post("/api/customer/logout")
    assert r.status_code == 200
    assert r.json().get("ok") is True


def test_customer_register_duplicate(client):
    email = "dup@example.test"
    password = "password123"
    assert client.post("/api/customer/register", json={"email": email, "password": password}).status_code == 200
    r = client.post("/api/customer/register", json={"email": email, "password": password})
    assert r.status_code == 409


def test_evolution_signal_endpoint(client):
    pid = "prod-testtelemetry01"
    r = client.post(
        "/api/telemetry/evolution-signal",
        json={
            "product_id": pid,
            "signal": "nps",
            "weight": 0.8,
            "context": {"bucket": "promoter"},
        },
    )
    assert r.status_code == 200
    assert r.json().get("ok") is True

    root = client.app.state.telemetry.data_root
    files = list((root / pid).glob("telemetry_*.jsonl"))
    assert files, "telemetry jsonl should exist"
    last = files[-1].read_text(encoding="utf-8").strip().splitlines()[-1]
    row = json.loads(last)
    assert row.get("event_type") == "evolution_signal"
    assert row.get("data", {}).get("signal") == "nps"


def test_browser_login_uses_httponly_cookie_without_returning_jwt(client):
    email = "browser-cookie@example.test"
    password = "password123"
    headers = {"Origin": "http://localhost:8080"}
    reg = client.post("/api/customer/register", headers=headers, json={"email": email, "password": password})
    assert reg.status_code == 200
    assert "access_token" not in reg.json()
    assert reg.json().get("token_type") == "cookie"
    assert "customer_token=" in (reg.headers.get("set-cookie") or "")
    assert "HttpOnly" in (reg.headers.get("set-cookie") or "")

    me = client.get("/api/customer/me", headers={"Origin": "http://localhost:8080"})
    assert me.status_code == 200
    assert me.json().get("email") == email


def test_customer_factory_vertical_slice_http(client, journey_commerce, tmp_path, monkeypatch):
    from web.backend.services import tenant_workspaces as tenants

    monkeypatch.setattr(tenants, "data_root", lambda: tmp_path / "tenant-data")

    email = "factory-vertical@example.test"
    password = "password123"
    reg = client.post("/api/customer/register", json={"email": email, "password": password})
    assert reg.status_code == 200
    token = reg.json()["access_token"]
    auth = {"Authorization": f"Bearer {token}"}

    initial = client.get("/api/customer/factory", headers=auth)
    assert initial.status_code == 200
    assert initial.json()["tenant_isolated"] is True
    assert initial.json()["projects"] == []

    mission = client.post(
        "/api/customer/factory/mission",
        headers=auth,
        json={"prompt": "Research a market opportunity system for independent roofers and prepare a launch plan."},
    )
    assert mission.status_code == 200
    mission_body = mission.json()
    product_id = mission_body["product_id"]
    assert mission_body["department"] == "small_business"
    assert len(mission_body["research_agents"]) == 5
    assert len(mission_body["task_ids"]) == 7

    worker = client.post(
        "/api/customer/factory/personnel",
        headers=auth,
        json={"description": "Validates lead sources and evidence.", "role_class": "worker", "label": "Lead Scout"},
    )
    manager = client.post(
        "/api/customer/factory/personnel",
        headers=auth,
        json={"description": "Assigns and reviews lead research.", "role_class": "manager", "label": "Lead Manager"},
    )
    assert worker.status_code == manager.status_code == 200

    delegated = client.post(
        f"/api/customer/factory/managers/{manager.json()['id']}/delegate",
        headers=auth,
        json={"worker_id": worker.json()["id"], "product_id": product_id, "directive": "Validate the top three lead channels."},
    )
    assert delegated.status_code == 200

    final = client.get("/api/customer/factory", headers=auth)
    assert final.status_code == 200
    body = final.json()
    assert len(body["projects"]) == 1
    assert body["task_count"] >= 8
    assert len(body["workforce"]) == 2
    assert body["customer_permissions"]["may_move_money"] is False
