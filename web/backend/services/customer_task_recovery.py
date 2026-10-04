"""Tenant-scoped recovery actions for customer Factory tasks."""
from __future__ import annotations

import time
import uuid
from pathlib import Path

from orchestrator.sqlite_manager import SQLiteManager
from web.backend.services.tenant_workspaces import customer_workspace_context


def retry_customer_task(customer_id: str, task_id: str) -> dict:
    ctx = customer_workspace_context(customer_id)
    sm = SQLiteManager(ctx["pipeline_db"], workspace_id=ctx["workspace_id"])
    sm.connect()
    try:
        task = sm.get_task(task_id)
        if not task:
            raise ValueError("Task not found in this customer Factory")
        if not sm.get_product(str(task.get("product_id") or "")):
            raise ValueError("Task project not found in this customer Factory")
        status = str(task.get("status") or "").lower()
        if status not in {"failed", "blocked"}:
            raise ValueError("Only failed or blocked tasks can be retried")
        for existing in sm.get_tasks_by_product(str(task.get("product_id") or "")):
            if str(existing.get("status") or "").lower() in {"pending", "running"}:
                if (existing.get("input_data") or {}).get("retry_of") == task_id:
                    return {"task_id": existing.get("id"), "retry_of": task_id, "status": existing.get("status"), "deduplicated": True}
        now = time.time()
        new_id = f"task-{uuid.uuid4().hex[:12]}"
        inp = dict(task.get("input_data") or {})
        inp["retry_of"] = task_id
        inp["recovery_requested_at"] = now
        clone = {
            "id": new_id, "workspace_id": ctx["workspace_id"],
            "product_id": task.get("product_id"), "agent_type": task.get("agent_type"),
            "assigned_to": task.get("assigned_to"), "state": task.get("state"),
            "status": "pending", "priority": task.get("priority") or 0,
            "retry_count": int(task.get("retry_count") or 0) + 1,
            "created_at": now, "input_data": inp,
        }
        sm.upsert_task(clone)
    finally:
        sm.close()
    Path(ctx["tenant_root"], "state", ".wake").touch(exist_ok=True)
    return {"task_id": new_id, "retry_of": task_id, "status": "pending", "deduplicated": False}
