"""Factory Floor routing intelligence and ecosystem policy metadata.

This layer describes the canonical pipeline's current owner and next destination,
then overlays ecosystem-specific supervision/approval policy without changing the
underlying pipeline state machine.
"""
from __future__ import annotations

from typing import Any

from orchestrator.pipeline_flow import PIPELINE_AGENT_FLOW

ECOSYSTEMS: dict[str, dict[str, Any]] = {
    "health": {
        "label": "HEALTH",
        "accent": "#2dd4bf",
        "manager_label": "Health Division Manager",
        "approval_rules": ["methodology_review", "safety_review", "human_release_approval"],
        "description": "Clinical / wellness / medical products",
    },
    "science": {
        "label": "SCIENCE",
        "accent": "#38bdf8",
        "manager_label": "Science Division Manager",
        "approval_rules": ["methodology_review", "evidence_review", "manager_release_approval"],
        "description": "Research / laboratory / technical discovery",
    },
    "commerce": {
        "label": "COMMERCE / ETSY",
        "accent": "#fb7185",
        "manager_label": "Commerce Division Manager",
        "approval_rules": ["market_review", "pricing_review", "launch_approval"],
        "description": "Marketplace / retail / ecommerce products",
    },
    "weapons": {
        "label": "DEFENSE",
        "accent": "#f97316",
        "manager_label": "Defense Division Manager",
        "approval_rules": ["safety_review", "security_review", "command_release_approval"],
        "description": "Defense / tactical projects",
    },
    "general": {
        "label": "GENERAL",
        "accent": "#a78bfa",
        "manager_label": "General Division Manager",
        "approval_rules": ["manager_review", "release_approval"],
        "description": "General product development",
    },
}

_AGENT_GROUP = {
    "analyst": "research",
    "marketing": "research",
    "methodologist": "research",
    "evolution_analyst": "research",
    "pm": "management",
    "architect": "management",
    "design_critic": "management",
    "designer": "production",
    "developer": "production",
    "hardening": "production",
    "qa": "production",
    "security": "production",
    "devops": "production",
    "sales": "funding",
    "__human_gate__": "approval",
    "__runtime_test__": "production",
    "__complete__": "complete",
}

_TERMINAL = {"COMPLETED", "DEPLOYED_PRODUCTION", "FAILED", "CANCELLED"}


def infer_ecosystem(category: Any, idea: str) -> str:
    text = f"{category or ''} {idea or ''}".lower()
    if any(k in text for k in ("health", "medical", "wellness", "clinical")):
        return "health"
    if any(k in text for k in ("weapon", "defense", "defence", "tactical")):
        return "weapons"
    if any(k in text for k in ("etsy", "ecommerce", "e-commerce", "marketplace", "retail")):
        return "commerce"
    if any(k in text for k in ("science", "research", "lab", "biotech")):
        return "science"
    return "general"


def ecosystem_config(name: str | None) -> dict[str, Any]:
    key = str(name or "general").strip().lower()
    base = ECOSYSTEMS.get(key) or ECOSYSTEMS["general"]
    return {"id": key if key in ECOSYSTEMS else "general", **base}


def route_plan(
    *,
    product_state: str,
    ecosystem: str,
    active_task: dict[str, Any] | None = None,
    paused: bool = False,
) -> dict[str, Any]:
    state = str(product_state or "IDEA_RECEIVED").upper()
    eco = ecosystem_config(ecosystem)
    flow = PIPELINE_AGENT_FLOW.get(state)
    current_owner = str((active_task or {}).get("assigned_to") or (active_task or {}).get("agent_type") or (flow[0] if flow else "")) or None
    next_state = str(flow[1]) if flow else None
    next_flow = PIPELINE_AGENT_FLOW.get(next_state or "") if next_state else None
    next_owner = str(next_flow[0]) if next_flow else None

    if state in _TERMINAL:
        route_status = "terminal"
        waiting_on = None
    elif paused:
        route_status = "paused"
        waiting_on = "operator_resume"
    elif state == "HUMAN_REVIEW_PENDING" or current_owner == "__human_gate__":
        route_status = "awaiting_approval"
        waiting_on = "human_release_approval"
    elif active_task and str(active_task.get("status") or "").lower() == "blocked":
        route_status = "blocked"
        waiting_on = "blocked_task_resolution"
    elif active_task:
        route_status = "active"
        waiting_on = None
    elif flow:
        route_status = "queued"
        waiting_on = "next_worker_pickup"
    else:
        route_status = "unrouted"
        waiting_on = "routing_review"

    current_group = _AGENT_GROUP.get(str(current_owner or ""), "general")
    next_group = _AGENT_GROUP.get(str(next_owner or ""), "complete" if next_state == "COMPLETED" else "general")
    crossing_division = bool(current_owner and next_owner and current_group != next_group)

    return {
        "routing_mode": "automatic",
        "route_status": route_status,
        "current_state": state,
        "current_stage": current_group,
        "current_owner": current_owner,
        "next_state": next_state,
        "next_stage": next_group,
        "next_owner": next_owner,
        "waiting_on": waiting_on,
        "crossing_division": crossing_division,
        "ecosystem": eco["id"],
        "ecosystem_manager_id": f"ecosystem-manager:{eco['id']}",
        "ecosystem_manager_label": eco["manager_label"],
        "approval_rules": list(eco["approval_rules"]),
    }


def ecosystem_nodes() -> list[dict[str, Any]]:
    nodes: list[dict[str, Any]] = []
    for key, raw in ECOSYSTEMS.items():
        nodes.append({
            "id": f"ecosystem-manager:{key}",
            "kind": "ecosystem_manager",
            "label": raw["manager_label"],
            "status": "idle",
            "prompt_line": raw["description"],
            "provider": "factory",
            "model": "division_supervisor",
            "role_class": "manager",
            "division": f"ecosystem:{key}",
            "authority": "ecosystem",
            "permissions": ["route_division_work", "review_division_handoffs", "request_cross_division_support"],
            "capability": "division_supervisor",
            "ecosystem": key,
            "approval_rules": list(raw["approval_rules"]),
            "virtual_personnel": True,
            "package_state": "idle",
            "package_progress": 0,
            "next_destination": "division_work",
        })
    return nodes
