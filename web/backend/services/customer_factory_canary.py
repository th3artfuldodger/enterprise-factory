"""Low-cost recurring synthetic checks for customer Factory invariants."""
from __future__ import annotations
import asyncio, json, tempfile, time
from pathlib import Path
from orchestrator.sqlite_manager import SQLiteManager
from core.paths import data_root
from web.backend.services.customer_factory_establishment import PLAN_LIMITS, MISSION_TEMPLATES
from web.backend.services.customer_workforce import FORBIDDEN_FINANCIAL_PERMISSIONS
from web.backend.services.provider_health import local_ollama_health


def run_customer_factory_canary() -> dict:
    checks: dict[str, bool] = {}
    errors: list[str] = []
    checks["plans_defined"] = all(k in PLAN_LIMITS for k in ("free","maker","studio","enterprise"))
    checks["templates_defined"] = len(MISSION_TEMPLATES) >= 7
    checks["financial_boundary"] = "spend_money" in FORBIDDEN_FINANCIAL_PERMISSIONS and "approve_funding" in FORBIDDEN_FINANCIAL_PERMISSIONS
    health = local_ollama_health()
    checks["provider_online"] = bool(health.get("online"))
    try:
        with tempfile.TemporaryDirectory(prefix="factory-canary-") as td:
            db=Path(td)/"canary.db"
            a=SQLiteManager(db,workspace_id="canary-a"); a.connect()
            a.upsert_product({"id":"prod-canary0001","idea":"canary","state":"IDEA_RECEIVED","workspace_id":"canary-a"}); a.close()
            b=SQLiteManager(db,workspace_id="canary-b"); b.connect()
            checks["workspace_isolation"] = b.get_product("prod-canary0001") is None; b.close()
    except Exception as exc:
        checks["workspace_isolation"] = False; errors.append(str(exc))
    result={"ok":all(checks.values()),"checked_at":time.time(),"checks":checks,"errors":errors,"provider":health}
    path=data_root()/"telemetry"/"customer_factory_canary.json"; path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix('.tmp'); tmp.write_text(json.dumps(result,indent=2,sort_keys=True),encoding='utf-8'); tmp.replace(path)
    return result


def read_customer_factory_canary() -> dict:
    path=data_root()/"telemetry"/"customer_factory_canary.json"
    if not path.exists(): return {"ok":False,"status":"not_run"}
    try: return json.loads(path.read_text(encoding='utf-8'))
    except Exception: return {"ok":False,"status":"invalid"}


async def customer_factory_canary_loop() -> None:
    while True:
        try: await asyncio.to_thread(run_customer_factory_canary)
        except asyncio.CancelledError: raise
        except Exception: pass
        await asyncio.sleep(21600)
