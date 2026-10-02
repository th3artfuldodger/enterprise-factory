"""Manager report-back controls for Factory Floor personnel assignments."""
from __future__ import annotations

import json
import time
import uuid
from typing import Any

from core.paths import pipeline_db_path
from orchestrator.sqlite_manager import SQLiteManager
from web.backend.services.factory_personnel import personnel_map

_OPEN = {"awaiting_manager", "escalated"}


def _json_obj(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str) and value:
        try:
            parsed = json.loads(value)
            return dict(parsed) if isinstance(parsed, dict) else {}
        except Exception:
            return {}
    return {}


def _load_assignment(sm: SQLiteManager, task_id: str) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    row = sm.conn.execute(
        "SELECT * FROM tasks WHERE workspace_id = ? AND id = ?",
        (sm.workspace_id, task_id),
    ).fetchone()
    if row is None:
        raise ValueError("Assignment report not found")
    task = dict(row)
    inp = _json_obj(task.get("input"))
    out = _json_obj(task.get("output"))
    if not inp.get("factory_personnel_assignment"):
        raise ValueError("This task is not a Factory Floor personnel assignment")
    return task, inp, out


def review_assignment_report(
    task_id: str,
    *,
    action: str,
    feedback: str = "",
) -> dict[str, Any]:
    tid = str(task_id or "").strip()
    if not tid:
        raise ValueError("Assignment report is required")
    if action not in {"accept", "send_back", "escalate", "incorporate"}:
        raise ValueError("Unknown report action")

    sm = SQLiteManager(str(pipeline_db_path()))
    sm.connect()
    try:
        task, inp, out = _load_assignment(sm, tid)
        status = str(out.get("factory_report_status") or "awaiting_manager")
        if status not in _OPEN:
            raise ValueError("This report has already been resolved")

        now = time.time()
        manager_id = str(inp.get("reports_to") or "pm")
        worker_id = str(inp.get("personnel_id") or task.get("assigned_to") or task.get("agent_type") or "")
        pid = str(task.get("product_id") or "")
        note = str(feedback or "").strip()[:4000]
        roster = personnel_map()

        out["factory_report_reviewed_at"] = now
        out["factory_report_reviewed_by"] = manager_id
        if note:
            out["factory_manager_feedback"] = note

        created_task_id: str | None = None
        if action == "accept":
            out["factory_report_status"] = "accepted"
        elif action == "incorporate":
            out["factory_report_status"] = "incorporated"
            prow = sm.conn.execute(
                "SELECT generic_metadata FROM products WHERE workspace_id = ? AND id = ?",
                (sm.workspace_id, pid),
            ).fetchone()
            meta = _json_obj(prow["generic_metadata"] if prow else None)
            reports = meta.get("factory_incorporated_reports")
            if not isinstance(reports, list):
                reports = []
            reports.append({
                "assignment_task_id": tid,
                "worker_id": worker_id,
                "manager_id": manager_id,
                "directive": inp.get("assignment_directive"),
                "result": out.get("factory_assignment_result", out),
                "incorporated_at": now,
            })
            meta["factory_incorporated_reports"] = reports[-20:]
            with sm.conn:
                sm.conn.execute(
                    "UPDATE products SET generic_metadata = ?, updated_at = ? WHERE workspace_id = ? AND id = ?",
                    (json.dumps(meta), now, sm.workspace_id, pid),
                )
        elif action == "send_back":
            out["factory_report_status"] = "sent_back"
            if not note:
                note = "Manager requested another pass. Improve the work and report back again."
            created_task_id = f"personnel-{uuid.uuid4().hex[:12]}"
            new_input = dict(inp)
            new_input["assignment_parent_task_id"] = tid
            new_input["assignment_created_at"] = now
            new_input["assignment_directive"] = (
                f"{str(inp.get('assignment_directive') or '').strip()}\n\n"
                f"MANAGER FEEDBACK: {note}"
            )[:8000]
            new_input["admin_instructions"] = new_input["assignment_directive"]
            new_task = {
                "id": created_task_id,
                "product_id": pid,
                "agent_type": str(task.get("agent_type") or "analyst"),
                "state": str(task.get("state") or "IDEA_RECEIVED"),
                "status": "pending",
                "assigned_to": worker_id,
                "input_data": new_input,
                "output_data": {},
                "created_at": now,
                "priority": int(task.get("priority") or 1),
                "retry_count": 0,
            }
            sm.upsert_task(new_task)
        else:  # escalate
            out["factory_report_status"] = "escalated"
            out["factory_escalated_from"] = manager_id
            out["factory_escalated_to"] = "external_agent"
            out["factory_escalation_note"] = note or "Escalated for command-level review"

        with sm.conn:
            sm.conn.execute(
                "UPDATE tasks SET output = ? WHERE workspace_id = ? AND id = ?",
                (json.dumps(out), sm.workspace_id, tid),
            )

        try:
            from web.backend.services.factory_event_journal import emit_factory_event
            event_target = (
                worker_id if action == "send_back"
                else "external_agent" if action == "escalate"
                else manager_id
            )
            emit_factory_event(
                f"report_{action}", product_id=pid, source=manager_id, target=event_target,
                task_id=tid, status=str(out.get("factory_report_status") or action),
                manager_id=manager_id, summary=note or f"Manager {action} report",
                metadata={"worker_id": worker_id, "next_task_id": created_task_id},
            )
        except Exception:
            pass

        return {
            "ok": True,
            "task_id": tid,
            "action": action,
            "report_status": out.get("factory_report_status"),
            "product_id": pid,
            "worker_id": worker_id,
            "manager_id": manager_id,
            "next_task_id": created_task_id,
            "manager_label": str((roster.get(manager_id) or {}).get("label") or manager_id),
        }
    finally:
        sm.close()
