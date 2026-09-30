#!/bin/bash
# ============================================================================
# AUTONOMOUS AI-FACTORY v2.1 — Docker Run Script
# ============================================================================
# Builds (if needed) and runs the AI-Factory container with persistent data.
# All configs, pipeline state, logs, and secrets are stored in ~/aicom-data
# and survive container rebuilds.
#
# Usage:
#   ./run.sh            — Build & run (first time or after code changes)
#   ./run.sh --no-build — Run without rebuilding (use existing image)
#   ./run.sh --help     — Show this help
# ============================================================================

set -euo pipefail

IMAGE_NAME="ai-factory:latest"
CONTAINER_NAME="ai-factory"
DATA_DIR="${HOME}/aicom-data"
FRONTEND_PORT="${FRONTEND_PORT:-8080}"
BACKEND_PORT="${BACKEND_PORT:-8081}"
# Bind to loopback by default. Set AIFACTORY_BIND_ADDRESS explicitly (for
# example to a Tailscale address) when remote access is intentionally needed.
AIFACTORY_BIND_ADDRESS="${AIFACTORY_BIND_ADDRESS:-127.0.0.1}"
# Optional second bind (for example the host's Tailscale IP). Leave unset to
# keep the service loopback-only. A host-local value may be persisted OUTSIDE
# Git at ~/aicom-data/config/remote_bind_address.
AIFACTORY_REMOTE_BIND_ADDRESS="${AIFACTORY_REMOTE_BIND_ADDRESS:-}"
if [[ -z "${AIFACTORY_REMOTE_BIND_ADDRESS}" && -f "${DATA_DIR}/config/remote_bind_address" ]]; then
    _remote_bind="$(tr -d '[:space:]' < "${DATA_DIR}/config/remote_bind_address")"
    if [[ "${_remote_bind}" =~ ^([0-9]{1,3}\.){3}[0-9]{1,3}$ || "${_remote_bind}" == *:* ]]; then
        AIFACTORY_REMOTE_BIND_ADDRESS="${_remote_bind}"
    else
        echo "Ignoring invalid host-local remote bind address" >&2
    fi
    unset _remote_bind
fi

# ── Colors ──────────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# ── Help ────────────────────────────────────────────────────────────────────
if [[ "${1:-}" == "--help" ]]; then
    echo "Usage:"
    echo "  ./run.sh            — Build Docker image & run container"
    echo "  ./run.sh --no-build — Run without rebuilding"
    echo "  ./run.sh --help     — Show this help"
    echo ""
    echo "Environment variables:"
    echo "  FRONTEND_PORT            — Host port for frontend (default: 8080)"
    echo "  BACKEND_PORT             — Host port for backend  (default: 8081)"
    echo "  AIFACTORY_BIND_ADDRESS          — Primary host bind address (default: 127.0.0.1)"
    echo "  AIFACTORY_REMOTE_BIND_ADDRESS   — Optional second host bind, e.g. a Tailscale IP"
    echo "  Host-local fallback: ~/aicom-data/config/remote_bind_address (never committed)"
    echo "  AIFACTORY_AUTONOMOUS_PIPELINE  — First run with this data dir: 1 = autonomous, 0 = ideas only (default, skips prompt)"
    exit 0
fi

# ── Step 1: Build (unless --no-build) ──────────────────────────────────────
if [[ "${1:-}" != "--no-build" ]]; then
    echo -e "${CYAN}══════════════════════════════════════════════════════════${NC}"
    echo -e "${CYAN}  Building Docker image: ${IMAGE_NAME}${NC}"
    echo -e "${CYAN}══════════════════════════════════════════════════════════${NC}"
    docker build -t "${IMAGE_NAME}" .
    echo -e "${GREEN}✓ Build complete${NC}"
    echo ""
fi

# ── Step 2: Ensure data directory ──────────────────────────────────────────
mkdir -p "${DATA_DIR}"
mkdir -p "${DATA_DIR}/config"
mkdir -p "${DATA_DIR}/secrets/llm"
chmod 700 "${DATA_DIR}" "${DATA_DIR}/config" "${DATA_DIR}/secrets" "${DATA_DIR}/secrets/llm" 2>/dev/null || true
echo -e "${YELLOW}Data directory: ${DATA_DIR}${NC}"

# Never pass provider credentials through `docker run -e`, where they are
# recoverable through container metadata. If an operator supplies a provider
# key to this launcher, migrate it into the host-local secret store instead.
_persist_provider_secret() {
    local var_name="$1"
    local file_name="$2"
    local value="${!var_name:-}"
    if [[ -n "$value" ]]; then
        umask 077
        printf '%s' "$value" > "${DATA_DIR}/secrets/llm/${file_name}"
        chmod 600 "${DATA_DIR}/secrets/llm/${file_name}" 2>/dev/null || true
        unset "$var_name"
        echo "✓ Stored ${var_name} in the host-local secret vault (not container metadata)"
    fi
}
_persist_provider_secret DEEPSEEK_API_KEY deepseek_api_key
_persist_provider_secret OPENROUTER_API_KEY openrouter_api_key
_persist_provider_secret ANTHROPIC_API_KEY anthropic_api_key
_persist_provider_secret GROQ_API_KEY groq_api_key
_persist_provider_secret TOGETHER_API_KEY together_api_key
unset -f _persist_provider_secret

