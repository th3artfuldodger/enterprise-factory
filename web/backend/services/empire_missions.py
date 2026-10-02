"""Turn a customer prompt into a real department research mission."""
from __future__ import annotations

import time
import uuid
from typing import Any

from orchestrator.sqlite_manager import SQLiteManager
from web.backend.services.empire_architecture import (
    DEPARTMENTS,
    RESEARCH_AGENT_KINDS,
    ULTRON_ID,
    department_manager_id,
    research_agent_id,
)
from web.backend.services.tenant_workspaces import customer_workspace_context

_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("health_wellness", ("health", "medical", "wellness", "fitness", "patient", "doctor", "nutrition")),
    ("personal_safety", ("safety", "preparedness", "emergency", "security", "disaster")),
    ("personal_finance", ("finance", "budget", "money", "invest", "bank", "debt", "credit")),
    ("small_business", ("small business", "local business", "restaurant", "service business", "shop")),
    ("education_learning", ("education", "school", "student", "teacher", "learn", "course")),
    ("careers_employment", ("career", "job", "employment", "resume", "hiring", "recruit")),
    ("home_household", ("home", "household", "apartment", "maintenance", "cleaning")),
    ("pets", ("pet", "dog", "cat", "veterinary", "animal")),
    ("automotive_transportation", ("car", "auto", "vehicle", "transportation", "driving", "mobility")),
    ("gaming_digital_assets", ("game", "gaming", "digital asset", "esports")),
    ("creators_social_media", ("creator", "social media", "instagram", "youtube", "tiktok", "influencer")),
    ("ecommerce_digital_products", ("ecommerce", "e-commerce", "online store", "digital product", "etsy")),
    ("travel_local_experiences", ("travel", "trip", "tourism", "hotel", "local experience")),
    ("productivity_organization", ("productivity", "organize", "workflow", "task", "schedule", "calendar")),
    ("entertainment_hobbies", ("entertainment", "hobby", "music", "movie", "sports", "collect")),
)


def infer_department(prompt: str) -> str:
    text = str(prompt or "").lower()
    best = ("small_business", 0)
    for slug, words in _KEYWORDS:
        score = sum(1 for word in words if word in text)
        if score > best[1]:
            best = (slug, score)
    return best[0]


def _department_label(slug: str) -> str:
    for row in DEPARTMENTS:
        if row["slug"] == slug:
            return row["label"]
    return slug.replace("_", " ").title()


def create_customer_mission(customer_id: str, prompt: str) -> dict[str, Any]:
    mission = str(prompt or "").strip()
    if len(mission) < 8:
        raise ValueError("Mission prompt is too short")
    ctx = customer_workspace_context(customer_id)
    ws = ctx["workspace_id"]
    department = infer_department(mission)
    manager_id = department_manager_id(department)
    product_id = f"prod-{uuid.uuid4().hex[:12]}"
    now = time.time()
    product = {
        "id": product_id,
        "workspace_id": ws,
        "idea": mission[:8000],
        "admin_instructions": "Empire mission: complete five-lens research, manager review, and independent Ultron audit before canonical production.",
        "delivery_profile": "full_software",
        "production_mode": False,
        "category": department,
        "tags": ["empire-mission", department],
        "state": "IDEA_RECEIVED",
        "created_at": now,
        "updated_at": now,
        "tasks": [],
        "spec": None,
        "architecture": None,
        "code": None,
        "marketing": None,
        "pricing": None,
        "evolution_history": [],
        "empire_department": department,
        "metadata": {
            "owner_customer_id": customer_id,
            "tenant_workspace_id": ws,
            "empire_department": department,
            "empire_research_required": True,
        },
    }

    tasks: list[dict[str, Any]] = []
    for index, agent in enumerate(RESEARCH_AGENT_KINDS):
        lens = agent["slug"]
        tasks.append(
            {
                "id": f"task-{uuid.uuid4().hex[:12]}",
                "workspace_id": ws,
                "product_id": product_id,
                "agent_type": "analyst",
                "assigned_to": research_agent_id(department, lens),
                "state": "EMPIRE_RESEARCH",
                "status": "pending",
                "retry_count": 0,
                "max_retries": 2,
                "priority": index,
                "created_at": now + index * 0.001,
                "input_data": {
                    "factory_personnel_assignment": True,
                    "personnel_id": research_agent_id(department, lens),
                    "personnel_label": f"{_department_label(department)} · {agent['label']}",
                    "personnel_capability": "analyst",
                    "reports_to": manager_id,
                    "reports_to_label": f"{_department_label(department)} Manager",
                    "assignment_directive": f"{agent['mission']} Mission: {mission}",
                    "empire_research_lens": lens,
                    "empire_department": department,
                    "workspace_id": ws,
                },
            }
        )

    tasks.append(
        {
            "id": f"task-{uuid.uuid4().hex[:12]}",
            "workspace_id": ws,
            "product_id": product_id,
            "agent_type": "__department_manager_review__",
            "assigned_to": manager_id,
            "state": "EMPIRE_MANAGER_REVIEW",
            "status": "pending",
            "retry_count": 0,
            "max_retries": 1,
            "priority": 10,
            "created_at": now + 0.010,
            "input_data": {
                "manager_id": manager_id,
                "department": department,
                "workspace_id": ws,
            },
        }
    )
    tasks.append(
        {
            "id": f"task-{uuid.uuid4().hex[:12]}",
            "workspace_id": ws,
            "product_id": product_id,
            "agent_type": "__ultron_review__",
            "assigned_to": ULTRON_ID,
            "state": "ULTRON_REVIEW",
            "status": "pending",
            "retry_count": 0,
            "max_retries": 1,
            "priority": 11,
            "created_at": now + 0.011,
            "input_data": {
                "department": department,
                "workspace_id": ws,
                "independent_review": True,
            },
        }
    )

    sm = SQLiteManager(ctx["pipeline_db"], workspace_id=ws)
    sm.connect()
    try:
        sm.upsert_product(product)
        for task in tasks:
            sm.upsert_task(task)
    finally:
        sm.close()

    return {
        "product_id": product_id,
        "workspace_id": ws,
        "department": department,
        "department_label": _department_label(department),
        "department_manager_id": manager_id,
        "research_agents": [
            {
                "id": research_agent_id(department, agent["slug"]),
                "lens": agent["slug"],
                "label": agent["label"],
            }
            for agent in RESEARCH_AGENT_KINDS
        ],
        "task_ids": [task["id"] for task in tasks],
        "status": "research_queued",
    }
