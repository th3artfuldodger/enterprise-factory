"""Live Factory Floor graph payload for admin WS / SSE metrics."""

from __future__ import annotations

import hashlib
import json
import logging
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

from core.paths import llm_calls_log_path, logs_dir
from orchestrator.pipeline_flow import pipeline_stage_agents

logger = logging.getLogger(__name__)


def _parse_log_timestamp(raw: Any) -> float:
    """Accept epoch seconds or ISO-8601 strings from llm_calls.jsonl."""
    if raw is None or raw == "":
        return 0.0
    if isinstance(raw, (int, float)):
        return float(raw)
    text = str(raw).strip()
    if not text:
        return 0.0
    try:
        return float(text)
    except ValueError:
        pass
    try:
        from datetime import datetime

        normalized = text.replace("Z", "+00:00")
        return datetime.fromisoformat(normalized).timestamp()
    except (ValueError, TypeError):
        return 0.0


_AGENT_BEHAVIOR: dict[str, dict[str, str]] = {
    "analyst": {"role_class": "worker", "division": "research", "authority": "local"},
    "marketing": {"role_class": "worker", "division": "research", "authority": "local"},
    "methodologist": {"role_class": "worker", "division": "research", "authority": "local"},
    "evolution_analyst": {"role_class": "worker", "division": "research", "authority": "local"},
    "designer": {"role_class": "worker", "division": "production", "authority": "local"},
    "developer": {"role_class": "worker", "division": "production", "authority": "local"},
    "qa": {"role_class": "worker", "division": "production", "authority": "local"},
    "security": {"role_class": "worker", "division": "production", "authority": "safety"},
    "devops": {"role_class": "worker", "division": "production", "authority": "local"},
    "pm": {"role_class": "manager", "division": "management", "authority": "cross_division"},
    "architect": {"role_class": "manager", "division": "management", "authority": "cross_division"},
    "sales": {"role_class": "manager", "division": "funding", "authority": "funding"},
}


def _behavior_for(agent: str) -> dict[str, str]:
    return _AGENT_BEHAVIOR.get(agent, {"role_class": "worker", "division": "general", "authority": "local"})


def _package_state_for(*, assigned_agent: str | None, product_state: str, has_task: bool) -> tuple[str, int, str]:
    state = product_state.upper()
    if "HUMAN_REVIEW" in state or "REVIEW" in state:
        return "awaiting_external_approval", 82, "approval"
    if "BLOCK" in state or "FAIL" in state or "ERROR" in state:
        return "blocked", 68, "manager_review"
    if assigned_agent:
        role_class = _behavior_for(assigned_agent).get("role_class")
        if role_class == "manager":
            return "manager_review", 72, "approval"
        return "drafting", 42, "manager_review"
    if has_task:
        return "in_transfer", 64, "manager_review"
    if state in {"DONE", "COMPLETE", "COMPLETED", "SHIPPED", "LAUNCHED"}:
        return "completed", 100, "complete"
    return "ready_for_manager", 58, "manager_review"

_AGENT_LABELS: dict[str, str] = {
    "analyst": "Market Analyst",
    "pm": "Product Manager",
    "marketing": "Marketing",
    "methodologist": "Methodologist",
    "architect": "Architect",
    "designer": "Designer",
    "developer": "Developer",
    "qa": "QA",
    "security": "Security",
    "devops": "DevOps",
    "sales": "Sales",
    "evolution_analyst": "Evolution",
}


def _stage_order() -> list[str]:
    stages = pipeline_stage_agents()
    if "designer" not in stages:
        try:
            ai = stages.index("architect")
            stages = stages[: ai + 1] + ["designer"] + stages[ai + 1 :]
        except ValueError:
            stages = [*stages, "designer"]
    return stages


def _pipeline_edges() -> list[dict[str, str]]:
    order = _stage_order()
    edges: list[dict[str, str]] = []
    for i in range(len(order) - 1):
        edges.append({"from": order[i], "to": order[i + 1], "kind": "flow"})
    edges.append({"from": "qa", "to": "developer", "kind": "rework"})
    edges.append({"from": "security", "to": "developer", "kind": "rework"})
    return edges


def _tail_llm_by_agent(*, limit_per_agent: int = 3) -> dict[str, dict[str, Any]]:
    path = llm_calls_log_path()
    if not path.is_file():
        return {}
    buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return {}
    cutoff = time.time() - 3600
    for line in reversed(lines[-8000:]):
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        ts = _parse_log_timestamp(row.get("timestamp") or row.get("time"))
        if ts and ts < cutoff:
            continue
        agent = str(row.get("agent_type") or "unknown")
        if len(buckets[agent]) >= limit_per_agent:
            continue
        buckets[agent].append(row)
    out: dict[str, dict[str, Any]] = {}
    for agent, rows in buckets.items():
        costs = [float(r.get("estimated_cost_usd") or 0) for r in rows]
        latencies = [float(r.get("latency_ms") or r.get("duration_ms") or 0) for r in rows if r.get("latency_ms") or r.get("duration_ms")]
        prompts = [str(r.get("prompt_preview") or r.get("task_preview") or "")[:120] for r in rows if r.get("prompt_preview") or r.get("task_preview")]
        out[agent] = {
            "provider": str(rows[0].get("provider") or rows[0].get("model_provider") or "—"),
            "model": str(rows[0].get("model") or "—"),
            "last_latency_ms": round(latencies[0], 1) if latencies else None,
            "last_cost_usd": round(costs[0], 6) if costs else 0.0,
            "calls_1h": len(rows),
            "prompt_line": prompts[0] if prompts else "",
        }
    return out


