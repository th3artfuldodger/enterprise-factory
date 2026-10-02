"""Division autonomy, staffing, manager inboxes and exception detection."""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from orchestrator.sqlite_manager import SQLiteManager
from web.backend.services.factory_personnel import personnel_map
from web.backend.services.factory_routing import ecosystem_config

_MANAGER_CAPABILITIES = {"pm", "architect", "sales"}


def infer_ecosystem(category: Any, idea: str) -> str:
    text = f"{category or ''} {idea or ''}".lower()
    if any(k in text for k in ("health", "medical", "wellness", "clinical", "patient")):
        return "health"
    if any(k in text for k in ("weapon", "defense", "defence", "tactical", "ballistic")):
        return "weapons"
    if any(k in text for k in ("etsy", "ecommerce", "e-commerce", "marketplace", "retail", "shop")):
        return "commerce"
    if any(k in text for k in ("science", "research", "lab", "biotech", "physics", "chemistry")):
        return "science"
    return "general"


def infer_personnel_ecosystem(description: str) -> str:
    return infer_ecosystem(None, description)


def staff_task(
    task: dict[str, Any],
    product: dict[str, Any],
    task_queue: list[dict[str, Any]],
) -> dict[str, Any]:
    """Assign the least-loaded suitable AI identity without changing executable capability."""
    if (task.get("input_data") or {}).get("factory_personnel_assignment"):
        return task
    capability = str(task.get("agent_type") or "")
    if not capability or capability.startswith("__"):
        return task
    ecosystem = infer_ecosystem(product.get("category"), str(product.get("idea") or ""))
    roster = personnel_map()
    loads: dict[str, int] = {}
    for queued in task_queue:
        if str(queued.get("status") or "").lower() not in {"pending", "running", "blocked"}:
            continue
        aid = str(queued.get("assigned_to") or queued.get("agent_type") or "")
        loads[aid] = loads.get(aid, 0) + 1

    want_manager = capability in _MANAGER_CAPABILITIES
    candidates: list[tuple[tuple[int, int, int, str], str, dict[str, Any]]] = []
    for aid, row in roster.items():
        if row.get("retired") or str(row.get("capability") or "") != capability:
            continue
        role = str(row.get("role_class") or "worker")
        if want_manager and role != "manager":
            continue
        if not want_manager and role == "manager":
            continue
        pe = str(row.get("ecosystem") or "general")
        eco_rank = 0 if pe == ecosystem else (1 if pe == "general" else 3)
        custom_rank = 0 if row.get("custom") else 1
        candidates.append(((eco_rank, loads.get(aid, 0), custom_rank, aid), aid, row))

    if candidates:
        candidates.sort(key=lambda x: x[0])
        _, selected, profile = candidates[0]
    else:
        selected = capability
        profile = roster.get(selected) or {}

    task["assigned_to"] = selected
    inp = task.setdefault("input_data", {})
    if not isinstance(inp, dict):
        inp = {}; task["input_data"] = inp
    eco = ecosystem_config(ecosystem)
    inp["factory_staffing"] = {
        "ecosystem": ecosystem,
        "division_manager": f"ecosystem-manager:{ecosystem}",
        "division_manager_label": eco.get("manager_label"),
        "staffed_to": selected,
        "staffed_to_label": profile.get("label") or selected,
        "capability": capability,
        "load_at_assignment": loads.get(selected, 0),
    }
    return task


def _json_obj(value: Any) -> dict[str, Any]:
    if isinstance(value, dict): return dict(value)
    if isinstance(value, str) and value:
        try:
            x=json.loads(value); return dict(x) if isinstance(x, dict) else {}
        except Exception: return {}
    return {}


