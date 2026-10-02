import json

from orchestrator.sqlite_manager import SQLiteManager
from web.backend.services import factory_assignments as assignments
from web.backend.services import factory_personnel as personnel


def test_manager_can_append_tasks_to_subordinate_queue(tmp_path, monkeypatch):
    personnel_path = tmp_path / "factory_personnel.json"
    db_path = tmp_path / "pipeline.db"
    monkeypatch.setattr(personnel, "_path", lambda: personnel_path)
    monkeypatch.setattr(assignments, "pipeline_db_path", lambda: db_path)

    manager = personnel.create_personnel(
        "Manager who oversees research workers and assigns work",
        role_class="manager",
        label="Research Manager",
    )
    worker = personnel.create_personnel(
        "AI worker that researches competitors",
        role_class="worker",
        label="Competitor Bot",
    )

    sm = SQLiteManager(str(db_path))
    sm.connect()
    sm.upsert_product(
        {
            "id": "product-1",
            "idea": "Research a new market",
            "state": "IDEA_RECEIVED",
            "metadata": {},
        }
    )
    sm.close()

    first = assignments.delegate_manager_task(
        manager_id=manager["id"],
        worker_id=worker["id"],
        product_id="product-1",
        directive="Compare the three strongest competitors.",
    )
    second = assignments.delegate_manager_task(
        manager_id=manager["id"],
        worker_id=worker["id"],
        product_id="product-1",
        directive="Then compare their pricing and summarize the risks.",
    )

    roster = personnel.personnel_map()
    assert roster[worker["id"]]["supervisor_id"] == manager["id"]
    assert roster[worker["id"]]["description"] == "AI worker that researches competitors"

    sm = SQLiteManager(str(db_path))
    sm.connect()
    rows = sm.conn.execute(
        "SELECT id, assigned_to, status, input FROM tasks WHERE workspace_id = ? ORDER BY created_at ASC",
        (sm.workspace_id,),
    ).fetchall()
    sm.close()

    assert [row["id"] for row in rows] == [first["task_id"], second["task_id"]]
    assert all(row["assigned_to"] == worker["id"] for row in rows)
    assert all(str(row["status"]).lower() == "pending" for row in rows)
    payloads = [json.loads(row["input"]) for row in rows]
    assert [p["assignment_directive"] for p in payloads] == [
        "Compare the three strongest competitors.",
        "Then compare their pricing and summarize the risks.",
    ]
    assert all(p["manager_delegated"] is True for p in payloads)
    assert all(p["delegated_by"] == manager["id"] for p in payloads)


def test_worker_cannot_be_taken_from_another_manager(tmp_path, monkeypatch):
    personnel_path = tmp_path / "factory_personnel.json"
    db_path = tmp_path / "pipeline.db"
    monkeypatch.setattr(personnel, "_path", lambda: personnel_path)
    monkeypatch.setattr(assignments, "pipeline_db_path", lambda: db_path)

    manager_a = personnel.create_personnel("Research manager", role_class="manager", label="Manager A")
    manager_b = personnel.create_personnel("Production manager", role_class="manager", label="Manager B")
    worker = personnel.create_personnel("Research worker", role_class="worker", label="Worker")

    sm = SQLiteManager(str(db_path))
    sm.connect()
    sm.upsert_product({"id": "p", "idea": "Project", "state": "IDEA_RECEIVED", "metadata": {}})
    sm.close()

    assignments.delegate_manager_task(
        manager_id=manager_a["id"],
        worker_id=worker["id"],
        product_id="p",
        directive="First assignment",
    )

    import pytest

    with pytest.raises(ValueError, match="another manager"):
        assignments.delegate_manager_task(
            manager_id=manager_b["id"],
            worker_id=worker["id"],
            product_id="p",
            directive="Unauthorized reassignment",
        )
