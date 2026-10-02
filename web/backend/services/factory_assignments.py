"""Create safe, non-pipeline-advancing work assignments for Factory Floor personnel."""
from __future__ import annotations

import json
import time
import uuid
from typing import Any

from core.paths import pipeline_db_path
from orchestrator.sqlite_manager import SQLiteManager
from web.backend.services.factory_personnel import personnel_map, set_supervisor


def _default_manager(profile: dict[str, Any], roster: dict[str, dict[str, Any]]) -> str:
    division = str(profile.get("division") or "general")
    preferred = {
        "research": "pm",
        "production": "architect",
        "funding": "sales",
        "management": "pm",
    }.get(division, "pm")
    if preferred in roster and not roster[preferred].get("retired"):
        return preferred
    for aid, row in roster.items():
        if row.get("role_class") == "manager" and row.get("division") == division and not row.get("retired"):
            return aid
    return "pm"


def assign_personnel_task(
    *,
    product_id: str,
    agent_id: str,
    directive: str,
    manager_id: str | None = None,
) -> dict[str, Any]:
    pid = str(product_id or "").strip()
    aid = str(agent_id or "").strip()
    text = str(directive or "").strip()
    if not pid or not aid or not text:
        raise ValueError("Project, AI unit, and assignment are required")

    roster = personnel_map()
    from web.backend.services.factory_staffing import choose_assignee, infer_capability
    auto_selected = aid in {"auto", "automatic", "best"}
    if auto_selected:
        selection = choose_assignee(
            product_id=pid,
            capability=infer_capability(text),
            directive=text,
            allow_temporary_specialist=True,
        )
        aid = str(selection["agent_id"])
        profile = dict(selection["profile"])
    else:
        profile = roster.get(aid)
    if not profile or profile.get("retired"):
        raise ValueError("AI unit is unavailable")
    capability = str(profile.get("capability") or aid)
    if capability not in {
        "analyst", "marketing", "methodologist", "evolution_analyst", "designer",
        "developer", "qa", "security", "devops", "pm", "architect", "sales",
    }:
        raise ValueError("This AI unit does not have an executable capability")

    if auto_selected:
        manager = str(manager_id or "").strip() or str(selection.get("manager_id") or "")
    else:
        manager = str(manager_id or "").strip() or _default_manager(profile, roster)
    if manager == aid:
        manager = "pm" if aid != "pm" else "architect"
    manager_profile = roster.get(manager)
    if manager.startswith("ecosystem-manager:"):
        eco = manager.split(":", 1)[1] if ":" in manager else "general"
        manager_profile = {"label": f"{eco.title()} Division Manager", "role_class": "manager", "retired": False}
    if not manager_profile or manager_profile.get("role_class") != "manager" or manager_profile.get("retired"):
        raise ValueError("Reporting manager is unavailable")

    sm = SQLiteManager(str(pipeline_db_path()))
    sm.connect()
    try:
        product = sm.conn.execute(
            "SELECT id, idea, state FROM products WHERE workspace_id = ? AND id = ?",
            (sm.workspace_id, pid),
        ).fetchone()
        if product is None:
            raise ValueError("Project not found")
        state = str(product["state"] or "IDEA_RECEIVED")
        task_id = f"personnel-{uuid.uuid4().hex[:12]}"
        now = time.time()
        payload = {
            "factory_personnel_assignment": True,
            "personnel_id": aid,
            "personnel_label": str(profile.get("label") or aid),
            "reports_to": manager,
            "reports_to_label": str(manager_profile.get("label") or manager),
            "assignment_directive": text[:8000],
            "admin_instructions": text[:8000],
            "product_id": pid,
            "idea": str(product["idea"] or ""),
            "assignment_created_at": now,
            "factory_staffing_mode": "automatic" if auto_selected else "manual",
            "factory_ecosystem": str(profile.get("ecosystem") or "shared"),
        }
        task = {
            "id": task_id,
            "product_id": pid,
            "agent_type": capability,
            "state": state,
            "status": "pending",
            "assigned_to": aid,
            "input_data": payload,
            "output_data": {},
            "created_at": now,
            "priority": -5 if profile.get("role_class") == "manager" else 1,
            "retry_count": 0,
        }
        sm.upsert_task(task)
        try:
            from web.backend.services.factory_event_journal import emit_factory_event
            emit_factory_event(
                "assignment_created", product_id=pid, source=manager, target=aid, task_id=task_id,
                status="pending", ecosystem=str(payload.get("factory_ecosystem") or "general"),
                manager_id=manager, summary=text[:500],
                metadata={"capability": capability, "staffing_mode": payload["factory_staffing_mode"]},
            )
        except Exception:
            pass
        return {
            "ok": True,
            "task_id": task_id,
            "product_id": pid,
            "agent_id": aid,
            "agent_label": str(profile.get("label") or aid),
            "manager_id": manager,
            "manager_label": str(manager_profile.get("label") or manager),
            "capability": capability,
            "status": "pending",
            "staffing_mode": "automatic" if auto_selected else "manual",
        }
    finally:
        sm.close()


