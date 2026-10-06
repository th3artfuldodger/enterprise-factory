from __future__ import annotations
import time
import pytest
from web.backend.services import customer_factory_establishment as est
from web.backend.services import tenant_workspaces as tenants
from orchestrator.sqlite_manager import SQLiteManager

def patch_root(tmp_path, monkeypatch): monkeypatch.setattr(tenants,"data_root",lambda:tmp_path)

def test_plan_limits_are_monotonic():
    names=["free","maker","studio","enterprise"]
    keys=["projects","personnel","managers","active_tasks","concurrent_missions","retries_per_hour","history","llm_cost_usd","delegations_per_project","auto_delegations_per_project"]
    for key in keys:
        vals=[est.limits_for(n)[key] for n in names]
        assert vals==sorted(vals), (key, vals)

def test_unknown_plan_falls_back_to_free(): assert est.limits_for("bogus")==est.limits_for("free")

def test_manual_and_auto_delegation_caps(tmp_path,monkeypatch):
    patch_root(tmp_path,monkeypatch); cid="loop-guard"
    tenants.write_customer_product(cid,{"id":"prod-loop1234","idea":"loop","state":"IDEA_RECEIVED"})
    ctx=tenants.customer_workspace_context(cid); sm=SQLiteManager(ctx["pipeline_db"],workspace_id=ctx["workspace_id"]); sm.connect()
    try:
      for i in range(est.limits_for("free")["auto_delegations_per_project"]):
        sm.upsert_task({"id":f"task-loop{i:04d}","workspace_id":ctx["workspace_id"],"product_id":"prod-loop1234","agent_type":"analyst","status":"completed","state":"TEST","created_at":time.time(),"input_data":{"manager_delegated":True}})
    finally: sm.close()
    with pytest.raises(ValueError,match="automatic delegation"): est.enforce_delegation_loop_guard(cid,"prod-loop1234","free",automatic=True)
    est.enforce_delegation_loop_guard(cid,"prod-loop1234","free",automatic=False)

def test_customer_cost_guard_blocks_at_plan_ceiling(monkeypatch):
    monkeypatch.setattr(est,"usage_summary",lambda *a,**k:{"llm_estimated_cost_usd":2.0})
    with pytest.raises(ValueError,match="cost ceiling"): est.enforce_customer_cost_guard("c","free")
