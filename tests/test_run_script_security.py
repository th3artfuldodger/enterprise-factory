"""Security invariants for the legacy bare ``docker run`` launcher."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUN_SH = (ROOT / "run.sh").read_text(encoding="utf-8")


def test_run_script_binds_loopback_by_default():
    assert 'AIFACTORY_BIND_ADDRESS="${AIFACTORY_BIND_ADDRESS:-127.0.0.1}"' in RUN_SH
    assert '-p "${AIFACTORY_BIND_ADDRESS}:${FRONTEND_PORT}:8080"' in RUN_SH
    assert '-p "${AIFACTORY_BIND_ADDRESS}:${BACKEND_PORT}:8081"' in RUN_SH


def test_run_script_supports_explicit_second_bind():
    assert 'AIFACTORY_REMOTE_BIND_ADDRESS="${AIFACTORY_REMOTE_BIND_ADDRESS:-}"' in RUN_SH
    assert '-p "${AIFACTORY_REMOTE_BIND_ADDRESS}:${FRONTEND_PORT}:8080"' in RUN_SH
    assert '-p "${AIFACTORY_REMOTE_BIND_ADDRESS}:${BACKEND_PORT}:8081"' in RUN_SH


def test_run_script_has_no_wildcard_port_publish():
    assert '-p "${FRONTEND_PORT}:8080"' not in RUN_SH
    assert '-p "${BACKEND_PORT}:8081"' not in RUN_SH


def test_run_script_drops_linux_privileges():
    assert "--security-opt no-new-privileges:true" in RUN_SH
    assert "--cap-drop ALL" in RUN_SH
