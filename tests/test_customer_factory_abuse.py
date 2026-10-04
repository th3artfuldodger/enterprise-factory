from __future__ import annotations

import time
from pathlib import Path

import pytest
from starlette.requests import Request
from pydantic import ValidationError

from web.backend.schemas.api_requests import CustomerManagerDelegationRequest, CustomerFundingRequest
from web.backend.services import customer_factory_establishment as est
from web.backend.services import customer_task_recovery as recovery
from web.backend.services import customer_workforce as workforce
from web.backend.services import tenant_workspaces as tenants
from web.backend.http.client_ip import client_ip
from orchestrator.sqlite_manager import SQLiteManager


def _patch_root(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(tenants, "data_root", lambda: tmp_path)


def _seed_task(customer_id: str, product_id: str, task_id: str, status: str = "failed"):
    tenants.write_customer_product(customer_id, {"id": product_id, "idea": "test", "state": "IDEA_RECEIVED"})
    ctx = tenants.customer_workspace_context(customer_id)
    sm = SQLiteManager(ctx["pipeline_db"], workspace_id=ctx["workspace_id"]); sm.connect()
    try:
        sm.upsert_task({"id":task_id,"workspace_id":ctx["workspace_id"],"product_id":product_id,"agent_type":"analyst","status":status,"state":"TEST","created_at":time.time(),"input_data":{}})
    finally: sm.close()


def test_cross_tenant_retry_is_rejected(tmp_path, monkeypatch):
    _patch_root(tmp_path, monkeypatch); _seed_task("owner-b", "prod-bbbbbbbb", "task-bbbbbbbb")
    with pytest.raises(ValueError, match="not found"):
        recovery.retry_customer_task("owner-a", "task-bbbbbbbb")


def test_cross_tenant_project_control_is_rejected(tmp_path, monkeypatch):
    _patch_root(tmp_path, monkeypatch); tenants.write_customer_product("owner-b", {"id":"prod-bbbbbbbb","idea":"b","state":"IDEA_RECEIVED"})
    with pytest.raises(ValueError, match="not found"):
        est.project_control("owner-a", "prod-bbbbbbbb", "pause")


def test_manager_without_assign_permission_cannot_delegate(tmp_path, monkeypatch):
    _patch_root(tmp_path, monkeypatch); cid="perm-owner"
    manager=workforce.create_customer_personnel(cid,"research manager",role_class="manager")
    worker=workforce.create_customer_personnel(cid,"research worker",role_class="worker")
    tenants.write_customer_product(cid,{"id":"prod-perm0001","idea":"p","state":"IDEA_RECEIVED"})
    doc=workforce._read(cid); doc["profiles"][manager["id"]]["permissions"]=["perform_assigned_work"]; workforce._write(cid,doc)
    with pytest.raises(ValueError, match="assign_work"):
        workforce.delegate_customer_manager_task(cid,manager_id=manager["id"],worker_id=worker["id"],product_id="prod-perm0001",directive="do work")


def test_worker_without_work_permission_cannot_receive_delegation(tmp_path, monkeypatch):
    _patch_root(tmp_path, monkeypatch); cid="worker-perm-owner"
    manager=workforce.create_customer_personnel(cid,"research manager",role_class="manager")
    worker=workforce.create_customer_personnel(cid,"research worker",role_class="worker")
    tenants.write_customer_product(cid,{"id":"prod-worker0001","idea":"p","state":"IDEA_RECEIVED"})
    doc=workforce._read(cid); doc["profiles"][worker["id"]]["permissions"]=["request_review"]; workforce._write(cid,doc)
    with pytest.raises(ValueError, match="cannot perform"):
        workforce.delegate_customer_manager_task(cid,manager_id=manager["id"],worker_id=worker["id"],product_id="prod-worker0001",directive="do work")


def test_oversized_high_cost_payloads_are_rejected_by_schema():
    with pytest.raises(ValidationError):
        CustomerManagerDelegationRequest(worker_id="w",product_id="p",directive="x"*8001)
    with pytest.raises(ValidationError):
        CustomerFundingRequest(product_id="p",department="research",amount_usd=10_000_001,purpose="too much")


def test_x_forwarded_for_spoof_uses_rightmost_untrusted_hop(monkeypatch):
    monkeypatch.setenv("AIFACTORY_TRUSTED_PROXY_IPS","127.0.0.1,10.0.0.2")
    scope={"type":"http","method":"GET","path":"/","headers":[(b"x-forwarded-for",b"1.2.3.4, 5.6.7.8, 10.0.0.2")],"client":("127.0.0.1",1234),"server":("test",80),"scheme":"http","query_string":b""}
    assert client_ip(Request(scope)) == "5.6.7.8"
