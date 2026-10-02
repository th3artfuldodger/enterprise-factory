from pathlib import Path

import pytest

from web.backend.services import customer_workforce as workforce
from web.backend.services import tenant_workspaces as tenants


def _patch_roots(tmp_path, monkeypatch):
    monkeypatch.setattr(tenants, "data_root", lambda: tmp_path)
    monkeypatch.setattr(
        workforce,
        "customer_workspace_context",
        lambda cid: tenants.customer_workspace_context(cid),
    )


def test_customer_personnel_are_tenant_owned(tmp_path, monkeypatch):
    _patch_roots(tmp_path, monkeypatch)
    a = workforce.create_customer_personnel("a", "manager who oversees competitor research", role_class="manager")
    b = workforce.create_customer_personnel("b", "worker who researches competitors", role_class="worker")
    assert {p["id"] for p in workforce.list_customer_personnel("a")} == {a["id"]}
    assert {p["id"] for p in workforce.list_customer_personnel("b")} == {b["id"]}
    assert "approve_funding" not in a["permissions"]
    assert "request_funding" in a["permissions"]


def test_customer_manager_delegates_only_inside_same_tenant(tmp_path, monkeypatch):
    _patch_roots(tmp_path, monkeypatch)
    cid = "tenant-a"
    other = "tenant-b"
    manager = workforce.create_customer_personnel(cid, "manager who oversees research", role_class="manager")
    worker = workforce.create_customer_personnel(cid, "worker who researches competitors", role_class="worker")
    foreign = workforce.create_customer_personnel(other, "worker who researches competitors", role_class="worker")

    tenants.write_customer_product(
        cid,
        {"id": "prod-owned1234", "idea": "Owned", "state": "IDEA_RECEIVED", "metadata": {}},
    )
    tenants.write_customer_product(
        other,
        {"id": "prod-other1234", "idea": "Other", "state": "IDEA_RECEIVED", "metadata": {}},
    )

    result = workforce.delegate_customer_manager_task(
        cid,
        manager_id=manager["id"],
        worker_id=worker["id"],
        product_id="prod-owned1234",
        directive="Compare the three strongest competitors.",
    )
    assert result["status"] == "pending"
    roster = workforce.list_customer_personnel(cid)
    updated_worker = next(row for row in roster if row["id"] == worker["id"])
    assert updated_worker["supervisor_id"] == manager["id"]

    with pytest.raises(ValueError, match="worker"):
        workforce.delegate_customer_manager_task(
            cid,
            manager_id=manager["id"],
            worker_id=foreign["id"],
            product_id="prod-owned1234",
            directive="Cross-tenant attempt",
        )

    with pytest.raises(ValueError, match="Project"):
        workforce.delegate_customer_manager_task(
            cid,
            manager_id=manager["id"],
            worker_id=worker["id"],
            product_id="prod-other1234",
            directive="Cross-tenant project attempt",
        )