def _running_tasks_snapshot(sqlite_path: Path) -> list[dict[str, Any]]:
    try:
        from orchestrator.sqlite_manager import SQLiteManager

        sm = SQLiteManager(str(sqlite_path))
        sm.connect()
        rows = sm.conn.execute(
            """
            SELECT t.id, t.product_id, t.agent_type, t.assigned_to, t.status, t.started_at, t.created_at,
                   t.priority, t.input, p.idea, p.state AS product_state
            FROM tasks t
            LEFT JOIN products p ON p.id = t.product_id AND p.workspace_id = t.workspace_id
            WHERE t.workspace_id = ?
              AND lower(trim(t.status)) IN ('running', 'pending')
            ORDER BY
              CASE WHEN lower(trim(t.status)) = 'running' THEN 0 ELSE 1 END,
              t.priority ASC,
              COALESCE(t.started_at, t.created_at) ASC
            LIMIT 120
            """,
            (sm.workspace_id,),
        ).fetchall()
        sm.close()
    except Exception:
        logger.debug("factory_floor running tasks query failed", exc_info=True)
        return []
    out: list[dict[str, Any]] = []
    for r in rows:
        d = dict(r) if hasattr(r, "keys") else {}
        if not d and isinstance(r, tuple):
            continue
        agent = str(d.get("agent_type") or "")
        assignment: dict[str, Any] = {}
        raw_input = d.get("input")
        if raw_input:
            try:
                parsed = json.loads(raw_input) if isinstance(raw_input, str) else raw_input
                if isinstance(parsed, dict) and parsed.get("factory_personnel_assignment"):
                    assignment = parsed
            except Exception:
                assignment = {}
        out.append(
            {
                "task_id": d.get("id"),
                "product_id": d.get("product_id"),
                "agent_type": agent,
                "assigned_to": d.get("assigned_to"),
                "personnel_assignment": bool(assignment),
                "reports_to": assignment.get("reports_to"),
                "reports_to_label": assignment.get("reports_to_label"),
                "assignment_directive": assignment.get("assignment_directive"),
                "manager_delegated": bool(assignment.get("manager_delegated")),
                "delegated_by": assignment.get("delegated_by"),
                "delegated_by_label": assignment.get("delegated_by_label"),
                "status": d.get("status"),
                "priority": d.get("priority"),
                "product_title": (str(d.get("idea") or "")[:80] or None),
                "product_state": d.get("product_state"),
                "created_at": d.get("created_at"),
                "started_at": d.get("started_at") or d.get("created_at"),
            }
        )
    return out


def _products_snapshot(sqlite_path: Path, limit: int = 80) -> list[dict[str, Any]]:
    """Persistent product objects for the Factory Floor world."""
    try:
        from orchestrator.sqlite_manager import SQLiteManager

        sm = SQLiteManager(str(sqlite_path))
        sm.connect()
        rows = sm.conn.execute(
            """
            SELECT
                id,
                idea,
                state,
                created_at,
                updated_at,
                current_task_id,
                category,
                extras
            FROM products
            WHERE workspace_id = ?
            ORDER BY COALESCE(updated_at, created_at) DESC
            LIMIT ?
            """,
            (sm.workspace_id, limit),
        ).fetchall()
        sm.close()
    except Exception:
        logger.debug("factory_floor products query failed", exc_info=True)
        return []

    products: list[dict[str, Any]] = []

    for row in rows:
        d = dict(row) if hasattr(row, "keys") else {}
        if not d:
            continue

        extras: dict[str, Any] = {}
        raw_extras = d.get("extras")

        if raw_extras:
            try:
                parsed = json.loads(raw_extras) if isinstance(raw_extras, str) else raw_extras
                if isinstance(parsed, dict):
                    extras = parsed
            except (json.JSONDecodeError, TypeError):
                pass

        products.append(
            {
                "id": d.get("id"),
                "idea": d.get("idea") or "",
                "state": d.get("state") or "IDEA",
                "created_at": d.get("created_at"),
                "updated_at": d.get("updated_at"),
                "current_task_id": d.get("current_task_id"),
                "category": d.get("category"),
                "delivery_profile": extras.get("delivery_profile"),
            }
        )

    return products

def _product_task_history(sqlite_path: Path, product_ids: list[str]) -> dict[str, dict[str, Any]]:
    """Compact completed-task history used for actionable Factory Floor alerts."""
    if not product_ids:
        return {}
    try:
        from orchestrator.sqlite_manager import SQLiteManager

        sm = SQLiteManager(str(sqlite_path))
        sm.connect()
        placeholders = ",".join("?" for _ in product_ids)
        rows = sm.conn.execute(
            f"""
            SELECT product_id, agent_type, status, state, completed_at, created_at, input
            FROM tasks
            WHERE workspace_id = ? AND product_id IN ({placeholders})
            ORDER BY product_id, COALESCE(completed_at, created_at) ASC
            """,
            (sm.workspace_id, *product_ids),
        ).fetchall()
        sm.close()
    except Exception:
        logger.debug("factory_floor task history query failed", exc_info=True)
        return {}

    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        d = dict(row) if hasattr(row, "keys") else {}
        if not d:
            continue
        pid = str(d.get("product_id") or "")
        if not pid:
            continue
        entry = out.setdefault(pid, {"completed_agents": [], "completed_states": [], "last_agent": None, "last_state": None})
        status = str(d.get("status") or "").lower()
        raw_input = d.get("input")
        if raw_input:
            try:
                parsed_input = json.loads(raw_input) if isinstance(raw_input, str) else raw_input
                if isinstance(parsed_input, dict) and parsed_input.get("factory_personnel_assignment"):
                    continue
            except Exception:
                pass
        if status == "completed":
            agent = str(d.get("agent_type") or "")
            state = str(d.get("state") or "")
            if agent and agent not in entry["completed_agents"]:
                entry["completed_agents"].append(agent)
            if state and state not in entry["completed_states"]:
                entry["completed_states"].append(state)
            if agent:
                entry["last_agent"] = agent
            if state:
                entry["last_state"] = state
    return out


