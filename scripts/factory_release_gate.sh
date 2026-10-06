#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"; cd "$ROOT"
TEST_IMAGE="${AIFACTORY_TEST_IMAGE:-ai-factory:latest}"
backend_py(){
  if python3 -c 'import fastapi,pytest' >/dev/null 2>&1; then python3 "$@";
  else docker run --rm --entrypoint /app/venv/bin/python -v "$ROOT:/workspace:ro" -w /workspace -e PYTHONPATH=/workspace -e AIFACTORY_DATA_ROOT=/tmp/aicom-data "$TEST_IMAGE" "$@"; fi
}
backend_pytest(){
  if command -v pytest >/dev/null 2>&1 && python3 -c 'import fastapi' >/dev/null 2>&1; then pytest "$@";
  else docker run --rm --entrypoint /app/venv/bin/pytest -v "$ROOT:/workspace:ro" -w /workspace -e PYTHONPATH=/workspace -e AIFACTORY_DATA_ROOT=/tmp/aicom-data "$TEST_IMAGE" "$@"; fi
}
echo "[1/8] repository security"; python3 scripts/security_gate.py --tracked; python3 scripts/security_gate.py --history
echo "[2/8] Python dependency audit"
if python3 -c 'import pip_audit' >/dev/null 2>&1; then bash scripts/pip_audit_gate.sh
else docker run --rm -v "$ROOT/requirements.txt:/tmp/requirements.txt:ro" python:3.12-slim bash -lc 'pip install -q pip-audit && pip-audit -r /tmp/requirements.txt'; fi
echo "[3/8] API contract"; backend_py scripts/check_api_contract.py
echo "[4/8] backend release suite"
backend_pytest -q tests/test_ultron_oversight.py tests/test_task_queue_hygiene.py tests/test_empire_missions.py tests/test_customer_workforce.py tests/test_empire_architecture.py tests/test_factory_manager_delegation.py tests/test_funding_utility.py tests/test_tenant_workspaces.py tests/test_customer_journey_e2e.py tests/test_customer_task_recovery.py tests/test_customer_factory_establishment.py tests/test_llm_router_credential_gate.py tests/test_production_readiness.py tests/test_customer_factory_abuse.py tests/test_provider_health_config.py tests/test_customer_plan_boundaries.py tests/test_api_contract_versioning.py
echo "[5/8] clean frontend install + lint"; (cd web/frontend && npm ci && npm run lint -- --max-warnings=0)
echo "[6/8] frontend production build"; (cd web/frontend && npm run build)
echo "[7/8] production dependency audit"; (cd web/frontend && npm audit --omit=dev --audit-level=high)
echo "[8/8] source readiness"; python3 scripts/factory_launch_readiness.py
echo "RELEASE GATE PASS"
