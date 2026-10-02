"""Supervisor for isolated customer Factory workers.

Each customer workspace gets a distinct SQLite pipeline store and distinct data
root.  The supervisor never combines tenant state in one PipelineWorker.
"""
from __future__ import annotations

import json
import logging
import os
import signal
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

from core.paths import data_root

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] tenant-supervisor: %(message)s",
)
logger = logging.getLogger("tenant-supervisor")

TERMINAL_STATES = {"COMPLETED", "DEPLOYED_PRODUCTION", "FAILED", "CANCELLED"}


def _tenant_dirs() -> list[Path]:
    root = data_root() / "tenants"
    if not root.exists():
        return []
    return sorted(
        p for p in root.iterdir()
        if p.is_dir() and (p / "state" / "pipeline.db").exists()
    )


def _has_active_work(root: Path) -> bool:
    db = root / "state" / "pipeline.db"
    try:
        conn = sqlite3.connect(str(db), timeout=3.0)
        conn.row_factory = sqlite3.Row
        task = conn.execute(
            "SELECT 1 FROM tasks WHERE lower(status) IN ('pending','running','blocked') LIMIT 1"
        ).fetchone()
        if task:
            conn.close()
            return True
        placeholders = ",".join("?" for _ in TERMINAL_STATES)
        product = conn.execute(
            f"SELECT 1 FROM products WHERE upper(state) NOT IN ({placeholders}) LIMIT 1",
            tuple(TERMINAL_STATES),
        ).fetchone()
        conn.close()
        return bool(product)
    except Exception:
        logger.exception("failed checking tenant store %s", db)
        return False


def _env_for(root: Path) -> dict[str, str]:
    ws = root.name
    env = dict(os.environ)
    env["AIFACTORY_WORKSPACE_ID"] = ws
    env["AIFACTORY_DATA_ROOT"] = str(root)
    env["SQLITE_PATH"] = str(root / "state" / "pipeline.db")
    env["PIPELINE_DB_BACKEND"] = "sqlite"
    env["USE_SQLITE"] = "true"
    env["PIPELINE_USE_POSTGRES"] = "false"
    env["AIFACTORY_WORKER_HEALTH_PORT"] = "0"
    env["AIFACTORY_AUTONOMOUS_PIPELINE"] = "0"
    env["AIFACTORY_PIPELINE_MIRROR_JSON"] = "0"
    # Preserve an explicit provider config supplied by the parent deployment.
    # Certification/custom deployments may intentionally point at a shared config outside
    # data_root; overwriting it here made tenant workers silently lose the parent's provider.
    if not str(env.get("AIFACTORY_MODEL_PROVIDERS") or "").strip():
        shared_providers = data_root() / "config" / "model_providers.yaml"
        if shared_providers.exists():
            env["AIFACTORY_MODEL_PROVIDERS"] = str(shared_providers)
    return env


class TenantWorkerSupervisor:
    def __init__(self) -> None:
        self.children: dict[str, subprocess.Popen] = {}
        self.idle_since: dict[str, float] = {}
        self.running = True
        self.max_workers = max(1, int(os.environ.get("AIFACTORY_TENANT_MAX_WORKERS", "8")))
        self.idle_shutdown_sec = max(
            30.0, float(os.environ.get("AIFACTORY_TENANT_WORKER_IDLE_SHUTDOWN_SEC", "300"))
        )

    def stop(self, *_args) -> None:
        self.running = False

    def _reap(self) -> None:
        for ws, proc in list(self.children.items()):
            code = proc.poll()
            if code is None:
                continue
            logger.warning("tenant worker exited workspace=%s code=%s", ws, code)
            self.children.pop(ws, None)
            self.idle_since.pop(ws, None)

    def _start(self, root: Path) -> None:
        ws = root.name
        if ws in self.children or len(self.children) >= self.max_workers:
            return
        log_path = root / "logs" / "pipeline-worker.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_handle = open(log_path, "ab", buffering=0)
        proc = subprocess.Popen(
            [sys.executable, "-m", "pipeline_worker"],
            cwd="/app" if Path("/app").exists() else str(Path(__file__).resolve().parent),
            env=_env_for(root),
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        log_handle.close()
        self.children[ws] = proc
        self.idle_since.pop(ws, None)
        logger.info("started isolated tenant worker workspace=%s pid=%s", ws, proc.pid)

    def _stop_child(self, ws: str) -> None:
        proc = self.children.pop(ws, None)
        self.idle_since.pop(ws, None)
        if proc is None or proc.poll() is not None:
            return
        try:
            os.killpg(proc.pid, signal.SIGTERM)
            proc.wait(timeout=10)
        except Exception:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except Exception:
                pass
        logger.info("stopped idle tenant worker workspace=%s", ws)

    def run(self) -> None:
        logger.info("tenant worker supervisor started max_workers=%s", self.max_workers)
        while self.running:
            self._reap()
            now = time.time()
            for root in _tenant_dirs():
                ws = root.name
                active = _has_active_work(root)
                if active:
                    self.idle_since.pop(ws, None)
                    self._start(root)
                    continue
                if ws in self.children:
                    since = self.idle_since.setdefault(ws, now)
                    if now - since >= self.idle_shutdown_sec:
                        self._stop_child(ws)
            time.sleep(2.0)
        for ws in list(self.children):
            self._stop_child(ws)


def main() -> int:
    supervisor = TenantWorkerSupervisor()
    signal.signal(signal.SIGTERM, supervisor.stop)
    signal.signal(signal.SIGINT, supervisor.stop)
    supervisor.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
