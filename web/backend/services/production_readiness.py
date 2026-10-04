"""Production readiness snapshot for the live Factory and tenant stores."""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from core.paths import data_root, pipeline_db_path
from orchestrator.sqlite_manager import SQLiteManager
from web.backend.services.customer_factory_canary import read_customer_factory_canary
from web.backend.services.corporate_standup import load_admin_config
from web.backend.services.factory_backup_scheduler import schedule_from_config
from web.backend.services.host_disk_monitor import disk_monitor_live_status
from web.backend.services.provider_health import local_ollama_health


def _db_paths() -> list[tuple[str, Path]]:
    out: list[tuple[str, Path]] = [("default", pipeline_db_path())]
    tenant_dir = data_root() / "tenants"
    if tenant_dir.is_dir():
        for db in sorted(tenant_dir.glob("*/state/pipeline.db")):
            out.append((db.parents[1].name, db))
    return out


def _db_status(workspace: str, path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"workspace_id": workspace, "path": str(path), "ok": True, "missing": True}
    manager = SQLiteManager(str(path), workspace_id=workspace)
    manager.connect()
    try:
        status = manager.integrity_status()
        tasks = manager.get_all_tasks()
        products = manager.get_all_products()
    finally:
        manager.close()
    counts: dict[str, int] = {}
    for task in tasks:
        key = str(task.get("status") or "pending").lower()
        counts[key] = counts.get(key, 0) + 1
    return {"workspace_id": workspace, "path": str(path), **status, "products": len(products), "tasks": len(tasks), "task_status": counts}


def production_readiness_snapshot() -> dict[str, Any]:
    now = time.time()
    provider = local_ollama_health()
    canary = read_customer_factory_canary()
    disk = disk_monitor_live_status()
    backup = schedule_from_config(load_admin_config())
    dbs = [_db_status(ws, path) for ws, path in _db_paths()]
    latest = (backup.get("on_disk_backups") or [None])[0]
    latest_age = None
    if latest and latest.get("modified_at_utc"):
        try:
            from datetime import datetime
            latest_age = max(0.0, now - datetime.fromisoformat(str(latest["modified_at_utc"])).timestamp())
        except Exception:
            latest_age = None
    canary_age = max(0.0, now - float(canary.get("checked_at") or 0)) if canary.get("checked_at") else None
    checks = {
        "provider_online": bool(provider.get("online")),
        "canary_fresh_and_green": bool(canary.get("ok")) and canary_age is not None and canary_age <= 7 * 3600,
        "databases_integrity_ok": all(bool(row.get("ok")) for row in dbs),
        "disk_not_critical": str(disk.get("level") or "ok") != "critical",
        "backup_policy_enabled": bool(backup.get("enabled")),
        "backup_recent": latest_age is not None and latest_age <= 48 * 3600,
    }
    total_tasks = sum(int(row.get("tasks") or 0) for row in dbs)
    failed_tasks = sum(int((row.get("task_status") or {}).get("failed") or 0) for row in dbs)
    return {
        "ready": all(checks.values()),
        "status": "ready" if all(checks.values()) else "degraded",
        "checked_at": now,
        "checks": checks,
        "provider": provider,
        "canary": {"ok": canary.get("ok"), "checked_at": canary.get("checked_at"), "age_seconds": canary_age, "checks": canary.get("checks") or {}},
        "backup": {"enabled": backup.get("enabled"), "time": backup.get("time"), "timezone": backup.get("timezone"), "retention": backup.get("retention"), "latest": latest, "latest_age_seconds": latest_age, "last_error": backup.get("last_error")},
        "disk": disk,
        "databases": dbs,
        "queue": {"workspaces": len(dbs), "tasks_total": total_tasks, "failed_tasks": failed_tasks},
    }


def customer_readiness_summary(customer_id: str) -> dict[str, Any]:
    """Customer-safe health summary: no other tenant paths or identifiers."""
    from web.backend.services.tenant_workspaces import customer_workspace_context
    ctx = customer_workspace_context(customer_id)
    db = _db_status(ctx["workspace_id"], Path(ctx["pipeline_db"]))
    provider = local_ollama_health()
    canary = read_customer_factory_canary()
    disk = disk_monitor_live_status()
    backup = schedule_from_config(load_admin_config())
    latest = (backup.get("on_disk_backups") or [None])[0]
    return {
        "ready": bool(provider.get("online")) and bool(canary.get("ok")) and bool(db.get("ok")) and str(disk.get("level") or "ok") != "critical",
        "provider_online": bool(provider.get("online")),
        "database_ok": bool(db.get("ok")),
        "schema_version": db.get("schema_version"),
        "disk_level": disk.get("level"),
        "canary_ok": bool(canary.get("ok")),
        "canary_checked_at": canary.get("checked_at"),
        "backup_enabled": bool(backup.get("enabled")),
        "latest_backup": latest.get("modified_at_utc") if isinstance(latest, dict) else None,
        "failed_tasks": int((db.get("task_status") or {}).get("failed") or 0),
    }
