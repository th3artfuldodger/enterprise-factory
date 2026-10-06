#!/usr/bin/env bash
set -euo pipefail
BASE="${AIFACTORY_BASE_URL:-http://127.0.0.1:8080}"; EXPECTED_IMAGE="${1:-}"; ROLLBACK_TAG="${2:-}"
COMPOSE="${AIFACTORY_LIVE_COMPOSE:-/Users/everetttrimble/aicom-data/config/empire2-live-compose.yml}"
fail=0
for path in /api/health /api/health/ready /factory; do code=$(curl -sS -o /tmp/aifactory-smoke.out -w '%{http_code}' "$BASE$path" || true); echo "$path $code"; [[ "$code" == 200 ]] || fail=1; done
if [[ -n "$EXPECTED_IMAGE" ]]; then live=$(docker inspect ai-factory --format '{{.Image}}' 2>/dev/null || true); expected=$(docker image inspect "$EXPECTED_IMAGE" --format '{{.Id}}' 2>/dev/null || true); echo "live=$live expected=$expected"; [[ -n "$expected" && "$live" == "$expected" ]] || fail=1; fi
if [[ -n "$ROLLBACK_TAG" ]]; then docker image inspect "$ROLLBACK_TAG" >/dev/null 2>&1 || { echo "Rollback image missing: $ROLLBACK_TAG" >&2; fail=1; }; fi
if [[ "$fail" -eq 0 ]]; then echo "POST-DEPLOY VERIFY PASS"; exit 0; fi
echo "POST-DEPLOY VERIFY FAILED" >&2
if [[ "${AIFACTORY_ALLOW_AUTO_ROLLBACK:-0}" == 1 && -n "$ROLLBACK_TAG" && -f "$COMPOSE" ]]; then
  echo "Explicit auto-rollback armed -> $ROLLBACK_TAG" >&2
  python3 - "$COMPOSE" "$ROLLBACK_TAG" <<'PY2'
from pathlib import Path
import re,sys
p=Path(sys.argv[1]); tag=sys.argv[2]; s=p.read_text(); s2,n=re.subn(r'(?m)^(\s*image:\s*)ai-factory:[^\s]+',r'\1'+tag,s,count=1)
if n != 1: raise SystemExit('Could not update live compose image')
p.write_text(s2)
PY2
  docker compose -f "$COMPOSE" up -d
  for i in {1..30}; do curl -fsS "$BASE/api/health" >/dev/null 2>&1 && { echo "ROLLBACK HEALTH PASS"; exit 1; }; sleep 2; done
  echo "ROLLBACK HEALTH FAILED" >&2
fi
exit 1
