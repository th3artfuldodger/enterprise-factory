"""Persistent Factory Floor personnel profiles and lightweight authority controls."""
from __future__ import annotations

import json
import re
import time
import uuid
from pathlib import Path
from typing import Any

from core.paths import data_root

CANONICAL: dict[str, dict[str, Any]] = {
    "analyst": {"label": "Market Analyst", "capability": "analyst", "role_class": "worker", "division": "research", "authority": "local"},
    "marketing": {"label": "Marketing", "capability": "marketing", "role_class": "worker", "division": "research", "authority": "local"},
    "methodologist": {"label": "Methodologist", "capability": "methodologist", "role_class": "worker", "division": "research", "authority": "local"},
    "evolution_analyst": {"label": "Evolution", "capability": "evolution_analyst", "role_class": "worker", "division": "research", "authority": "local"},
    "designer": {"label": "Designer", "capability": "designer", "role_class": "worker", "division": "production", "authority": "local"},
    "developer": {"label": "Developer", "capability": "developer", "role_class": "worker", "division": "production", "authority": "local"},
    "qa": {"label": "QA", "capability": "qa", "role_class": "worker", "division": "production", "authority": "local"},
    "security": {"label": "Security", "capability": "security", "role_class": "worker", "division": "production", "authority": "safety"},
    "devops": {"label": "DevOps", "capability": "devops", "role_class": "worker", "division": "production", "authority": "local"},
    "pm": {"label": "Product Manager", "capability": "pm", "role_class": "manager", "division": "management", "authority": "cross_division"},
    "architect": {"label": "Architect", "capability": "architect", "role_class": "manager", "division": "management", "authority": "cross_division"},
    "sales": {"label": "Sales", "capability": "sales", "role_class": "manager", "division": "funding", "authority": "funding"},
}

_DEFAULT_PERMISSIONS = {
    "worker": ["perform_assigned_work", "request_review"],
    "manager": ["perform_assigned_work", "request_review", "approve_division_work", "assign_work", "cross_division_request"],
}

# Factory Constitution: AI personnel may research, recommend, and request capital,
# but may never receive authority to move money or bind the owner/company.
_FORBIDDEN_AI_FINANCIAL_PERMISSIONS = {
    "approve_funding",
    "spend_money",
    "spend_funds",
    "transfer_money",
    "transfer_funds",
    "borrow_money",
    "borrow_funds",
    "invest_money",
    "invest_funds",
    "contract_authority",
    "sign_contract",
    "execute_contract",
    "open_bank_account",
    "payout_funds",
}


def _sanitize_permissions(values: list[str] | tuple[str, ...] | set[str]) -> list[str]:
    return sorted({
        str(value).strip().lower()
        for value in values
        if str(value).strip() and str(value).strip().lower() not in _FORBIDDEN_AI_FINANCIAL_PERMISSIONS
    })


def _path() -> Path:
    p = data_root() / "config" / "factory_personnel.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _read() -> dict[str, Any]:
    p = _path()
    if not p.is_file():
        return {"version": 1, "profiles": {}}
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(raw, dict) and isinstance(raw.get("profiles"), dict):
            return raw
    except Exception:
        pass
    return {"version": 1, "profiles": {}}


