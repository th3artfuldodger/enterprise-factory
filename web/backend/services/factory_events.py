"""Append-only event journal for live Factory Floor movement and decisions."""
from __future__ import annotations

import json
import os
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from core.paths import data_root

_LOCK = threading.Lock()
_MAX_READ_BYTES = 2_000_000


def _path() -> Path:
    p = data_root() / "state" / "factory_events.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def append_factory_event(
    event_type: str,
    *,
    product_id: str | None = None,
    task_id: str | None = None,
    source: str | None = None,
    target: str | None = None,
    status: str | None = None,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    event = {
        "event_id": f"evt-{uuid.uuid4().hex[:14]}",
        "event_type": str(event_type),
        "time": time.time(),
        "product_id": product_id,
        "task_id": task_id,
        "source": source,
        "target": target,
        "status": status,
        "payload": payload or {},
    }
    line = json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n"
    path = _path()
    with _LOCK:
        with path.open("a", encoding="utf-8") as fh:
            fh.write(line)
    return event


def recent_factory_events(*, limit: int = 250, product_id: str | None = None) -> list[dict[str, Any]]:
    path = _path()
    if not path.is_file():
        return []
    try:
        size = path.stat().st_size
        with path.open("rb") as fh:
            if size > _MAX_READ_BYTES:
                fh.seek(max(0, size - _MAX_READ_BYTES))
                fh.readline()
            raw = fh.read().decode("utf-8", errors="replace")
    except OSError:
        return []
    out: list[dict[str, Any]] = []
    for line in reversed(raw.splitlines()):
        try:
            row = json.loads(line)
        except Exception:
            continue
        if product_id and str(row.get("product_id") or "") != str(product_id):
            continue
        out.append(row)
        if len(out) >= max(1, min(int(limit), 1000)):
            break
    out.reverse()
    return out


def latest_task_event(task_id: str, event_types: set[str] | None = None) -> dict[str, Any] | None:
    tid = str(task_id or "")
    if not tid:
        return None
    for row in reversed(recent_factory_events(limit=600)):
        if str(row.get("task_id") or "") != tid:
            continue
        if event_types and str(row.get("event_type") or "") not in event_types:
            continue
        return row
    return None