# First launch: choose autonomous pipeline vs ideas-only (writes marker inside container)
FIRST_MARK="${DATA_DIR}/config/first_run_pipeline_mode.done"
if [[ ! -f "${FIRST_MARK}" ]] && [[ -t 0 ]] && [[ -z "${AIFACTORY_AUTONOMOUS_PIPELINE:-}" ]]; then
    echo ""
    echo "AI-Factory — pipeline mode (first run with this data directory)"
    echo "  1) Autonomous mode — Director periodically creates new products"
    echo "  2) Ideas only — new products only when you submit an idea"
    read -r -p "Choose [1/2], Enter = 2: " _mode_choice || true
    _mode_choice="${_mode_choice:-2}"
    case "${_mode_choice}" in
        1) export AIFACTORY_AUTONOMOUS_PIPELINE=1 ;;
        *) export AIFACTORY_AUTONOMOUS_PIPELINE=0 ;;
    esac
fi
echo ""

# ── Step 3: Stop & remove old container ────────────────────────────────────
if docker ps -a --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    echo -e "${YELLOW}Stopping and removing existing container '${CONTAINER_NAME}'...${NC}"
    docker stop "${CONTAINER_NAME}" 2>/dev/null || true
    docker rm "${CONTAINER_NAME}" 2>/dev/null || true
    echo -e "${GREEN}✓ Old container removed${NC}"
    echo ""
fi

# ── Step 4: Run container ──────────────────────────────────────────────────
echo -e "${CYAN}══════════════════════════════════════════════════════════${NC}"
echo -e "${CYAN}  Starting AI-Factory container${NC}"
echo -e "${CYAN}══════════════════════════════════════════════════════════${NC}"
echo ""
echo -e "  Frontend:  ${GREEN}http://localhost:${FRONTEND_PORT}${NC}"
echo -e "  Backend:   ${GREEN}http://localhost:${BACKEND_PORT}/api/health${NC}"
echo -e "  Admin:     ${GREEN}http://localhost:${FRONTEND_PORT}/admin/login${NC}"
echo -e "  Data:      ${YELLOW}${DATA_DIR}${NC}"
echo ""

PORT_ARGS=(
    -p "${AIFACTORY_BIND_ADDRESS}:${FRONTEND_PORT}:8080"
    -p "${AIFACTORY_BIND_ADDRESS}:${BACKEND_PORT}:8081"
)
if [[ -n "${AIFACTORY_REMOTE_BIND_ADDRESS}" && "${AIFACTORY_REMOTE_BIND_ADDRESS}" != "${AIFACTORY_BIND_ADDRESS}" ]]; then
    PORT_ARGS+=(
        -p "${AIFACTORY_REMOTE_BIND_ADDRESS}:${FRONTEND_PORT}:8080"
        -p "${AIFACTORY_REMOTE_BIND_ADDRESS}:${BACKEND_PORT}:8081"
    )
fi

docker run -d \
    --name "${CONTAINER_NAME}" \
    --restart unless-stopped \
    --security-opt no-new-privileges:true \
    --cap-drop ALL \
    "${PORT_ARGS[@]}" \
    -v "${DATA_DIR}:/app/data" \
    --add-host host.docker.internal:host-gateway \
    -e "AIFACTORY_AUTONOMOUS_PIPELINE=${AIFACTORY_AUTONOMOUS_PIPELINE:-}" \
    -e "AIFACTORY_CONFIG_YAML=/app/data/config/admin_config_overlay.yaml" \
    -e "AIFACTORY_CONFIG_FRAGMENTS_DIR=/app/config/fragments" \
    "${IMAGE_NAME}"

echo ""
echo -e "${GREEN}✓ Container '${CONTAINER_NAME}' started successfully!${NC}"
echo ""

# ── Step 5: Show logs (first 10 lines) ─────────────────────────────────────
echo -e "${YELLOW}Waiting for services to initialize (10s)...${NC}"
sleep 10

echo -e "${CYAN}── Recent container logs ──${NC}"
docker logs --tail 10 "${CONTAINER_NAME}" 2>&1 || true

echo ""
echo -e "${CYAN}── Container status ──${NC}"
docker ps --filter "name=${CONTAINER_NAME}" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

echo ""
echo -e "${GREEN}══════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}  AI-Factory is running!${NC}"
echo -e "${GREEN}══════════════════════════════════════════════════════════${NC}"
echo ""
echo -e "  ${CYAN}Frontend:${NC}   http://localhost:${FRONTEND_PORT}"
echo -e "  ${CYAN}Admin:${NC}      http://localhost:${FRONTEND_PORT}/admin/login"
echo -e "  ${CYAN}API Health:${NC} http://localhost:${BACKEND_PORT}/api/health"
echo -e "  ${CYAN}Categories:${NC} http://localhost:${BACKEND_PORT}/api/products/categories"
echo -e "  ${CYAN}Products:${NC}   http://localhost:${BACKEND_PORT}/api/products"
echo ""
echo -e "  ${YELLOW}Admin login:${NC} user admin — password from bootstrap (see docs/security.md)"
echo ""
echo -e "  ${YELLOW}To stop:${NC}  docker stop ${CONTAINER_NAME}"
echo -e "  ${YELLOW}To start:${NC} docker start ${CONTAINER_NAME}"
echo -e "  ${YELLOW}To rebuild:${NC} ./run.sh"
echo -e "  ${YELLOW}To view logs:${NC} docker logs -f ${CONTAINER_NAME}"
echo ""