def build_manager_inboxes(sqlite_path: Path, products: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not products:
        return []
    sm=SQLiteManager(str(sqlite_path)); sm.connect()
    try:
        pids=[str(p.get("id") or "") for p in products if p.get("id")]
        if not pids: return []
        ph=",".join("?" for _ in pids)
        rows=sm.conn.execute(f"SELECT * FROM tasks WHERE workspace_id=? AND product_id IN ({ph}) ORDER BY created_at DESC",(sm.workspace_id,*pids)).fetchall()
    finally:
        sm.close()
    product_map={str(p.get("id")):p for p in products}
    inbox: dict[str,list[dict[str,Any]]]={}
    seen:set[str]=set()
    for rr in rows:
        t=dict(rr); tid=str(t.get("id") or ""); pid=str(t.get("product_id") or "")
        if not tid or tid in seen: continue
        inp=_json_obj(t.get("input")); out=_json_obj(t.get("output")); status=str(t.get("status") or "").lower()
        product=product_map.get(pid) or {}; eco=infer_ecosystem(product.get("category"),str(product.get("idea") or "")); manager=f"ecosystem-manager:{eco}"
        item=None
        if inp.get("factory_personnel_assignment") and status=="completed" and str(out.get("factory_report_status") or "") in {"awaiting_manager","escalated"}:
            manager=str(inp.get("reports_to") or manager)
            item={"id":f"inbox:report:{tid}","action_type":"assignment_report","task_id":tid,"product_id":pid,"title":inp.get("personnel_label") or t.get("assigned_to") or t.get("agent_type"),"summary":inp.get("assignment_directive") or "Completed assignment ready for review","status":out.get("factory_report_status") or "awaiting_manager","actions":["accept","incorporate","send_back","escalate"]}
        elif str(product.get("state") or "").upper()=="HUMAN_REVIEW_PENDING" and status in {"pending","running"}:
            item={"id":f"inbox:approval:{pid}","action_type":"human_review","product_id":pid,"title":str(product.get("idea") or pid)[:72],"summary":"Release decision required before the project can continue","status":"awaiting_approval","actions":["approve","send_back"]}
        elif status=="blocked":
            item={"id":f"inbox:blocked:{tid}","action_type":"blocked","task_id":tid,"product_id":pid,"title":str(product.get("idea") or pid)[:72],"summary":str(t.get("error") or "Blocked task needs manager intervention")[:240],"status":"blocked","actions":["prioritize","hold","escalate"]}
        elif str(t.get("agent_type") or "")=="sales" and status in {"pending","running"}:
            manager="sales"
            item={"id":f"inbox:funding:{tid}","action_type":"funding_review","task_id":tid,"product_id":pid,"title":str(product.get("idea") or pid)[:72],"summary":"Commercial / funding stage requires attention","status":status,"actions":["prioritize","hold"]}
        if item:
            seen.add(tid if item.get("task_id") else f"{item['action_type']}:{pid}")
            item["manager_id"]=manager
            item["ecosystem"]=eco
            inbox.setdefault(manager,[]).append(item)
    roster=personnel_map()
    result=[]
    for manager,items in inbox.items():
        eco=manager.split(":",1)[1] if manager.startswith("ecosystem-manager:") else "general"
        result.append({"manager_id":manager,"manager_label":(roster.get(manager) or {}).get("label") or ecosystem_config(eco).get("manager_label") or manager,"ecosystem":eco,"open_count":len(items),"items":items[:12]})
    return sorted(result,key=lambda x:(-int(x["open_count"]),str(x["manager_label"])))


def build_command_exceptions(sqlite_path: Path, products: list[dict[str, Any]], *, now: float | None=None) -> list[dict[str, Any]]:
    now=float(now or time.time()); pmap={str(p.get("id")):p for p in products}
    if not pmap: return []
    sm=SQLiteManager(str(sqlite_path)); sm.connect()
    try:
        ph=",".join("?" for _ in pmap)
        rows=sm.conn.execute(f"SELECT * FROM tasks WHERE workspace_id=? AND product_id IN ({ph}) ORDER BY created_at DESC",(sm.workspace_id,*pmap.keys())).fetchall()
    finally: sm.close()
    alerts=[]; rework_counts:dict[str,int]={}
    for rr in rows:
        t=dict(rr); pid=str(t.get("product_id") or ""); status=str(t.get("status") or "").lower(); agent=str(t.get("assigned_to") or t.get("agent_type") or "")
        age=now-float(t.get("started_at") or t.get("created_at") or now)
        product=pmap.get(pid) or {}; title=str(product.get("idea") or pid)[:72]; eco=infer_ecosystem(product.get("category"),str(product.get("idea") or ""))
        if status in {"pending","running"} and age>2700:
            alerts.append({"id":f"exception:stale:{t.get('id')}","severity":"warning","exception_type":"stuck_task","action_type":"stuck_task","product_id":pid,"task_id":t.get("id"),"origin_agent":agent,"origin_division":eco,"package_label":title,"objective":f"Task has been {status} for {int(age//60)} minutes","next_required_action":"manager_intervention","recommended_actions":["prioritize","hold","reassign"]})
        if status=="failed":
            alerts.append({"id":f"exception:failed:{t.get('id')}","severity":"stop","exception_type":"failed_worker","action_type":"failed_task","product_id":pid,"task_id":t.get("id"),"origin_agent":agent,"origin_division":eco,"package_label":title,"objective":str(t.get("error") or "Worker failed")[:260],"next_required_action":"repair_or_reassign","recommended_actions":["reopen","reassign","escalate"]})
        retry=int(t.get("retry_count") or 0)
        if retry>0: rework_counts[pid]=rework_counts.get(pid,0)+retry
        if str(t.get("agent_type") or "")=="security" and status in {"blocked","failed"}:
            alerts.append({"id":f"exception:safety:{t.get('id')}","severity":"stop","exception_type":"safety_block","action_type":"safety_block","product_id":pid,"task_id":t.get("id"),"origin_agent":agent,"origin_division":eco,"package_label":title,"objective":"Security/safety work is blocking release","next_required_action":"safety_review","recommended_actions":["inspect","hold","escalate"]})
    for pid,count in rework_counts.items():
        if count>=2:
            product=pmap.get(pid) or {}; eco=infer_ecosystem(product.get("category"),str(product.get("idea") or ""))
            alerts.append({"id":f"exception:rework:{pid}","severity":"warning","exception_type":"repeated_rework","action_type":"repeated_rework","product_id":pid,"origin_division":eco,"package_label":str(product.get("idea") or pid)[:72],"objective":f"Project has accumulated {count} retry/rework passes","next_required_action":"manager_review","recommended_actions":["inspect_history","prioritize","hold"]})
    # Highest severity and newest-ish unique alerts first.
    uniq={a["id"]:a for a in alerts}
    return sorted(uniq.values(),key=lambda a:(0 if a.get("severity")=="stop" else 1,str(a.get("id"))))[:30]
