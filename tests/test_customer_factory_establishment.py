import json
import time
from pathlib import Path

import pytest

from web.backend.services import customer_factory_establishment as est
from web.backend.services import customer_workforce as workforce
from web.backend.services import tenant_workspaces as tenants


def _patch_root(tmp_path, monkeypatch):
    monkeypatch.setattr(tenants, "data_root", lambda: tmp_path)


def test_plan_limits_and_templates_keep_financial_boundary():
    assert est.limits_for("free")["projects"] < est.limits_for("enterprise")["projects"]
    assert est.limits_for("free")["active_tasks"] >= 7
    assert len(est.MISSION_TEMPLATES) >= 7
    assert "approve_funding" in workforce.FORBIDDEN_FINANCIAL_PERMISSIONS
    assert "spend_money" in workforce.FORBIDDEN_FINANCIAL_PERMISSIONS


def test_project_controls_are_tenant_scoped_and_reversible(tmp_path, monkeypatch):
    _patch_root(tmp_path, monkeypatch)
    cid = "control-customer"
    tenants.write_customer_product(cid, {"id": "prod-control1234", "idea": "Control", "state": "IDEA_RECEIVED"})
    ctx = tenants.customer_workspace_context(cid)
    from orchestrator.sqlite_manager import SQLiteManager
    sm = SQLiteManager(ctx["pipeline_db"], workspace_id=ctx["workspace_id"]); sm.connect()
    sm.upsert_task({"id":"task-control1234","workspace_id":ctx["workspace_id"],"product_id":"prod-control1234","agent_type":"analyst","status":"pending","state":"TEST","created_at":time.time(),"input_data":{}}); sm.close()

    assert est.project_control(cid, "prod-control1234", "pause")["ok"]
    state = tenants.read_customer_pipeline_state(cid)
    task = next(iter(state["task_queue"]))
    assert task["status"].lower() == "blocked"
    assert state["products"]["prod-control1234"]["factory_paused"] is True

    est.project_control(cid, "prod-control1234", "resume")
    state = tenants.read_customer_pipeline_state(cid)
    assert next(iter(state["task_queue"]))["status"].lower() == "pending"

    est.project_control(cid, "prod-control1234", "archive")
    assert tenants.read_customer_pipeline_state(cid)["products"]["prod-control1234"]["archived"] is True
    est.project_control(cid, "prod-control1234", "restore")
    assert tenants.read_customer_pipeline_state(cid)["products"]["prod-control1234"]["archived"] is False


def test_stall_detection_and_audit_log(tmp_path, monkeypatch):
    _patch_root(tmp_path, monkeypatch)
    product={"id":"prod-stall1234","updated_at":time.time()-2000}
    tasks=[{"product_id":"prod-stall1234","status":"running","created_at":time.time()-2000}]
    row=est.stall_for(product,tasks,stall_seconds=900)
    assert row["stalled"] is True
    evt=est.emit_audit("audit-customer","mission_test",product_id="prod-stall1234")
    assert evt["financial_authority"] is False
    assert est.read_audit("audit-customer")[-1]["event"] == "mission_test"


def test_tenant_snapshot_preserves_state_and_retention(tmp_path, monkeypatch):
    _patch_root(tmp_path, monkeypatch)
    cid="backup-customer"
    tenants.write_customer_product(cid,{"id":"prod-backup1234","idea":"Backup","state":"IDEA_RECEIVED"})
    first=est.tenant_snapshot(cid,retention=1)
    time.sleep(0.01)
    second=est.tenant_snapshot(cid,retention=1)
    assert Path(second["path"]).exists()
    assert est.snapshot_status(cid)["count"] == 1


def test_manager_permissions_and_disable_are_enforced(tmp_path, monkeypatch):
    _patch_root(tmp_path, monkeypatch)
    cid="govern-customer"
    manager=workforce.create_customer_personnel(cid,"research manager",role_class="manager")
    worker=workforce.create_customer_personnel(cid,"research worker",role_class="worker")
    tenants.write_customer_product(cid,{"id":"prod-govern1234","idea":"Govern","state":"IDEA_RECEIVED"})
    workforce.set_customer_personnel_enabled(cid, manager["id"], False)
    with pytest.raises(ValueError, match="disabled"):
        workforce.delegate_customer_manager_task(cid,manager_id=manager["id"],worker_id=worker["id"],product_id="prod-govern1234",directive="Research it")


def test_mission_capacity_blocks_second_concurrent_free_mission(tmp_path, monkeypatch):
    _patch_root(tmp_path, monkeypatch)
    cid="capacity-customer"
    tenants.write_customer_product(cid,{"id":"prod-active1234","idea":"Active","state":"IDEA_RECEIVED"})
    ctx=tenants.customer_workspace_context(cid)
    from orchestrator.sqlite_manager import SQLiteManager
    sm=SQLiteManager(ctx["pipeline_db"],workspace_id=ctx["workspace_id"]); sm.connect()
    sm.upsert_task({"id":"task-active1234","workspace_id":ctx["workspace_id"],"product_id":"prod-active1234","agent_type":"analyst","status":"running","state":"TEST","created_at":time.time(),"input_data":{}}); sm.close()
    with pytest.raises(ValueError, match="concurrent mission"):
        est.enforce_mission_capacity(cid,"free")


def test_isolated_synthetic_canary_exercises_mission_delegation_ultron_and_recovery():
    from web.backend.services.customer_factory_canary import _isolated_customer_journey
    result = _isolated_customer_journey()
    for key in (
        "mission_created", "five_research_lenses", "manager_stage_present",
        "ultron_stage_present", "delegation_queued", "recovery_queued", "workspace_isolation",
    ):
        assert result[key] is True
    assert result["financial_authority"] is False