def delegate_manager_task(
    *,
    manager_id: str,
    worker_id: str,
    product_id: str,
    directive: str,
) -> dict[str, Any]:
    """Let a manager add a new real queue item to one of its worker subordinates."""
    mid = str(manager_id or "").strip()
    wid = str(worker_id or "").strip()
    roster = personnel_map()
    manager = roster.get(mid)
    worker = roster.get(wid)
    if not manager or manager.get("retired") or manager.get("role_class") != "manager":
        raise ValueError("Manager AI unit is unavailable")
    if "assign_work" not in set(manager.get("permissions") or []):
        raise ValueError("This manager does not have permission to assign work")
    if not worker or worker.get("retired") or worker.get("role_class") != "worker":
        raise ValueError("Choose an available worker AI subordinate")
    existing_supervisor = str(worker.get("supervisor_id") or "").strip()
    same_division = str(worker.get("division") or "") == str(manager.get("division") or "")
    if existing_supervisor and existing_supervisor != mid:
        raise ValueError("This worker already reports to another manager")
    if not existing_supervisor and not same_division and "cross_division_request" not in set(manager.get("permissions") or []):
        raise ValueError("This manager cannot assign work across divisions")

    result = assign_personnel_task(
        product_id=product_id,
        agent_id=wid,
        directive=directive,
        manager_id=mid,
    )
    set_supervisor(wid, mid)

    sm = SQLiteManager(str(pipeline_db_path()))
    sm.connect()
    try:
        row = sm.conn.execute(
            "SELECT input FROM tasks WHERE workspace_id = ? AND id = ?",
            (sm.workspace_id, result["task_id"]),
        ).fetchone()
        if row is not None:
            raw = row["input"] if hasattr(row, "keys") else row[0]
            payload = json.loads(raw) if isinstance(raw, str) else dict(raw or {})
            payload["manager_delegated"] = True
            payload["delegated_by"] = mid
            payload["delegated_by_label"] = str(manager.get("label") or mid)
            payload["supervisor_relationship"] = True
            with sm.conn:
                sm.conn.execute(
                    "UPDATE tasks SET input = ? WHERE workspace_id = ? AND id = ?",
                    (json.dumps(payload), sm.workspace_id, result["task_id"]),
                )
    finally:
        sm.close()

    return {
        **result,
        "delegated_by": mid,
        "delegated_by_label": str(manager.get("label") or mid),
        "subordinate_id": wid,
        "subordinate_label": str(worker.get("label") or wid),
    }


def assignment_detail_from_task(row: dict[str, Any]) -> dict[str, Any] | None:
    raw = row.get("input_data") or {}
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except Exception:
            raw = {}
    if not isinstance(raw, dict) or not raw.get("factory_personnel_assignment"):
        return None
    return {
        "personnel_id": raw.get("personnel_id") or row.get("assigned_to"),
        "personnel_label": raw.get("personnel_label"),
        "reports_to": raw.get("reports_to"),
        "reports_to_label": raw.get("reports_to_label"),
        "directive": raw.get("assignment_directive") or raw.get("admin_instructions"),
    }