def _product_control_metadata(product_ids: list[str]) -> dict[str, dict[str, Any]]:
    if not product_ids:
        return {}
    try:
        from web.backend.services.product_followup import normalize_pipeline_followup, read_followup
    except Exception:
        return {}
    out: dict[str, dict[str, Any]] = {}
    for pid in product_ids:
        try:
            row = normalize_pipeline_followup(read_followup(pid))
            out[pid] = {
                "pipeline_paused": bool(row.get("pipeline_on_hold")),
                "factory_priority": str(row.get("factory_priority") or "normal"),
            }
        except Exception:
            out[pid] = {"pipeline_paused": False, "factory_priority": "normal"}
    return out


def _ecosystem_name(category: Any, idea: str) -> str:
    text = f"{category or ''} {idea or ''}".lower()
    if any(k in text for k in ("health", "medical", "wellness", "clinical")):
        return "health"
    if any(k in text for k in ("weapon", "defense", "defence", "tactical")):
        return "weapons"
    if any(k in text for k in ("etsy", "ecommerce", "e-commerce", "marketplace", "retail")):
        return "commerce"
    if any(k in text for k in ("science", "research", "lab", "biotech")):
        return "science"
    if category:
        return str(category).strip().lower().replace(" ", "_")[:32]
    return "general"


_STRAND_APPEARANCES: tuple[dict[str, str], ...] = (
    {"style": "polka", "color": "#22d3ee", "accent": "#f8fafc"},
    {"style": "red_laser", "color": "#ef4444", "accent": "#fecaca"},
    {"style": "orange_butterfly", "color": "#f97316", "accent": "#fde68a"},
    {"style": "violet_wave", "color": "#a78bfa", "accent": "#e9d5ff"},
    {"style": "green_dots", "color": "#34d399", "accent": "#bbf7d0"},
    {"style": "gold_comet", "color": "#fbbf24", "accent": "#fef3c7"},
    {"style": "blue_scan", "color": "#60a5fa", "accent": "#dbeafe"},
    {"style": "pink_pulse", "color": "#f472b6", "accent": "#fce7f3"},
)


def _strand_appearance(request_id: str) -> dict[str, str]:
    digest = hashlib.sha256(str(request_id).encode("utf-8")).digest()
    return dict(_STRAND_APPEARANCES[digest[0] % len(_STRAND_APPEARANCES)])


def _active_handoff_tasks(sqlite_path: Path, product_ids: list[str]) -> list[dict[str, Any]]:
    if not product_ids:
        return []
    try:
        from orchestrator.sqlite_manager import SQLiteManager
        sm = SQLiteManager(str(sqlite_path)); sm.connect()
        placeholders = ",".join("?" for _ in product_ids)
        rows = sm.conn.execute(
            f"""
            SELECT id, product_id, agent_type, assigned_to, status, state, created_at, started_at, priority, retry_count, input
            FROM tasks
            WHERE workspace_id = ? AND product_id IN ({placeholders})
              AND lower(status) IN ('pending','running','blocked')
            ORDER BY created_at ASC
            """,
            (sm.workspace_id, *product_ids),
        ).fetchall()
        sm.close()
        return [dict(row) for row in rows]
    except Exception:
        logger.debug("factory_floor active handoff query failed", exc_info=True)
        return []


def _open_assignment_reports(sqlite_path: Path, product_ids: list[str]) -> list[dict[str, Any]]:
    if not product_ids:
        return []
    try:
        from orchestrator.sqlite_manager import SQLiteManager
        sm = SQLiteManager(str(sqlite_path)); sm.connect()
        placeholders = ",".join("?" for _ in product_ids)
        rows = sm.conn.execute(
            f"""
            SELECT id, product_id, agent_type, assigned_to, status, state, created_at, completed_at, input, output
            FROM tasks
            WHERE workspace_id = ? AND product_id IN ({placeholders})
              AND lower(status) = 'completed'
            ORDER BY COALESCE(completed_at, created_at) ASC
            """,
            (sm.workspace_id, *product_ids),
        ).fetchall()
        sm.close()
    except Exception:
        logger.debug("factory_floor assignment report query failed", exc_info=True)
        return []
    out: list[dict[str, Any]] = []
    for row in rows:
        task = dict(row)
        try:
            inp = json.loads(task.get("input") or "{}") if isinstance(task.get("input"), str) else (task.get("input") or {})
            result = json.loads(task.get("output") or "{}") if isinstance(task.get("output"), str) else (task.get("output") or {})
        except Exception:
            continue
        if not isinstance(inp, dict) or not inp.get("factory_personnel_assignment") or not isinstance(result, dict):
            continue
        report_status = str(result.get("factory_report_status") or "")
        if report_status not in {"awaiting_manager", "escalated"}:
            continue
        task["assignment_input"] = inp
        task["assignment_output"] = result
        task["report_status"] = report_status
        out.append(task)
    return out


