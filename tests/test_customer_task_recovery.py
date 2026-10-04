import pytest

from orchestrator.sqlite_manager import SQLiteManager
from web.backend.services import customer_task_recovery as recovery
from web.backend.services import provider_health
from web.backend.services import tenant_workspaces as tenants


def _ctx(tmp_path, monkeypatch, customer_id: str):
    monkeypatch.setattr(tenants, "data_root", lambda: tmp_path)
    monkeypatch.setattr(recovery, "customer_workspace_context", lambda cid: tenants.customer_workspace_context(cid))
    return tenants.customer_workspace_context(customer_id)


def test_retry_failed_task_stays_tenant_scoped_and_deduplicates(tmp_path, monkeypatch):
    ctx = _ctx(tmp_path, monkeypatch, "owner-a")
    tenants.write_customer_product("owner-a", {"id": "prod-retry1234", "idea": "Retry me", "state": "IDEA_RECEIVED"})
    sm = SQLiteManager(ctx["pipeline_db"], workspace_id=ctx["workspace_id"])
    sm.connect()
    sm.upsert_task({
        "id": "task-failed1234", "workspace_id": ctx["workspace_id"], "product_id": "prod-retry1234",
        "agent_type": "analyst", "assigned_to": "unit-a", "state": "CUSTOMER_MANAGER_ASSIGNMENT",
        "status": "failed", "created_at": 1.0, "completed_at": 2.0, "retry_count": 0,
        "input_data": {"assignment_directive": "Try again with fresh evidence."}, "error": "provider timeout",
    })
    sm.close()

    first = recovery.retry_customer_task("owner-a", "task-failed1234")
    assert first["status"] == "pending"
    state = tenants.read_customer_pipeline_state("owner-a")
    retry = next(t for t in state["task_queue"] if t["id"] == first["task_id"])
    assert retry["input_data"]["retry_of"] == "task-failed1234"
    assert retry["retry_count"] == 1

    second = recovery.retry_customer_task("owner-a", "task-failed1234")
    assert second["task_id"] == first["task_id"]
    assert second["deduplicated"] is True

    _ctx(tmp_path, monkeypatch, "owner-b")
    with pytest.raises(ValueError, match="Task not found"):
        recovery.retry_customer_task("owner-b", "task-failed1234")


def test_provider_health_tracks_offline_to_online_recovery(monkeypatch):
    provider_health._STATE.update({"was_online": None, "recovery_count": 0, "last_recovered_at": None})
    def down(url, timeout=0.45):
        raise OSError("offline")
    monkeypatch.setattr(provider_health, "_get_json", down)
    assert provider_health.local_ollama_health()["online"] is False

    def up(url, timeout=0.45):
        return {"models": [{"name": "qwen2.5:3b"}]} if url.endswith("/api/tags") else {"version": "0.35.0"}
    monkeypatch.setattr(provider_health, "_get_json", up)
    snap = provider_health.local_ollama_health()
    assert snap["online"] is True
    assert snap["models"] == ["qwen2.5:3b"]
    assert snap["recovery_count"] == 1
