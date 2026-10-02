"""Operator controls for Factory Floor projects.

Actions are intentionally reversible where possible. "terminate" stops work and marks
CANCELLED while preserving product history and artifacts for audit/backtrace.
"""
from __future__ import annotations

import time
from typing import Any

from core.paths import pipeline_db_path
from orchestrator.sqlite_manager import SQLiteManager
from web.backend.services.product_followup import (
    read_followup,
    set_product_factory_priority,
    set_product_pipeline_on_hold,
    write_followup,
)

_PRIORITY_VALUE = {"critical": -20, "high": -10, "low": 20}


def _emit_control_event(product_id: str, action: str, *, status: str, summary: str = "", metadata: dict[str, Any] | None = None) -> None:
    try:
        from web.backend.services.factory_event_journal import emit_factory_event
        emit_factory_event(
            f"project_{action}", product_id=product_id, source="operator", target=None,
            status=status, summary=summary or action, metadata=metadata or {},
        )
    except Exception:
        pass


def control_factory_product(
    product_id: str,
    *,
    action: str,
    priority: str | None = None,
    reason: str = "",
) -> dict[str, Any]:
    pid = str(product_id or "").strip()
    if not pid:
        raise ValueError("Product id is required")

    sm = SQLiteManager(str(pipeline_db_path()))
    sm.connect()
    try:
        row = sm.conn.execute(
            "SELECT id, state, idea FROM products WHERE workspace_id = ? AND id = ?",
            (sm.workspace_id, pid),
        ).fetchone()
        if row is None:
            raise ValueError("Product not found")
        state = str(row["state"] or "")
        state_u = state.upper()
        now = time.time()

        if action == "pause":
            set_product_pipeline_on_hold(pid, True)
            _emit_control_event(pid, action, status="paused", summary="Project paused from Factory Floor")
            return {"product_id": pid, "action": action, "ok": True, "state": state, "paused": True}

        if action == "resume":
            if state_u == "CANCELLED":
                raise ValueError("Cancelled projects cannot be resumed; reopen them from the pipeline first")
            set_product_pipeline_on_hold(pid, False)
            _emit_control_event(pid, action, status="active", summary="Project resumed from Factory Floor")
            return {"product_id": pid, "action": action, "ok": True, "state": state, "paused": False}

        if action == "set_priority":
            level = str(priority or "normal").strip().lower()
            if level not in {"normal", "high", "critical", "low"}:
                raise ValueError("Priority must be normal, high, critical, or low")
            override = None if level == "normal" else _PRIORITY_VALUE[level]
            set_product_factory_priority(pid, level, override)
            if override is not None:
                with sm.conn:
                    sm.conn.execute(
                        "UPDATE tasks SET priority = ? WHERE workspace_id = ? AND product_id = ? AND lower(status) IN ('pending','running')",
                        (override, sm.workspace_id, pid),
                    )
            _emit_control_event(pid, action, status="priority_changed", summary=f"Priority set to {level}", metadata={"priority": level})
            return {"product_id": pid, "action": action, "ok": True, "state": state, "priority": level}

        if action == "terminate":
            if state_u in {"COMPLETED", "DEPLOYED_PRODUCTION"}:
                raise ValueError("Completed projects are preserved; use storefront controls instead of terminating them")
            note = (reason or "Stopped from Factory Floor").strip()[:2000]
            with sm.conn:
                sm.conn.execute(
                    """UPDATE tasks
                       SET status = 'cancelled', completed_at = COALESCE(completed_at, ?), error = COALESCE(error, ?)
                       WHERE workspace_id = ? AND product_id = ? AND lower(status) IN ('pending','running','blocked')""",
                    (now, note, sm.workspace_id, pid),
                )
                sm.conn.execute(
                    """UPDATE products
                       SET state = 'CANCELLED', updated_at = ?, current_task_id = NULL, error = ?
                       WHERE workspace_id = ? AND id = ?""",
                    (now, note, sm.workspace_id, pid),
                )
            set_product_pipeline_on_hold(pid, True)
            meta = read_followup(pid) or {}
            meta["factory_terminated_at"] = now
            meta["factory_terminated_reason"] = note
            write_followup(pid, meta)
            _emit_control_event(pid, action, status="cancelled", summary=note)
            return {"product_id": pid, "action": action, "ok": True, "state": "CANCELLED", "paused": True}

        raise ValueError("Unknown Factory Floor action")
    finally:
        sm.close()
