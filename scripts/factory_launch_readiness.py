#!/usr/bin/env python3
"""Machine-readable pre-launch score; source checks always run, live checks are optional."""
from __future__ import annotations
import json, subprocess, urllib.request, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
checks={}
def sh(cmd): return subprocess.run(cmd,cwd=ROOT,shell=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode==0
checks["git_clean"]=sh("git diff --quiet && git diff --cached --quiet")
checks["security_gate_present"]=(ROOT/".github/workflows/security-gate.yml").is_file()
checks["release_gate_present"]=(ROOT/"scripts/factory_release_gate.sh").is_file()
checks["api_contract_present"]=(ROOT/"docs/api-contract-v1.json").is_file()
checks["operations_runbook_present"]=(ROOT/"docs/FACTORY_OPERATIONS.md").is_file()
checks["disaster_recovery_runbook_present"]=(ROOT/"docs/FACTORY_DISASTER_RECOVERY.md").is_file()
checks["dependency_policy_present"]=(ROOT/".github/dependabot.yml").is_file()
checks["production_readiness_tests_present"]=(ROOT/"tests/test_production_readiness.py").is_file()
if "--live" in sys.argv:
    try:
        with urllib.request.urlopen("http://127.0.0.1:8080/api/health/ready",timeout=5) as r:
            data=json.loads(r.read()); checks["live_ready"]=r.status==200 and bool(data.get("ready"))
    except Exception: checks["live_ready"]=False
score=round(100*sum(checks.values())/max(1,len(checks)))
result={"score":score,"ready":all(checks.values()),"checks":checks}
print(json.dumps(result,indent=2)); raise SystemExit(0 if result["ready"] else 1)
