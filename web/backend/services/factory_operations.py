from __future__ import annotations

import time
from typing import Any

_TERMINAL = {"COMPLETED", "DEPLOYED_PRODUCTION", "CANCELLED", "FAILED"}


def build_operational_alerts(*, product_nodes: list[dict[str, Any]], active_tasks: list[dict[str, Any]], open_reports: list[dict[str, Any]], base_alerts: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, list[dict[str, Any]]]]:
    now = time.time()
    alerts: list[dict[str, Any]] = []
    seen: set[str] = set()

    def add(row: dict[str, Any]) -> None:
        key = str(row.get("id") or "")
        if key and key not in seen:
            seen.add(key)
            alerts.append(row)

    by_pid = {str(n.get("product_id") or ""): n for n in product_nodes if n.get("product_id")}
    for old in base_alerts:
        row = dict(old)
        nxt = str(row.get("next_required_action") or "")
        row.setdefault("action_type", "human_review" if "approval" in nxt else "system_intervention")
        row.setdefault("recommended_action", "Review and resolve")
        product_node = by_pid.get(str(row.get("product_id") or "")) or {}
        row.setdefault("manager_id", product_node.get("ecosystem_manager_id") or "external_agent")
        row.setdefault("ecosystem", product_node.get("ecosystem") or row.get("origin_division") or "general")
        add(row)

    for pid, node in by_pid.items():
        state = str(node.get("product_state") or "").upper()
        manager_id = str(node.get("ecosystem_manager_id") or "ecosystem-manager:general")
        common = {
            "origin_division": node.get("ecosystem") or node.get("division") or "general",
            "origin_agent": node.get("current_owner") or node.get("assigned_agent") or node.get("last_agent"),
            "product_id": pid,
            "package_label": node.get("label"),
            "objective": node.get("prompt_line") or node.get("label"),
            "manager_id": manager_id,
            "ecosystem": node.get("ecosystem") or "general",
        }
        if node.get("pipeline_paused") and state not in _TERMINAL:
            add({"id": f"ops:paused:{pid}", "severity": "warning", "action_type": "resume_project", "next_required_action": "resume_or_hold", "recommended_action": "Resume when ready or leave intentionally paused", **common})
        if str(node.get("route_status") or "") == "unrouted":
            add({"id": f"ops:unrouted:{pid}", "severity": "stop", "action_type": "routing_review", "next_required_action": "routing_review", "recommended_action": "Inspect stage and assign a route", **common})
        if node.get("crossing_division"):
            add({"id": f"ops:cross-division:{pid}", "severity": "info", "action_type": "cross_division_handoff", "next_required_action": "manager_visibility", "recommended_action": "No action required unless handoff stalls", **common})

    for task in active_tasks:
        pid = str(task.get("product_id") or "")
        node = by_pid.get(pid) or {}
        created = float(task.get("created_at") or 0)
        started = float(task.get("started_at") or 0)
        status = str(task.get("status") or "").lower()
        age = max(0.0, now - (started or created or now))
        retries = int(task.get("retry_count") or 0)
        manager_id = str(node.get("ecosystem_manager_id") or "ecosystem-manager:general")
        common = {"origin_division": node.get("ecosystem") or "general", "origin_agent": task.get("assigned_to") or task.get("agent_type"), "product_id": pid, "package_label": node.get("label"), "manager_id": manager_id, "ecosystem": node.get("ecosystem") or "general", "objective": node.get("prompt_line")}
        if status == "blocked":
            add({"id": f"ops:blocked:{task.get('id')}", "severity": "stop", "action_type": "blocked_task", "next_required_action": "manager_intervention", "recommended_action": "Inspect blocker, reassign or escalate", "age_seconds": age, **common})
        elif (status == "running" and age > 3600) or (status == "pending" and age > 1800):
            add({"id": f"ops:stale:{task.get('id')}", "severity": "warning", "action_type": "stale_task", "next_required_action": "prioritize_or_reassign", "recommended_action": "Raise priority or reassign the work", "age_seconds": age, **common})
        if retries >= 2:
            add({"id": f"ops:rework:{task.get('id')}", "severity": "warning", "action_type": "rework_loop", "next_required_action": "manager_review", "recommended_action": "Review repeated failure and change approach", "retry_count": retries, **common})

    inboxes: dict[str, list[dict[str, Any]]] = {}
    for report in open_reports:
        inp = report.get("assignment_input") or {}
        outp = report.get("assignment_output") or {}
        manager_id = str(inp.get("reports_to") or "ecosystem-manager:general")
        inboxes.setdefault(manager_id, []).append({"id": f"inbox:report:{report.get('id')}", "kind": "assignment_report", "manager_id": manager_id, "product_id": report.get("product_id"), "task_id": report.get("id"), "worker_id": inp.get("personnel_id") or report.get("assigned_to"), "title": inp.get("personnel_label") or report.get("agent_type") or "AI report", "summary": inp.get("assignment_directive") or "Completed assignment awaiting review", "status": outp.get("factory_report_status") or "awaiting_manager", "actions": ["accept", "incorporate", "send_back", "escalate"], "created_at": report.get("completed_at") or report.get("created_at")})

    for alert in alerts:
        if alert.get("action_type") == "cross_division_handoff":
            continue
        manager_id = str(alert.get("manager_id") or "external_agent")
        inboxes.setdefault(manager_id, []).append({"id": f"inbox:{alert['id']}", "kind": "exception", "manager_id": manager_id, "product_id": alert.get("product_id"), "title": alert.get("package_label") or alert.get("action_type") or "Factory exception", "summary": alert.get("recommended_action") or alert.get("objective") or "Review required", "status": alert.get("action_type"), "actions": [alert.get("action_type")], "severity": alert.get("severity")})

    for key, items in inboxes.items():
        items.sort(key=lambda x: float(x.get("created_at") or 0), reverse=True)
        inboxes[key] = items[:50]
    return alerts, inboxes
