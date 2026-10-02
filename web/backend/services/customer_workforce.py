"""Tenant-owned AI personnel and manager delegation for customer factories."""
from __future__ import annotations

import json
import re
import time
import uuid
from pathlib import Path
from typing import Any

from orchestrator.sqlite_manager import SQLiteManager
from web.backend.services.tenant_workspaces import customer_workspace_context

FORBIDDEN_FINANCIAL_PERMISSIONS = {
    "approve_funding", "spend_money", "spend_funds", "transfer_money",
    "transfer_funds", "borrow_money", "borrow_funds", "invest_money",
    "invest_funds", "contract_authority", "sign_contract", "execute_contract",
    "open_bank_account", "payout_funds",
}

_CAPABILITY_WORDS = (
    (("security", "safety", "risk"), "security", "production"),
    (("deploy", "infrastructure", "server", "devops"), "devops", "production"),
    (("test", "qa", "quality"), "qa", "production"),
    (("code", "developer", "build", "program"), "developer", "production"),
    (("design", "ux", "ui", "visual"), "designer", "production"),
    (("market", "advertising", "campaign"), "marketing", "research"),
    (("sales", "pricing", "revenue"), "sales", "funding"),
    (("method", "experiment"), "methodologist", "research"),
    (("product", "requirements", "roadmap"), "pm", "management"),
    (("research", "analyze", "analysis", "study", "competitor"), "analyst", "research"),
)


def _personnel_path(customer_id: str) -> Path:
    ctx = customer_workspace_context(customer_id)
    path = Path(ctx["tenant_root"]) / "config" / "factory_personnel.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _read(customer_id: str) -> dict[str, Any]:
    path = _personnel_path(customer_id)
    if not path.exists():
        return {"version": 1, "profiles": {}}
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(doc, dict) and isinstance(doc.get("profiles"), dict):
            return doc
    except Exception:
        pass
    return {"version": 1, "profiles": {}}


