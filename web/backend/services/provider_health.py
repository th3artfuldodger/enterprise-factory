"""Safe health snapshot for the configured local Ollama provider."""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen

import yaml

from core.paths import data_root

_STATE = {"was_online": None, "recovery_count": 0, "last_recovered_at": None}
_ALLOWED_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", "host.docker.internal"}


def _get_json(url: str, timeout: float = 0.45) -> dict:
    req = Request(url, headers={"Accept": "application/json"})
    with urlopen(req, timeout=timeout) as response:  # nosec B310 - validated local provider target
        return json.loads(response.read().decode("utf-8"))


def _validated_local_url(value: str) -> str | None:
    try:
        parsed = urlparse(value)
    except Exception:
        return None
    if parsed.scheme not in {"http", "https"} or parsed.hostname not in _ALLOWED_LOCAL_HOSTS:
        return None
    return value.rstrip("/")


def configured_ollama_base_url() -> str:
    override = (os.environ.get("AIFACTORY_OLLAMA_URL") or "").strip()
    if override:
        safe = _validated_local_url(override)
        if safe:
            return safe
    cfg_path = Path(os.environ.get("AIFACTORY_MODEL_PROVIDERS") or (data_root() / "config" / "model_providers.yaml"))
    try:
        cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
        default = str(cfg.get("default_provider") or "local_ollama")
        providers = cfg.get("providers") or {}
        candidates = [default, "local_ollama"]
        for name in candidates:
            row = providers.get(name) or {}
            if str(row.get("provider_type") or "") in {"local_ollama", "ollama"} or name == "local_ollama":
                safe = _validated_local_url(str(row.get("base_url") or ""))
                if safe:
                    return safe
    except Exception:
        pass
    return "http://host.docker.internal:11434"


def local_ollama_health() -> dict:
    base = configured_ollama_base_url()
    started = time.perf_counter(); checked_at = time.time()
    try:
        tags = _get_json(f"{base}/api/tags"); version = _get_json(f"{base}/api/version")
        online = True; error = None
        models = [str(row.get("name") or row.get("model") or "") for row in tags.get("models", []) if row]
    except Exception as exc:
        online = False; error = type(exc).__name__; models = []; version = {}
    previous = _STATE.get("was_online")
    if online and previous is False:
        _STATE["recovery_count"] = int(_STATE.get("recovery_count") or 0) + 1
        _STATE["last_recovered_at"] = checked_at
    _STATE["was_online"] = online
    return {
        "provider": "local_ollama", "base_url": base, "online": online,
        "status": "online" if online else "offline",
        "version": version.get("version") if isinstance(version, dict) else None,
        "models": models, "latency_ms": round((time.perf_counter()-started)*1000,1),
        "last_checked_at": checked_at, "recovery_count": _STATE["recovery_count"],
        "last_recovered_at": _STATE["last_recovered_at"], "error": error,
    }
