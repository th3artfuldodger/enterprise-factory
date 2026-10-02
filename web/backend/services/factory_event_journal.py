"""Durable event journal for Factory Floor live movement and operator provenance."""
from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any

from core.paths import data_root


def _path() -> Path:
    p = data_root() / "logs" / "factory_floor_events.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def emit_factory_event(
    event_type: str,
    *,
    product_id: str | None = None,
    source: str | None = None,
    target: str | None = None,
    task_id: str | None = None,
    status: str | None = None,
    ecosystem: str | None = None,
    manager_id: str | None = None,
    summary: str = "",
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    event = {
        "id": f"ffe-{uuid.uuid4().hex[:14]}",
        "type": str(event_type or "event"),
        "time": time.time(),
        "product_id": product_id,
        "source": source,
        "target": target,
        "task_id": task_id,
        "status": status,
        "ecosystem": ecosystem,
        "manager_id": manager_id,
        "summary": str(summary or "")[:1000],
        "metadata": metadata or {},
    }
    with _path().open("a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False, default=str) + "\n")
    return event


def recent_factory_events(*, limit: int = 300, product_id: str | None = None) -> list[dict[str, Any]]:
    p = _path()
    if not p.is_file():
        return []
    try:
        lines = p.read_text(encoding="utf-8", errors="replace").splitlines()[-max(1, min(int(limit), 2000)):]
    except OSError:
        return []
    out: list[dict[str, Any]] = []
    for line in lines:
        try:
            row = json.loads(line)
        except Exception:
            continue
        if not isinstance(row, dict):
            continue
        if product_id and str(row.get("product_id") or "") != str(product_id):
            continue
        out.append(row)
    return out
