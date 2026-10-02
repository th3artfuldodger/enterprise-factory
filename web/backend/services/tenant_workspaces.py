"""Customer tenant workspace isolation for the gamified Factory product."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Any

from core.paths import data_root
from orchestrator.sqlite_manager import SQLiteManager


def customer_workspace_id(customer_id: str) -> str:
    cid = str(customer_id or "").strip()
    if not cid:
        raise ValueError("customer_id is required")
    digest = hashlib.sha256(cid.encode("utf-8")).hexdigest()[:20]
    return f"customer-{digest}"


def tenant_root_for_customer(customer_id: str) -> Path:
    ws = customer_workspace_id(customer_id)
    root = data_root() / "tenants" / ws
    for name in ("state", "config", "specs", "arch", "code", "bugs", "logs", "telemetry", "reports"):
        (root / name).mkdir(parents=True, exist_ok=True)
    return root


def tenant_pipeline_db(customer_id: str) -> Path:
    return tenant_root_for_customer(customer_id) / "state" / "pipeline.db"


def tenant_marker(customer_id: str) -> Path:
    return tenant_root_for_customer(customer_id) / "state" / "tenant.json"


def customer_workspace_context(customer_id: str) -> dict[str, str]:
    root = tenant_root_for_customer(customer_id)
    ws = customer_workspace_id(customer_id)
    return {
        "workspace_id": ws,
        "tenant_root": str(root),
        "pipeline_db": str(root / "state" / "pipeline.db"),
    }


def write_customer_product(customer_id: str, product: dict[str, Any]) -> dict[str, Any]:
    ctx = customer_workspace_context(customer_id)
    row = dict(product)
    row["workspace_id"] = ctx["workspace_id"]
    metadata = dict(row.get("metadata") or {})
    metadata["tenant_workspace_id"] = ctx["workspace_id"]
    metadata["owner_customer_id"] = customer_id
    row["metadata"] = metadata
    manager = SQLiteManager(ctx["pipeline_db"], workspace_id=ctx["workspace_id"])
    manager.connect()
    try:
        manager.upsert_product(row)
    finally:
        manager.close()
    # Wake marker is intentionally tenant-local. The tenant supervisor watches
    # these stores and starts/reuses a worker scoped to this exact root/workspace.
    wake = Path(ctx["tenant_root"]) / "state" / ".wake"
    wake.touch(exist_ok=True)
    return row


def read_customer_pipeline_state(customer_id: str) -> dict[str, Any]:
    ctx = customer_workspace_context(customer_id)
    manager = SQLiteManager(ctx["pipeline_db"], workspace_id=ctx["workspace_id"])
    manager.connect()
    try:
        products = manager.get_all_products()
        tasks = manager.get_all_tasks()
    finally:
        manager.close()
    return {
        "workspace_id": ctx["workspace_id"],
        "products": {str(p["id"]): p for p in products if p.get("id")},
        "task_queue": tasks,
    }


def tenant_env(customer_id: str) -> dict[str, str]:
    ctx = customer_workspace_context(customer_id)
    env = dict(os.environ)
    env["AIFACTORY_WORKSPACE_ID"] = ctx["workspace_id"]
    env["AIFACTORY_DATA_ROOT"] = ctx["tenant_root"]
    env["SQLITE_PATH"] = ctx["pipeline_db"]
    env["PIPELINE_DB_BACKEND"] = "sqlite"
    env["USE_SQLITE"] = "true"
    env["PIPELINE_USE_POSTGRES"] = "false"
    env["AIFACTORY_WORKER_HEALTH_PORT"] = "0"
    # Tenant workers share only the provider configuration; generated artifacts,
    # logs and pipeline state stay under the tenant root.
    shared_providers = data_root() / "config" / "model_providers.yaml"
    if shared_providers.exists():
        env["AIFACTORY_MODEL_PROVIDERS"] = str(shared_providers)
    return env