def _report_result_summary(value: Any) -> str:
    if value is None:
        return "Assignment completed; manager review requested."
    if isinstance(value, str):
        return value[:500]
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True)[:500]
    except Exception:
        return str(value)[:500]


def _agent_log_pulse() -> dict[str, str]:
    log_dir = logs_dir()
    pulse: dict[str, str] = {}
    if not log_dir.is_dir():
        return pulse
    now = time.time()
    for log_file in sorted(log_dir.glob("*.jsonl")):
        agent = log_file.stem
        try:
            tail = log_file.read_text(encoding="utf-8", errors="replace").splitlines()[-20:]
        except OSError:
            continue
        recent = False
        for line in reversed(tail):
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            ts = float(row.get("time") or 0)
            if ts > now - 120:
                recent = True
                break
        pulse[agent] = "active" if recent else "idle"
    return pulse


def _ai_market_external_slice() -> dict[str, Any]:
    """Recent AI Market Protocol v1 invocations for Factory Floor WOW overlay."""
    try:
        from web.backend.services.ai_market_protocol.stats import list_recent_stats

        events = list_recent_stats(16)
    except Exception:
        logger.debug("factory_floor ai_market stats unavailable", exc_info=True)
        events = []
    if not events:
        return {"events": [], "node": None, "hot_edges": []}
    last = events[0]
    total_usd = sum(float(e.get("price_usd") or 0) for e in events if e.get("type") == "invoke")
    node = {
        "id": "external_agent",
        "label": "🤖 External AI",
        "status": "running",
        "prompt_line": f"{last.get('capability_id', 'invoke')} · ${float(last.get('price_usd') or 0):.2f}",
        "provider": "ai-market",
        "model": "protocol-v1",
        "latency_ms": last.get("latency_ms"),
        "cost_usd": float(last.get("price_usd") or 0),
        "product_id": last.get("product_id"),
        "circuit_tripped": False,
    }
    target = "developer" if "developer" in _stage_order() else (_stage_order()[0] if _stage_order() else "analyst")
    hot = [{"from": "external_agent", "to": target, "pulse_id": "ai-market-live"}]
    return {"events": events, "node": node, "hot_edges": hot, "total_usd_1h": round(total_usd, 4)}