def _write(customer_id: str, doc: dict[str, Any]) -> None:
    path = _personnel_path(customer_id)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(doc, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(path)


def _infer(description: str, role_class: str | None) -> tuple[str, str, str]:
    text = description.lower()
    role = role_class if role_class in {"worker", "manager"} else (
        "manager" if any(w in text for w in ("manager", "manage", "oversee", "supervise", "lead team")) else "worker"
    )
    capability, division = "analyst", "research"
    for words, cap, div in _CAPABILITY_WORDS:
        if any(word in text for word in words):
            capability, division = cap, div
            break
    if role == "manager" and division not in {"funding", "production"}:
        division = "management" if capability in {"pm", "architect"} else division
    authority = "cross_division" if role == "manager" else "local"
    return role, capability, division


def _permissions(role: str) -> list[str]:
    if role == "manager":
        return ["assign_work", "cross_division_request", "perform_assigned_work", "request_review", "request_funding"]
    return ["perform_assigned_work", "request_review", "request_funding"]


def list_customer_personnel(customer_id: str) -> list[dict[str, Any]]:
    profiles = _read(customer_id).get("profiles") or {}
    out = []
    for agent_id, row in profiles.items():
        if not isinstance(row, dict) or row.get("retired"):
            continue
        item = {"id": agent_id, "custom": True, **row}
        item["permissions"] = [
            p for p in (item.get("permissions") or [])
            if str(p).lower() not in FORBIDDEN_FINANCIAL_PERMISSIONS
        ]
        out.append(item)
    return out


def create_customer_personnel(
    customer_id: str,
    description: str,
    *,
    role_class: str | None = None,
    label: str | None = None,
) -> dict[str, Any]:
    desc = str(description or "").strip()
    if not desc:
        raise ValueError("Describe what the AI should do")
    role, capability, division = _infer(desc, role_class)
    unit_id = f"unit-{uuid.uuid4().hex[:8]}"
    generated = label or (
        f"{capability.replace('_', ' ').title()} Manager"
        if role == "manager" else f"{capability.replace('_', ' ').title()} Worker"
    )
    now = time.time()
    row = {
        "label": generated[:80],
        "description": desc[:1000],
        "capability": capability,
        "role_class": role,
        "division": division,
        "authority": "cross_division" if role == "manager" else "local",
        "permissions": _permissions(role),
        "ecosystem": "customer",
        "created_at": now,
        "updated_at": now,
    }
    doc = _read(customer_id)
    doc.setdefault("profiles", {})[unit_id] = row
    _write(customer_id, doc)
    return {"id": unit_id, "custom": True, **row}


def _profile(customer_id: str, agent_id: str) -> dict[str, Any] | None:
    for row in list_customer_personnel(customer_id):
        if row["id"] == agent_id:
            return row
    return None


def set_customer_supervisor(customer_id: str, worker_id: str, manager_id: str) -> dict[str, Any]:
    worker = _profile(customer_id, worker_id)
    manager = _profile(customer_id, manager_id)
    if not worker or worker.get("role_class") != "worker":
        raise ValueError("Choose a tenant-owned worker AI")
    if not manager or manager.get("role_class") != "manager":
        raise ValueError("Choose a tenant-owned AI manager")
    existing = str(worker.get("supervisor_id") or "")
    if existing and existing != manager_id:
        raise ValueError("This worker already reports to another manager")
    doc = _read(customer_id)
    row = dict((doc.get("profiles") or {}).get(worker_id) or {})
    row["supervisor_id"] = manager_id
    row["supervisor_label"] = manager.get("label") or manager_id
    row["updated_at"] = time.time()
    doc.setdefault("profiles", {})[worker_id] = row
    _write(customer_id, doc)
    return {"id": worker_id, **row}


def _execution_agent(capability: str) -> str:
    allowed = {
        "analyst", "marketing", "methodologist", "designer", "developer",
        "qa", "security", "devops", "pm", "architect", "sales",
    }
    return capability if capability in allowed else "analyst"


def delegate_customer_manager_task(
    customer_id: str,
    *,
    manager_id: str,
    worker_id: str,
    product_id: str,
    directive: str,
) -> dict[str, Any]:
    manager = _profile(customer_id, manager_id)
    worker = _profile(customer_id, worker_id)
    if not manager or manager.get("role_class") != "manager":
        raise ValueError("AI manager not found in this customer Factory")
    if not worker or worker.get("role_class") != "worker":
        raise ValueError("AI worker not found in this customer Factory")
    existing = str(worker.get("supervisor_id") or "")
    if existing and existing != manager_id:
        raise ValueError("This worker already reports to another manager")
    instruction = str(directive or "").strip()
    if not instruction:
        raise ValueError("Task directive is required")

    ctx = customer_workspace_context(customer_id)
    sm = SQLiteManager(ctx["pipeline_db"], workspace_id=ctx["workspace_id"])
    sm.connect()
    try:
        product = sm.get_product(product_id)
        if not product:
            raise ValueError("Project not found in this customer Factory")
        task_id = f"task-{uuid.uuid4().hex[:12]}"
        task = {
            "id": task_id,
            "workspace_id": ctx["workspace_id"],
            "product_id": product_id,
            "agent_type": _execution_agent(str(worker.get("capability") or "analyst")),
            "assigned_to": worker_id,
            "state": "CUSTOMER_MANAGER_ASSIGNMENT",
            "status": "pending",
            "retry_count": 0,
            "max_retries": 2,
            "priority": 5,
            "created_at": time.time(),
            "input_data": {
                "factory_personnel_assignment": True,
                "manager_delegated": True,
                "delegated_by": manager_id,
                "delegated_by_label": manager.get("label"),
                "personnel_id": worker_id,
                "personnel_label": worker.get("label"),
                "personnel_capability": worker.get("capability"),
                "reports_to": manager_id,
                "reports_to_label": manager.get("label"),
                "assignment_directive": instruction[:8000],
                "workspace_id": ctx["workspace_id"],
            },
        }
        sm.upsert_task(task)
    finally:
        sm.close()
    set_customer_supervisor(customer_id, worker_id, manager_id)
    Path(ctx["tenant_root"], "state", ".wake").touch(exist_ok=True)
    return {
        "task_id": task_id,
        "manager_id": manager_id,
        "worker_id": worker_id,
        "worker_label": worker.get("label"),
        "status": "pending",
    }
