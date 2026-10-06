#!/usr/bin/env python3
"""Fail when the stable customer Factory v1 API surface changes unexpectedly."""
from __future__ import annotations
import json, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from web.backend.main import app
REQUIRED={
  ("GET","/api/customer/factory"), ("POST","/api/customer/factory/mission"),
  ("POST","/api/customer/factory/personnel"), ("POST","/api/customer/factory/managers/{manager_id}/delegate"),
  ("POST","/api/customer/factory/tasks/{task_id}/retry"), ("POST","/api/customer/factory/projects/{product_id}/control"),
  ("POST","/api/customer/factory/projects/{product_id}/auto-delegate"), ("POST","/api/customer/factory/projects/{product_id}/retry-failed"),
  ("POST","/api/customer/factory/backup"), ("GET","/api/health"), ("GET","/api/health/ready"),
}
def surface():
    # FastAPI 0.141 keeps included routers as lazy _IncludedRouter entries in app.routes.
    # OpenAPI is therefore the canonical public HTTP surface, not the internal route list.
    rows=set()
    for path, operations in (app.openapi().get("paths") or {}).items():
        for method in operations:
            upper=str(method).upper()
            if upper not in {"HEAD","OPTIONS","PARAMETERS"}: rows.add((upper,path))
    return rows
def main():
    actual=surface(); missing=sorted(REQUIRED-actual)
    payload={"contract":"factory-v1","required":[{"method":m,"path":p} for m,p in sorted(REQUIRED)],"missing":[{"method":m,"path":p} for m,p in missing]}
    if "--write" in sys.argv:
        out=ROOT/"docs"/"api-contract-v1.json"; out.write_text(json.dumps(payload,indent=2)+"\n"); print(out)
    if missing:
        print(json.dumps(payload,indent=2)); raise SystemExit(1)
    print(f"API contract OK: {len(REQUIRED)} required routes")
if __name__=="__main__": main()