def _write(doc: dict[str, Any]) -> None:
    p = _path()
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(doc, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(p)


def _division_for(capability: str) -> str:
    if capability in {"analyst", "marketing", "methodologist", "evolution_analyst"}:
        return "research"
    if capability in {"designer", "developer", "qa", "security", "devops"}:
        return "production"
    if capability == "sales":
        return "funding"
    return "management"


def _infer_capability(text: str) -> str:
    t = text.lower()
    pairs = [
        (("security", "safety", "risk"), "security"),
        (("deploy", "infrastructure", "server", "devops"), "devops"),
        (("test", "qa", "quality"), "qa"),
        (("code", "developer", "build", "program"), "developer"),
        (("design", "ux", "ui", "visual"), "designer"),
        (("architect", "architecture", "system design"), "architect"),
        (("market", "marketing", "advertising", "campaign"), "marketing"),
        (("sales", "funding", "finance", "revenue"), "sales"),
        (("method", "methodology", "experiment"), "methodologist"),
        (("evolution", "improve", "optimization"), "evolution_analyst"),
        (("product", "requirements", "roadmap"), "pm"),
        (("research", "analyze", "analysis", "study"), "analyst"),
    ]
    for words, capability in pairs:
        if any(w in t for w in words):
            return capability
    return "analyst"


def _infer_role(text: str, explicit_role: str | None = None) -> str:
    if explicit_role in {"worker", "manager"}:
        return explicit_role
    t = text.lower()
    if any(w in t for w in ("manager", "manage", "oversee", "supervise", "department head", "approve work")):
        return "manager"
    return "worker"


def _authority(role: str, capability: str, text: str) -> str:
    t = text.lower()
    if capability == "security" and role == "manager":
        return "safety"
    if capability == "sales" or any(w in t for w in ("funding authority", "approve funding", "finance authority")):
        return "funding"
    if role == "manager":
        return "cross_division"
    return "local"


def _permissions(role: str, authority: str) -> list[str]:
    out = list(_DEFAULT_PERMISSIONS[role])
    if authority == "funding":
        out.append("request_funding")
    elif authority == "safety":
        out.extend(["safety_review", "block_release"])
    return _sanitize_permissions(out)


def list_personnel() -> list[dict[str, Any]]:
    doc = _read()
    overrides = doc.get("profiles") or {}
    out: list[dict[str, Any]] = []
    for agent_id, base in CANONICAL.items():
        row = {"id": agent_id, **base, "custom": False, "ecosystem": "shared"}
        row.update(overrides.get(agent_id) or {})
        row.setdefault("permissions", _permissions(str(row.get("role_class") or "worker"), str(row.get("authority") or "local")))
        row["permissions"] = _sanitize_permissions(list(row.get("permissions") or []))
        out.append(row)
    for agent_id, row in overrides.items():
        if agent_id in CANONICAL:
            continue
        if not isinstance(row, dict):
            continue
        item = {"id": agent_id, "custom": True, **row}
        item.setdefault("permissions", _permissions(str(item.get("role_class") or "worker"), str(item.get("authority") or "local")))
        item["permissions"] = _sanitize_permissions(list(item.get("permissions") or []))
        out.append(item)
    return out


def personnel_map() -> dict[str, dict[str, Any]]:
    return {str(row["id"]): row for row in list_personnel()}


def create_personnel(description: str, *, role_class: str | None = None, label: str | None = None) -> dict[str, Any]:
    desc = str(description or "").strip()
    if not desc:
        raise ValueError("Describe what the AI unit should do")
    capability = _infer_capability(desc)
    role = _infer_role(desc, role_class)
    division = "management" if role == "manager" and capability not in {"sales", "security"} else _division_for(capability)
    authority = _authority(role, capability, desc)
    unit_id = f"unit-{uuid.uuid4().hex[:8]}"
    generated_label = label or (f"{capability.replace('_', ' ').title()} Manager" if role == "manager" else f"{capability.replace('_', ' ').title()} Worker")
    row = {
        "label": generated_label[:80],
        "description": desc[:1000],
        "capability": capability,
        "role_class": role,
        "division": division,
        "authority": authority,
        "permissions": _permissions(role, authority),
        "ecosystem": "shared",
        "created_at": time.time(),
        "updated_at": time.time(),
    }
    doc = _read(); doc.setdefault("profiles", {})[unit_id] = row; _write(doc)
    return {"id": unit_id, "custom": True, **row}


def set_supervisor(worker_id: str, manager_id: str) -> dict[str, Any]:
    """Persist a manager → subordinate relationship without changing either AI's role."""
    wid = str(worker_id or "").strip()
    mid = str(manager_id or "").strip()
    roster = personnel_map()
    worker = roster.get(wid)
    manager = roster.get(mid)
    if not worker or worker.get("retired"):
        raise ValueError("Subordinate AI unit is unavailable")
    if not manager or manager.get("retired") or manager.get("role_class") != "manager":
        raise ValueError("Manager AI unit is unavailable")
    if wid == mid:
        raise ValueError("A manager cannot supervise itself")
    if worker.get("role_class") == "manager":
        raise ValueError("Choose a worker AI as the subordinate")

    doc = _read()
    profiles = doc.setdefault("profiles", {})
    base = CANONICAL.get(wid) or {}
    row = {**base, **dict(profiles.get(wid) or {})}
    row["supervisor_id"] = mid
    row["supervisor_label"] = str(manager.get("label") or mid)
    row["updated_at"] = time.time()
    profiles[wid] = row
    _write(doc)
    return {"id": wid, "custom": wid not in CANONICAL, **row}


def update_personnel(agent_id: str, *, action: str, division: str | None = None, permission: str | None = None, label: str | None = None, ecosystem: str | None = None) -> dict[str, Any]:
    aid = str(agent_id or "").strip()
    if not aid:
        raise ValueError("AI unit is required")
    current = personnel_map().get(aid)
    if not current:
        raise ValueError("AI unit not found")
    doc = _read(); profiles = doc.setdefault("profiles", {})
    row = dict(profiles.get(aid) or {})
    base = CANONICAL.get(aid) or {}
    merged = {**base, **row}

    if action == "promote":
        merged["role_class"] = "manager"
        if str(merged.get("authority") or "local") == "local":
            merged["authority"] = "cross_division"
        merged["permissions"] = _permissions("manager", str(merged.get("authority") or "cross_division"))
    elif action == "demote":
        merged["role_class"] = "worker"
        merged["authority"] = "local"
        merged["permissions"] = _permissions("worker", "local")
    elif action == "set_division":
        div = re.sub(r"[^a-z0-9_-]+", "_", str(division or "").strip().lower())[:40]
        if not div:
            raise ValueError("Division is required")
        merged["division"] = div
    elif action == "set_ecosystem":
        eco = re.sub(r"[^a-z0-9_-]+", "_", str(ecosystem or "").strip().lower())[:40]
        if not eco:
            raise ValueError("Ecosystem is required")
        merged["ecosystem"] = eco
    elif action == "grant_permission":
        perm = re.sub(r"[^a-z0-9_-]+", "_", str(permission or "").strip().lower())[:60]
        if not perm:
            raise ValueError("Permission is required")
        if perm in _FORBIDDEN_AI_FINANCIAL_PERMISSIONS:
            raise ValueError("Factory Constitution forbids granting AI personnel direct financial authority")
        merged["permissions"] = _sanitize_permissions([*(merged.get("permissions") or []), perm])
    elif action == "revoke_permission":
        perm = str(permission or "").strip().lower()
        merged["permissions"] = [p for p in (merged.get("permissions") or []) if str(p).lower() != perm]
    elif action == "rename":
        name = str(label or "").strip()[:80]
        if not name:
            raise ValueError("Name is required")
        merged["label"] = name
    elif action == "retire":
        if aid in CANONICAL:
            merged["retired"] = True
        else:
            profiles.pop(aid, None); _write(doc)
            return {"id": aid, "retired": True, "deleted": True}
    elif action == "restore":
        merged["retired"] = False
    else:
        raise ValueError("Unknown personnel action")

    merged["updated_at"] = time.time()
    # Persist only overrides + custom fields, but keeping merged is harmless and makes
    # profiles self-describing if the defaults evolve later.
    profiles[aid] = merged
    _write(doc)
    return {"id": aid, "custom": aid not in CANONICAL, **merged}
