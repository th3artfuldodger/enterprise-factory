"""Low-cost recurring synthetic checks for customer Factory invariants.

The synthetic customer journey runs in a subprocess with a temporary
AIFACTORY_DATA_ROOT so it exercises real tenant services without touching or
waking any production tenant.
"""
from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import tempfile
import time

from core.paths import data_root
from web.backend.services.customer_factory_establishment import MISSION_TEMPLATES, PLAN_LIMITS
from web.backend.services.customer_workforce import FORBIDDEN_FINANCIAL_PERMISSIONS
from web.backend.services.provider_health import local_ollama_health

_ISOLATED_SCRIPT = r"""
import json
import time
from orchestrator.sqlite_manager import SQLiteManager
from web.backend.services.empire_missions import create_customer_mission
from web.backend.services.customer_task_recovery import retry_customer_task
from web.backend.services.customer_workforce import create_customer_personnel, delegate_customer_manager_task
from web.backend.services.tenant_workspaces import customer_workspace_context, read_customer_pipeline_state

cid = 'canary-customer-a'
other = 'canary-customer-b'
mission = create_customer_mission(cid, 'Canary: validate a small-business market opportunity with evidence and risk review')
state = read_customer_pipeline_state(cid)
tasks = list(state.get('task_queue') or [])
research = [t for t in tasks if t.get('state') == 'EMPIRE_RESEARCH']
manager_review = [t for t in tasks if t.get('state') == 'EMPIRE_MANAGER_REVIEW']
ultron = [t for t in tasks if t.get('state') == 'ULTRON_REVIEW']
manager = create_customer_personnel(cid, 'Canary research manager', role_class='manager', label='Canary Manager')
worker = create_customer_personnel(cid, 'Canary research analyst', role_class='worker', label='Canary Analyst')
delegated = delegate_customer_manager_task(
    cid, manager_id=manager['id'], worker_id=worker['id'], product_id=mission['product_id'],
    directive='Challenge the weakest assumption with fresh evidence.'
)
ctx = customer_workspace_context(cid)
sm = SQLiteManager(ctx['pipeline_db'], workspace_id=ctx['workspace_id'])
sm.connect()
row = sm.get_task(delegated['task_id'])
row['status'] = 'failed'
row['error'] = 'synthetic canary failure'
row['completed_at'] = time.time()
sm.upsert_task(row)
sm.close()
recovery = retry_customer_task(cid, delegated['task_id'])
after = read_customer_pipeline_state(cid)
retry_row = next((t for t in after.get('task_queue') or [] if t.get('id') == recovery['task_id']), {})
foreign = read_customer_pipeline_state(other)
print(json.dumps({
    'mission_created': bool(mission.get('product_id')),
    'five_research_lenses': len(research) == 5,
    'manager_stage_present': len(manager_review) == 1,
    'ultron_stage_present': len(ultron) == 1,
    'delegation_queued': bool(delegated.get('task_id')),
    'recovery_queued': retry_row.get('status', '').lower() == 'pending' and (retry_row.get('input_data') or {}).get('retry_of') == delegated['task_id'],
    'workspace_isolation': mission['product_id'] not in (foreign.get('products') or {}),
    'financial_authority': False,
}))
"""

_JOURNEY_CHECKS = (
    "mission_created",
    "five_research_lenses",
    "manager_stage_present",
    "ultron_stage_present",
    "delegation_queued",
    "recovery_queued",
    "workspace_isolation",
)


def _isolated_customer_journey() -> dict:
    with tempfile.TemporaryDirectory(prefix="factory-canary-") as td:
        env = dict(os.environ)
        env["AIFACTORY_DATA_ROOT"] = td
        env["AIFACTORY_WORKSPACE_ID"] = "canary-root"
        proc = subprocess.run(
            [sys.executable, "-c", _ISOLATED_SCRIPT],
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        if proc.returncode != 0:
            raise RuntimeError((proc.stderr or proc.stdout or "isolated canary failed")[-2000:])
        lines = [line for line in proc.stdout.splitlines() if line.strip()]
        if not lines:
            raise RuntimeError("isolated canary produced no result")
        return json.loads(lines[-1])


def run_customer_factory_canary() -> dict:
    checks: dict[str, bool] = {}
    errors: list[str] = []
    checks["plans_defined"] = all(k in PLAN_LIMITS for k in ("free", "maker", "studio", "enterprise"))
    checks["templates_defined"] = len(MISSION_TEMPLATES) >= 7
    checks["financial_boundary"] = (
        "spend_money" in FORBIDDEN_FINANCIAL_PERMISSIONS
        and "approve_funding" in FORBIDDEN_FINANCIAL_PERMISSIONS
    )
    health = local_ollama_health()
    checks["provider_online"] = bool(health.get("online"))
    journey: dict = {}
    try:
        journey = _isolated_customer_journey()
        for key in _JOURNEY_CHECKS:
            checks[key] = bool(journey.get(key))
    except Exception as exc:
        errors.append(str(exc))
        for key in _JOURNEY_CHECKS:
            checks[key] = False
    result = {
        "ok": all(checks.values()),
        "checked_at": time.time(),
        "checks": checks,
        "errors": errors,
        "provider": health,
        "synthetic_journey": journey,
    }
    path = data_root() / "telemetry" / "customer_factory_canary.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(path)
    return result


def read_customer_factory_canary() -> dict:
    path = data_root() / "telemetry" / "customer_factory_canary.json"
    if not path.exists():
        return {"ok": False, "status": "not_run"}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"ok": False, "status": "invalid"}


async def customer_factory_canary_loop() -> None:
    while True:
        try:
            await asyncio.to_thread(run_customer_factory_canary)
        except asyncio.CancelledError:
            raise
        except Exception:
            pass
        await asyncio.sleep(21600)
