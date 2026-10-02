"""Capability, ecosystem and workload-aware Factory Floor staffing."""
from __future__ import annotations

import json
from typing import Any

from core.paths import pipeline_db_path
from orchestrator.sqlite_manager import SQLiteManager
from web.backend.services.factory_personnel import create_personnel, personnel_map
from web.backend.services.factory_routing import infer_ecosystem

_EXECUTABLE = {
    "analyst", "marketing", "methodologist", "evolution_analyst", "designer",
    "developer", "qa", "security", "devops", "pm", "architect", "sales",
}


def infer_capability(text: str) -> str:
    t = str(text or "").lower()
    pairs = [
        (("security", "safety", "risk", "threat"), "security"),
        (("deploy", "infrastructure", "server", "devops", "hosting"), "devops"),
        (("test", "qa", "quality", "verify"), "qa"),
        (("code", "developer", "build", "program", "implementation"), "developer"),
        (("design", "ux", "ui", "visual", "wireframe"), "designer"),
        (("architect", "architecture", "system design"), "architect"),
        (("sales", "funding", "finance", "revenue", "pricing"), "sales"),
        (("market", "marketing", "advertising", "campaign", "positioning"), "marketing"),
        (("method", "methodology", "experiment", "evidence"), "methodologist"),
        (("evolution", "improve", "optimization", "iterate"), "evolution_analyst"),
        (("product", "requirements", "roadmap", "manage", "oversee"), "pm"),
        (("research", "analyze", "analysis", "study", "compare"), "analyst"),
    ]
    for words, capability in pairs:
        if any(w in t for w in words):
            return capability
    return "analyst"


def _product_context(sm: SQLiteManager, product_id: str) -> tuple[str, str, str]:
    row = sm.conn.execute(
        "SELECT idea, category, state FROM products WHERE workspace_id = ? AND id = ?",
        (sm.workspace_id, product_id),
    ).fetchone()
    if row is None:
        raise ValueError("Project not found")
    idea = str(row["idea"] or "")
    ecosystem = infer_ecosystem(row["category"], idea)
    return idea, ecosystem, str(row["state"] or "IDEA_RECEIVED")


def _workload(sm: SQLiteManager) -> dict[str, int]:
    rows = sm.conn.execute(
        """SELECT COALESCE(assigned_to, agent_type) AS owner, COUNT(*) AS n
           FROM tasks WHERE workspace_id = ? AND lower(status) IN ('pending','running','blocked')
           GROUP BY COALESCE(assigned_to, agent_type)""",
        (sm.workspace_id,),
    ).fetchall()
    return {str(r["owner"]): int(r["n"] or 0) for r in rows if r["owner"]}


def ecosystem_manager_id(ecosystem: str) -> str:
    return f"ecosystem-manager:{ecosystem or 'general'}"


def choose_assignee(
    *,
    product_id: str,
    capability: str,
    directive: str = "",
    allow_temporary_specialist: bool = True,
) -> dict[str, Any]:
    cap = str(capability or "").strip() or infer_capability(directive)
    if cap not in _EXECUTABLE:
        cap = infer_capability(directive)
    sm = SQLiteManager(str(pipeline_db_path())); sm.connect()
    try:
        idea, ecosystem, state = _product_context(sm, product_id)
        roster = personnel_map()
        loads = _workload(sm)
        candidates: list[tuple[tuple[int, int, int, str], str, dict[str, Any]]] = []
        for aid, row in roster.items():
            if row.get("retired") or str(row.get("capability") or "") != cap:
                continue
            role = str(row.get("role_class") or "worker")
            if cap not in {"pm", "architect", "sales"} and role != "worker":
                continue
            member_ecosystem = str(row.get("ecosystem") or "shared")
            eco_penalty = 0 if member_ecosystem == ecosystem else (1 if member_ecosystem in {"shared", "general", ""} else 3)
            custom_penalty = 0 if row.get("custom") else 1
            candidates.append(((eco_penalty, loads.get(aid, 0), custom_penalty, aid), aid, row))
        if not candidates and allow_temporary_specialist:
            temp = create_personnel(
                f"Temporary {ecosystem} specialist for {cap}. {directive or idea}",
                role_class="manager" if cap in {"pm", "architect", "sales"} else "worker",
                label=f"{ecosystem.title()} {cap.replace('_',' ').title()} Specialist",
            )
            # Mark as ecosystem-bound + temporary without requiring a UI prompt.
            from web.backend.services.factory_personnel import update_personnel
            update_personnel(temp["id"], action="set_ecosystem", ecosystem=ecosystem)
            temp = personnel_map()[temp["id"]]
            return {
                "agent_id": temp["id"], "profile": temp, "ecosystem": ecosystem,
                "manager_id": ecosystem_manager_id(ecosystem), "temporary": True,
                "capability": cap, "state": state,
            }
        if not candidates:
            raise ValueError(f"No available AI unit can perform {cap}")
        _, aid, profile = sorted(candidates, key=lambda item: item[0])[0]
        return {
            "agent_id": aid, "profile": profile, "ecosystem": ecosystem,
            "manager_id": ecosystem_manager_id(ecosystem), "temporary": False,
            "capability": cap, "state": state,
        }
    finally:
        sm.close()


def stamp_pipeline_task(product: dict[str, Any], task: dict[str, Any]) -> dict[str, Any]:
    """Attach an actual worker identity + division manager to a canonical task."""
    agent_type = str(task.get("agent_type") or "")
    if agent_type.startswith("__"):
        return task
    pid = str(task.get("product_id") or product.get("id") or "")
    if not pid:
        return task
    try:
        selection = choose_assignee(product_id=pid, capability=agent_type, directive=str(product.get("idea") or ""))
    except Exception:
        return task
    task["assigned_to"] = selection["agent_id"]
    inp = task.setdefault("input_data", {})
    inp["factory_ecosystem"] = selection["ecosystem"]
    inp["factory_manager_id"] = selection["manager_id"]
    inp["factory_staffing_mode"] = "automatic"
    inp["factory_temporary_specialist"] = bool(selection["temporary"])
    return task