def build_factory_floor_slice(
    *,
    sqlite_path: Path,
    circuit_breakers: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Graph nodes/edges + live pulses for the Factory Floor UI."""
    llm_by_agent = _tail_llm_by_agent()
    running = _running_tasks_snapshot(sqlite_path)
    products = _products_snapshot(sqlite_path)
    product_ids = [str(p.get("id") or "") for p in products if p.get("id")]
    task_history = _product_task_history(sqlite_path, product_ids)
    control_meta = _product_control_metadata(product_ids)
    active_handoffs = _active_handoff_tasks(sqlite_path, product_ids)
    from web.backend.services.factory_routing import ecosystem_config, ecosystem_nodes, route_plan
    canonical_active_by_product: dict[str, dict[str, Any]] = {}
    for task in active_handoffs:
        raw_input = task.get("input")
        is_personnel = False
        if raw_input:
            try:
                parsed_input = json.loads(raw_input) if isinstance(raw_input, str) else raw_input
                is_personnel = bool(isinstance(parsed_input, dict) and parsed_input.get("factory_personnel_assignment"))
            except Exception:
                is_personnel = False
        if not is_personnel:
            pid = str(task.get("product_id") or "")
            if pid and pid not in canonical_active_by_product:
                canonical_active_by_product[pid] = task
    try:
        from web.backend.services.factory_personnel import personnel_map
        personnel = personnel_map()
    except Exception:
        logger.debug("factory floor personnel unavailable", exc_info=True)
        personnel = {}
    log_pulse = _agent_log_pulse()

    active_by_agent: dict[str, dict[str, Any]] = {}
    assignment_queue_by_agent: dict[str, list[dict[str, Any]]] = {}
    for row in running:
        key = str(row.get("assigned_to") or row.get("agent_type") or "")
        if not key:
            continue
        if key not in active_by_agent:
            active_by_agent[key] = row
        if row.get("personnel_assignment"):
            assignment_queue_by_agent.setdefault(key, []).append({
                "task_id": row.get("task_id"),
                "product_id": row.get("product_id"),
                "product_title": row.get("product_title"),
                "directive": row.get("assignment_directive"),
                "status": row.get("status"),
                "priority": row.get("priority"),
                "reports_to": row.get("reports_to"),
                "reports_to_label": row.get("reports_to_label"),
                "manager_delegated": bool(row.get("manager_delegated")),
                "delegated_by": row.get("delegated_by"),
                "delegated_by_label": row.get("delegated_by_label"),
                "created_at": row.get("created_at"),
            })

    subordinates_by_manager: dict[str, list[str]] = {}
    for worker_id, worker_profile in personnel.items():
        supervisor_id = str(worker_profile.get("supervisor_id") or "").strip()
        if supervisor_id and worker_profile.get("role_class") == "worker" and not worker_profile.get("retired"):
            subordinates_by_manager.setdefault(supervisor_id, []).append(worker_id)

    cb_providers = (circuit_breakers or {}).get("providers") or {}
    open_providers = {
        name
        for name, row in cb_providers.items()
        if str((row or {}).get("state") or "").lower() in ("open", "half_open")
    }

    nodes: list[dict[str, Any]] = []
    stage_order = _stage_order()
    for agent in stage_order:
        profile = personnel.get(agent) or {}
        if profile.get("retired"):
            continue
        llm = llm_by_agent.get(agent) or {}
        active = active_by_agent.get(agent)
        pulse = log_pulse.get(agent, "idle")
        if active:
            status = "running"
        elif pulse == "active":
            status = "thinking"
        else:
            status = "idle"

        provider = llm.get("provider") or "—"
        circuit_tripped = any(p.lower() in provider.lower() for p in open_providers) if provider != "—" else False
        if not circuit_tripped and open_providers and llm.get("provider"):
            for pname in open_providers:
                if pname.split("_")[0] in str(llm.get("provider", "")).lower():
                    circuit_tripped = True
                    break

        nodes.append(
            {
                "id": agent,
                "label": str(profile.get("label") or _AGENT_LABELS.get(agent, agent.title())),
                "status": status,
                "prompt_line": (active and active.get("product_title")) or llm.get("prompt_line") or "",
                "provider": provider,
                "model": llm.get("model") or "—",
                "latency_ms": llm.get("last_latency_ms"),
                "cost_usd": llm.get("last_cost_usd"),
                "product_id": active.get("product_id") if active else None,
                "circuit_tripped": circuit_tripped,
                **_behavior_for(agent),
                "role_class": str(profile.get("role_class") or _behavior_for(agent).get("role_class") or "worker"),
                "division": str(profile.get("division") or _behavior_for(agent).get("division") or "general"),
                "authority": str(profile.get("authority") or _behavior_for(agent).get("authority") or "local"),
                "permissions": list(profile.get("permissions") or []),
                "capability": str(profile.get("capability") or agent),
                "custom_personnel": bool(profile.get("custom")),
                "supervisor_id": profile.get("supervisor_id"),
                "supervisor_label": profile.get("supervisor_label"),
                "subordinate_ids": list(subordinates_by_manager.get(agent) or []),
                "task_queue": list(assignment_queue_by_agent.get(agent) or []),
                "queued_task_count": len(assignment_queue_by_agent.get(agent) or []),
                "package_state": "drafting" if status in ("running", "thinking") else "idle",
                "package_progress": 45 if status == "running" else (22 if status == "thinking" else 0),
                "next_destination": "manager_review" if str(profile.get("role_class") or _behavior_for(agent).get("role_class")) == "worker" else "approval",
            }
        )


    canonical_ids = set(stage_order)
    for agent, profile in personnel.items():
        if agent in canonical_ids or profile.get("retired"):
            continue
        role_class = str(profile.get("role_class") or "worker")
        active = active_by_agent.get(agent)
        nodes.append({
            "id": agent,
            "label": str(profile.get("label") or agent),
            "status": "running" if active else "idle",
            "prompt_line": str((active or {}).get("assignment_directive") or profile.get("description") or ""),
            "provider": "factory",
            "model": str(profile.get("capability") or "general"),
            "latency_ms": None,
            "cost_usd": None,
            "product_id": (active or {}).get("product_id"),
            "assignment_task_id": (active or {}).get("task_id"),
            "reports_to": (active or {}).get("reports_to"),
            "reports_to_label": (active or {}).get("reports_to_label"),
            "assignment_directive": (active or {}).get("assignment_directive"),
            "circuit_tripped": False,
            "role_class": role_class,
            "division": str(profile.get("division") or "general"),
            "authority": str(profile.get("authority") or ("cross_division" if role_class == "manager" else "local")),
            "permissions": list(profile.get("permissions") or []),
            "capability": str(profile.get("capability") or "analyst"),
            "custom_personnel": True,
            "supervisor_id": profile.get("supervisor_id"),
            "supervisor_label": profile.get("supervisor_label"),
            "subordinate_ids": list(subordinates_by_manager.get(agent) or []),
            "task_queue": list(assignment_queue_by_agent.get(agent) or []),
            "queued_task_count": len(assignment_queue_by_agent.get(agent) or []),
            "package_state": "drafting" if active else "idle",
            "package_progress": 45 if active else 0,
            "next_destination": "approval" if role_class == "manager" else "manager_review",
        })


    # Division ecosystem managers are persistent supervisory nodes. They carry
    # routing/approval policy but do not impersonate executable pipeline agents.
    nodes.extend(ecosystem_nodes())


    # Products are persistent world objects. They stay visible even when
    # no agent currently has an active task for them.
    product_to_agent: dict[str, str] = {}

    for agent_name, task in active_by_agent.items():
        product_id = task.get("product_id")
        if product_id:
            product_to_agent[str(product_id)] = agent_name

    product_edges: list[dict[str, str]] = []

    for product in products:
        product_id = str(product.get("id") or "")
        if not product_id:
            continue

        assigned_agent = product_to_agent.get(product_id)
        idea = str(product.get("idea") or product_id)
        state = str(product.get("state") or "IDEA")
        history = task_history.get(product_id) or {}
        controls = control_meta.get(product_id) or {}
        last_agent = str(history.get("last_agent") or "") or None
        history_agent = assigned_agent or last_agent
        ecosystem = _ecosystem_name(product.get("category"), idea)
        eco = ecosystem_config(ecosystem)
        routing = route_plan(
            product_state=state,
            ecosystem=ecosystem,
            active_task=canonical_active_by_product.get(product_id),
            paused=bool(controls.get("pipeline_paused")),
        )

        package_state, package_progress, next_destination = _package_state_for(
            assigned_agent=assigned_agent,
            product_state=state,
            has_task=bool(product.get("current_task_id")),
        )

        nodes.append(
            {
                "id": f"product:{product_id}",
                "kind": "product",
                "label": idea[:72],
                "status": "running" if assigned_agent else "idle",
                "prompt_line": idea,
                "provider": "factory",
                "model": product.get("delivery_profile") or "product",
                "latency_ms": None,
                "cost_usd": None,
                "product_id": product_id,
                "product_state": state,
                "current_task_id": product.get("current_task_id"),
                "assigned_agent": assigned_agent,
                "last_agent": last_agent,
                "completed_agents": list(history.get("completed_agents") or []),
                "completed_states": list(history.get("completed_states") or []),
                "circuit_tripped": False,
                "role_class": "package",
                "division": _behavior_for(history_agent or "").get("division", "general"),
                "authority": "none",
                "package_state": package_state,
                "package_progress": package_progress,
                "next_destination": next_destination,
                "pipeline_paused": bool(controls.get("pipeline_paused")),
                "factory_priority": str(controls.get("factory_priority") or "normal"),
                "ecosystem": ecosystem,
                "ecosystem_label": eco.get("label"),
                "ecosystem_accent": eco.get("accent"),
                "ecosystem_manager_id": routing.get("ecosystem_manager_id"),
                "ecosystem_manager_label": routing.get("ecosystem_manager_label"),
                "approval_rules": routing.get("approval_rules"),
                "routing_mode": routing.get("routing_mode"),
                "route_status": routing.get("route_status"),
                "current_stage": routing.get("current_stage"),
                "current_owner": routing.get("current_owner"),
                "next_stage": routing.get("next_stage"),
                "next_owner": routing.get("next_owner"),
                "next_state": routing.get("next_state"),
                "waiting_on": routing.get("waiting_on"),
                "crossing_division": routing.get("crossing_division"),
            }
        )

        if assigned_agent:
            product_edges.append(
                {
                    "from": assigned_agent,
                    "to": f"product:{product_id}",
                    "kind": "work_item",
                    "signal_kind": "production",
                }
            )

    hot_edges: list[dict[str, str]] = []
    for i, row in enumerate(running[:8]):
        agent = str(row.get("agent_type") or "")
        if not agent:
            continue
        idx = stage_order.index(agent) if agent in stage_order else -1
        if idx > 0:
            hot_edges.append({"from": stage_order[idx - 1], "to": agent, "pulse_id": f"pulse-{i}"})


    for idx, edge in enumerate(product_edges):
        hot_edges.append(
            {
                "from": edge["from"],
                "to": edge["to"],
                "pulse_id": f"product-{idx}",
            }
        )

    alerts: list[dict[str, Any]] = []
    for node in nodes:
        if node.get("kind") == "product" and node.get("package_state") in {"blocked", "awaiting_external_approval"}:
            completed_agents = [str(a) for a in (node.get("completed_agents") or []) if a]
            completed_states = [str(st) for st in (node.get("completed_states") or []) if st]
            approvals_completed = [_AGENT_LABELS.get(a, a.replace("_", " ").title()) for a in completed_agents]
            if completed_states:
                approvals_completed.extend([st.replace("_", " ").title() for st in completed_states[-3:] if st.replace("_", " ").title() not in approvals_completed])
            alerts.append({
                "id": f"alert:{node.get('id')}",
                "severity": "warning" if node.get("package_state") == "awaiting_external_approval" else "stop",
                "origin_division": node.get("division") or "general",
                "origin_agent": node.get("assigned_agent") or node.get("last_agent"),
                "product_id": node.get("product_id"),
                "package_label": node.get("label"),
                "approvals_completed": approvals_completed[-6:],
                "next_required_action": node.get("next_destination") or "manager_review",
                "objective": node.get("prompt_line") or node.get("label"),
            })
        elif node.get("role_class") == "manager" and node.get("circuit_tripped"):
            alerts.append({
                "id": f"alert:{node.get('id')}",
                "severity": "stop",
                "origin_division": node.get("division") or "management",
                "origin_agent": node.get("id"),
                "product_id": node.get("product_id"),
                "package_label": node.get("prompt_line") or node.get("label"),
                "approvals_completed": [],
                "next_required_action": "system_intervention",
                "objective": node.get("prompt_line") or "Restore manager workflow",
            })

    # Only current handoffs are drawn. Historical routes remain in metadata so
    # the floor stays uncluttered while every active request has its own strand.
    strand_edges: list[dict[str, Any]] = []
    product_by_id = {str(p.get("id") or ""): p for p in products if p.get("id")}
    open_reports = _open_assignment_reports(sqlite_path, product_ids)
    for task in active_handoffs:
        pid = str(task.get("product_id") or "")
        assignment: dict[str, Any] = {}
        raw_input = task.get("input")
        if raw_input:
            try:
                parsed = json.loads(raw_input) if isinstance(raw_input, str) else raw_input
                if isinstance(parsed, dict) and parsed.get("factory_personnel_assignment"):
                    assignment = parsed
            except Exception:
                assignment = {}
        task_context: dict[str, Any] = {}
        if raw_input:
            try:
                parsed_context = json.loads(raw_input) if isinstance(raw_input, str) else raw_input
                if isinstance(parsed_context, dict):
                    task_context = parsed_context
            except Exception:
                task_context = {}
        target = str(task.get("assigned_to") or task.get("agent_type") or "")
        history = task_history.get(pid) or {}
        completed_agents = [str(a) for a in (history.get("completed_agents") or []) if a]
        source = str(assignment.get("reports_to") or task_context.get("factory_manager_id") or (completed_agents[-1] if completed_agents else "external_agent"))
        # A retry by the same unit is still an individual request; route it from
        # the preceding completed unit when possible so the strand has length.
        if source == target and len(completed_agents) > 1:
            source = completed_agents[-2]
        product = product_by_id.get(pid) or {}
        request_id = str(task.get("id") or f"{pid}:{source}:{target}")
        appearance = _strand_appearance(request_id)
        strand_edges.append({
            "id": f"strand:{request_id}",
            "from": source,
            "to": target,
            "kind": "active_handoff",
            "signal_kind": (
                "funding" if target == "sales" or source == "sales"
                else "alert" if source == "security" or target == "security"
                else "command" if source in {"pm", "architect"} or target in {"pm", "architect"}
                else "production" if source in {"designer", "developer", "qa", "devops"} or target in {"designer", "developer", "qa", "devops"}
                else "data"
            ),
            "request_id": request_id,
            "product_id": pid or None,
            "product_label": str(product.get("idea") or pid)[:72],
            "product_state": product.get("state"),
            "source_label": str((personnel.get(source) or {}).get("label") or assignment.get("reports_to_label") or _AGENT_LABELS.get(source, source.replace("_", " ").title())),
            "target_label": str((personnel.get(target) or {}).get("label") or assignment.get("personnel_label") or _AGENT_LABELS.get(target, target.replace("_", " ").title())),
            "last_approved_agent": source,
            "last_approved_label": _AGENT_LABELS.get(source, source.replace("_", " ").title()),
            "original_agent": completed_agents[0] if completed_agents else source,
            "origin_chain": completed_agents,
            "completed_states": list(history.get("completed_states") or []),
            "data_summary": (
                f"{str((personnel.get(source) or {}).get('label') or _AGENT_LABELS.get(source, source.title()))} → "
                f"{str((personnel.get(target) or {}).get('label') or _AGENT_LABELS.get(target, target.title()))}: "
                f"{str(assignment.get('assignment_directive') or product.get('idea') or 'factory workflow')[:160]}"
            ),
            "assignment_directive": assignment.get("assignment_directive"),
            "reports_to": assignment.get("reports_to"),
            "active": True,
            "status": str(task.get("status") or "running"),
            "appearance": appearance,
            "created_at": task.get("created_at"),
            "route_status": next((n.get("route_status") for n in nodes if n.get("kind") == "product" and n.get("product_id") == pid), None),
            "current_stage": next((n.get("current_stage") for n in nodes if n.get("kind") == "product" and n.get("product_id") == pid), None),
            "next_stage": next((n.get("next_stage") for n in nodes if n.get("kind") == "product" and n.get("product_id") == pid), None),
            "next_owner": next((n.get("next_owner") for n in nodes if n.get("kind") == "product" and n.get("product_id") == pid), None),
            "ecosystem": str(task_context.get("factory_ecosystem") or _ecosystem_name(product.get("category"), str(product.get("idea") or pid))),
            "manager_id": str(task_context.get("factory_manager_id") or assignment.get("reports_to") or "") or None,
        })

    # Completed personnel work reverses direction as a live report-back strand.
    # Once the manager resolves it, this strand disappears; send-back creates a
    # fresh worker assignment strand, and escalation reroutes toward Command AI.
    for report in open_reports:
        pid = str(report.get("product_id") or "")
        inp = report.get("assignment_input") or {}
        outp = report.get("assignment_output") or {}
        worker = str(inp.get("personnel_id") or report.get("assigned_to") or report.get("agent_type") or "")
        manager = str(inp.get("reports_to") or "pm")
        escalated = str(report.get("report_status") or "") == "escalated"
        source = manager if escalated else worker
        target = "external_agent" if escalated else manager
        request_id = f"report:{report.get('id')}:{source}:{target}"
        product = product_by_id.get(pid) or {}
        result_summary = _report_result_summary(outp.get("factory_assignment_result"))
        strand_edges.append({
            "id": f"strand:{request_id}",
            "from": source,
            "to": target,
            "kind": "assignment_report",
            "signal_kind": "command",
            "request_id": request_id,
            "report_task_id": report.get("id"),
            "report_status": report.get("report_status"),
            "product_id": pid,
            "product_label": str(product.get("idea") or pid)[:72],
            "product_state": product.get("state"),
            "source_label": str((personnel.get(source) or {}).get("label") or ("Command Manager" if source == "external_agent" else _AGENT_LABELS.get(source, source.replace("_", " ").title()))),
            "target_label": str((personnel.get(target) or {}).get("label") or ("Command AI" if target == "external_agent" else _AGENT_LABELS.get(target, target.replace("_", " ").title()))),
            "last_approved_agent": source,
            "last_approved_label": str((personnel.get(source) or {}).get("label") or _AGENT_LABELS.get(source, source.replace("_", " ").title())),
            "original_agent": worker,
            "origin_chain": [worker, manager] if worker and manager else [x for x in (worker, manager) if x],
            "data_summary": (
                f"{'Escalated manager report' if escalated else 'Completed work reporting back'}: "
                f"{str(inp.get('assignment_directive') or '')[:120]}"
            ),
            "assignment_directive": inp.get("assignment_directive"),
            "report_result_summary": result_summary,
            "manager_feedback": outp.get("factory_manager_feedback") or outp.get("factory_escalation_note"),
            "reports_to": manager,
            "active": True,
            "status": "escalated" if escalated else "awaiting_manager",
            "appearance": _strand_appearance(request_id),
            "created_at": report.get("completed_at") or report.get("created_at"),
        })

    # A human-review wait is also an active communication strand. It remains
    # visible until the approval resolves, then disappears automatically.
    for node in nodes:
        if node.get("kind") != "product" or node.get("package_state") != "awaiting_external_approval":
            continue
        pid = str(node.get("product_id") or "")
        history = task_history.get(pid) or {}
        completed_agents = [str(a) for a in (history.get("completed_agents") or []) if a]
        source = str(node.get("last_agent") or (completed_agents[-1] if completed_agents else "pm"))
        target = "sales"
        request_id = f"review:{pid}:{source}:approval"
        appearance = _strand_appearance(request_id)
        strand_edges.append({
            "id": f"strand:{request_id}",
            "from": source,
            "to": target,
            "kind": "active_handoff",
            "signal_kind": "funding",
            "request_id": request_id,
            "product_id": pid,
            "product_label": str(node.get("label") or pid)[:72],
            "product_state": node.get("product_state"),
            "source_label": _AGENT_LABELS.get(source, source.replace("_", " ").title()),
            "target_label": "Funding / Review",
            "last_approved_agent": source,
            "last_approved_label": _AGENT_LABELS.get(source, source.replace("_", " ").title()),
            "original_agent": completed_agents[0] if completed_agents else source,
            "origin_chain": completed_agents,
            "completed_states": list(history.get("completed_states") or []),
            "data_summary": f"Approval request for {str(node.get('label') or pid)[:110]}",
            "active": True,
            "status": "awaiting_approval",
            "appearance": appearance,
        })

    # Package tethers are only present while a worker is actively carrying one.
    for edge in product_edges:
        pid = str(str(edge.get("to") or "").replace("product:", "", 1))
        product = product_by_id.get(pid) or {}
        hist = task_history.get(pid) or {}
        src = str(edge.get("from") or "")
        request_id = f"package:{pid}:{src}"
        edge.update({
            "id": f"strand:{request_id}",
            "kind": "package_tether",
            "request_id": request_id,
            "product_id": pid,
            "product_label": str(product.get("idea") or pid)[:72],
            "product_state": product.get("state"),
            "source_label": _AGENT_LABELS.get(src, src.replace("_", " ").title()),
            "target_label": "Project Package",
            "last_approved_agent": (hist.get("last_agent") or src),
            "last_approved_label": _AGENT_LABELS.get(str(hist.get("last_agent") or src), str(hist.get("last_agent") or src).replace("_", " ").title()),
            "origin_chain": list(hist.get("completed_agents") or []),
            "data_summary": f"Live package data for {str(product.get('idea') or pid)[:110]}",
            "active": True,
            "appearance": _strand_appearance(request_id),
        })

    # Attach durable event provenance to currently visible strands. New work is
    # driven by explicit task-start/handoff events; older in-flight work falls back
    # to task state until it naturally advances.
    try:
        from web.backend.services.factory_event_journal import recent_factory_events
        recent_events = recent_factory_events(limit=500)
    except Exception:
        recent_events = []
    latest_event_by_task: dict[str, dict[str, Any]] = {}
    for ev in recent_events:
        tid = str(ev.get("task_id") or "")
        if tid:
            latest_event_by_task[tid] = ev
    for edge in strand_edges:
        tid = str(edge.get("report_task_id") or edge.get("request_id") or "")
        ev = latest_event_by_task.get(tid)
        edge["movement_source"] = "event_journal" if ev else "task_state"
        if ev:
            edge["event_id"] = ev.get("id")
            edge["event_type"] = ev.get("type")
            edge["event_time"] = ev.get("time")

    try:
        from web.backend.services.factory_operations import build_operational_alerts
        product_nodes = [n for n in nodes if n.get("kind") == "product"]
        alerts, manager_inboxes = build_operational_alerts(
            product_nodes=product_nodes,
            active_tasks=active_handoffs,
            open_reports=open_reports,
            base_alerts=alerts,
        )
    except Exception:
        logger.debug("factory floor operational inbox build failed", exc_info=True)
        manager_inboxes = {}

    for node in nodes:
        inbox = manager_inboxes.get(str(node.get("id") or ""), [])
        if node.get("role_class") == "manager" or node.get("kind") == "ecosystem_manager":
            node["inbox_count"] = len(inbox)
            node["manager_inbox"] = inbox[:12]

    try:
        from core.paths import workspace_id as current_workspace_id
        from web.backend.services.empire_architecture import architecture_summary
        from web.backend.services.funding_utility import funding_status_summary
        empire_architecture = architecture_summary()
        funding_utility = funding_status_summary(workspace_id=current_workspace_id())
    except Exception:
        logger.debug("Empire 2 architecture/funding slice unavailable", exc_info=True)
        empire_architecture = {}
        funding_utility = {}

    ai_market = _ai_market_external_slice()
    if ai_market.get("node"):
        nodes.insert(0, ai_market["node"])
        hot_edges = list(ai_market.get("hot_edges") or []) + hot_edges

    return {
        "nodes": nodes,
        "edges": [*strand_edges, *product_edges],
        "hot_edges": hot_edges,
        "running_count": len(running),
        "open_circuits": sorted(open_providers),
        "ecosystems": [ecosystem_config(name) for name in ("health", "science", "commerce", "weapons", "general")],
        "alerts": alerts,
        "manager_inboxes": manager_inboxes,
        "recent_events": recent_events[-80:],
        "empire_architecture": empire_architecture,
        "funding_utility": funding_utility,
        "updated_at": time.time(),
        "ai_market": {
            "events": ai_market.get("events") or [],
            "total_usd_1h": ai_market.get("total_usd_1h", 0),
        },
    }
