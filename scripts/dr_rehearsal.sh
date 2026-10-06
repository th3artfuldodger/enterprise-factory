#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DATA="${AIFACTORY_DATA_ROOT:-/Users/everetttrimble/aicom-data}"; IMAGE="${1:-ai-factory:latest}"
BACKUP=$(ls -1t "$DATA"/backups/aicom-factory-backup-*.zip 2>/dev/null | head -1 || true); [[ -n "$BACKUP" ]] || { echo "No factory backup found" >&2; exit 2; }
TMP=$(mktemp -d /tmp/aifactory-dr.XXXXXX); NAME="aifactory-dr-$RANDOM"
cleanup(){ docker rm -f "$NAME" >/dev/null 2>&1 || true; rm -rf "$TMP"; }; trap cleanup EXIT
unzip -q "$BACKUP" -d "$TMP"
docker run -d --name "$NAME" --user aifactory:aifactory --security-opt no-new-privileges:true --cap-drop ALL --add-host host.docker.internal:host-gateway -v "$TMP:/app/data" -p 127.0.0.1::8080 "$IMAGE" >/dev/null
for i in {1..30}; do P=$(docker port "$NAME" 8080/tcp 2>/dev/null | sed 's/.*://'); [[ -n "$P" ]] && curl -fsS "http://127.0.0.1:$P/api/health" >/dev/null 2>&1 && break; sleep 2; done
[[ -n "${P:-}" ]] && curl -fsS "http://127.0.0.1:$P/api/health" >/dev/null
echo "DR REHEARSAL PASS backup=$(basename "$BACKUP") image=$IMAGE port=$P"
