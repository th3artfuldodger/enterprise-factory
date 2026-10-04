"""Safe, fixed-target health snapshot for the local Ollama provider."""
from __future__ import annotations

import json
import os
import time
from urllib.request import Request, urlopen

_STATE = {"was_online": None, "recovery_count": 0, "last_recovered_at": None}


def _get_json(url: str, timeout: float = 0.45) -> dict:
    req = Request(url, headers={"Accept": "application/json"})
    with urlopen(req, timeout=timeout) as response:  # nosec B310 - fixed local provider target
        return json.loads(response.read().decode("utf-8"))


def local_ollama_health() -> dict:
    base = os.environ.get("AIFACTORY_OLLAMA_URL", "http://host.docker.internal:11434").rstrip("/")
    started = time.perf_counter()
    checked_at = time.time()
    try:
        tags = _get_json(f"{base}/api/tags")
        version = _get_json(f"{base}/api/version")
        online = True
        error = None
        models = [str(row.get("name") or row.get("model") or "") for row in tags.get("models", []) if row]
    except Exception as exc:
        online = False
        error = type(exc).__name__
        models = []
        version = {}
    previous = _STATE.get("was_online")
    if online and previous is False:
        _STATE["recovery_count"] = int(_STATE.get("recovery_count") or 0) + 1
        _STATE["last_recovered_at"] = checked_at
    _STATE["was_online"] = online
    return {
        "provider": "local_ollama",
        "online": online,
        "status": "online" if online else "offline",
        "version": version.get("version") if isinstance(version, dict) else None,
        "models": models,
        "latency_ms": round((time.perf_counter() - started) * 1000, 1),
        "last_checked_at": checked_at,
        "recovery_count": _STATE["recovery_count"],
        "last_recovered_at": _STATE["last_recovered_at"],
        "error": error,
    }
