from __future__ import annotations

import sqlite3
from pathlib import Path

from orchestrator.sqlite_manager import CURRENT_SCHEMA_VERSION, SQLiteManager


def test_sqlite_schema_version_foreign_keys_and_integrity(tmp_path: Path):
    db = tmp_path / "pipeline.db"
    sm = SQLiteManager(str(db), workspace_id="test-ws")
    sm.connect()
    try:
        sm.upsert_product({"id":"prod-ready0001","workspace_id":"test-ws","idea":"readiness","state":"IDEA_RECEIVED"})
        sm.upsert_task({"id":"task-ready0001","workspace_id":"test-ws","product_id":"prod-ready0001","agent_type":"analyst","status":"pending","state":"TEST","created_at":1.0,"input_data":{}})
        status = sm.integrity_status()
        assert status["ok"] is True
        assert status["schema_version"] == CURRENT_SCHEMA_VERSION
        assert status["journal_mode"].lower() == "wal"
        assert sm.conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    finally:
        sm.close()


def test_foreign_key_blocks_orphan_task(tmp_path: Path):
    db = tmp_path / "pipeline.db"
    sm = SQLiteManager(str(db), workspace_id="test-ws"); sm.connect()
    try:
        try:
            sm.upsert_task({"id":"task-orphan0001","workspace_id":"test-ws","product_id":"prod-missing0001","agent_type":"analyst","status":"pending","state":"TEST","created_at":1.0,"input_data":{}})
        except sqlite3.IntegrityError:
            pass
        else:
            raise AssertionError("orphan task was accepted with foreign_keys=ON")
    finally:
        sm.close()


def test_request_id_round_trip_and_sanitization():
    from fastapi.testclient import TestClient
    from web.backend.main import app
    with TestClient(app) as client:
        r = client.get('/api/health', headers={'X-Request-ID':'factory-test-123'})
        assert r.status_code == 200
        assert r.headers['x-request-id'] == 'factory-test-123'
        assert 'app;dur=' in r.headers['server-timing']
        r2 = client.get('/api/health', headers={'X-Request-ID':'bad request id with spaces'})
        assert r2.status_code == 200
        assert r2.headers['x-request-id'] != 'bad request id with spaces'
        assert len(r2.headers['x-request-id']) >= 16
