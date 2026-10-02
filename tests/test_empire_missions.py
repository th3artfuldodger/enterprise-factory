from pathlib import Path

from orchestrator.sqlite_manager import SQLiteManager
from web.backend.services import empire_missions


def test_mission_creates_five_research_lenses_then_manager_then_ultron(tmp_path, monkeypatch):
    ws = "customer-test"
    db = tmp_path / "state" / "pipeline.db"
    db.parent.mkdir(parents=True)

    monkeypatch.setattr(
        empire_missions,
        "customer_workspace_context",
        lambda _customer_id: {
            "workspace_id": ws,
            "tenant_root": str(tmp_path),
            "pipeline_db": str(db),
        },
    )

    result = empire_missions.create_customer_mission(
        "cust-test",
        "Build a better financial budgeting assistant for freelancers",
    )

    assert result["workspace_id"] == ws
    assert result["department"] == "personal_finance"
    assert len(result["research_agents"]) == 5

    sm = SQLiteManager(str(db), workspace_id=ws)
    sm.connect()
    try:
        products = sm.get_all_products()
        tasks = sm.get_all_tasks()
    finally:
        sm.close()

    assert len(products) == 1
    assert products[0]["workspace_id"] == ws
    assert len(tasks) == 7
    ordered = sorted(tasks, key=lambda row: (row.get("priority", 999), row.get("created_at", 0)))
    lenses = [(row.get("input_data") or {}).get("empire_research_lens") for row in ordered[:5]]
    assert lenses == ["need", "money", "competition", "ai_advantage", "feasibility"]
    assert ordered[5]["agent_type"] == "__department_manager_review__"
    assert ordered[6]["agent_type"] == "__ultron_review__"


def test_manager_review_loads_completed_empire_research_from_sql_history():
    import asyncio
    from types import SimpleNamespace
    from orchestrator.task_executor_builtin import run_builtin_task

    pid = "prod-test"
    lenses = ("need", "money", "competition", "ai_advantage", "feasibility")
    persisted = []
    for lens in lenses:
        persisted.append({
            "id": f"t-{lens}",
            "product_id": pid,
            "agent_type": "analyst",
            "status": "completed",
            "input_data": {"empire_research_lens": lens, "personnel_id": f"agent-{lens}"},
            "output_data": {"factory_assignment_result": {"evidence": [{"source": lens}], "summary": f"{lens} result"}},
        })

    class Store:
        async def get_all_tasks(self):
            return persisted

    host = SimpleNamespace(_persistence=SimpleNamespace(_async_store=Store()))
    task = {
        "id": "mgr",
        "product_id": pid,
        "agent_type": "__department_manager_review__",
        "assigned_to": "department-manager:test",
        "input_data": {"manager_id": "department-manager:test"},
        "status": "running",
    }
    products = {pid: {"id": pid, "workspace_id": "ws", "empire_department": "small_business"}}

    handled = asyncio.run(run_builtin_task(
        host,
        agent_type="__department_manager_review__",
        task=task,
        products=products,
        task_queue=[task],
        product=products[pid],
        pid=pid,
        task_id="mgr",
    ))

    assert handled is True
    assert task["status"] == "completed"
    assert set(products[pid]["empire_research_packet"]) == set(lenses)
    assert products[pid]["empire_manager_review"]["confidence"] == 100.0


def test_empire_lens_forces_fresh_analyst_research_even_when_shared_artifact_exists(tmp_path, monkeypatch):
    import asyncio
    from unittest.mock import AsyncMock
    from agents.analyst import MarketResearchAgent
    from agents.base_agent import AgentInput
    import core.paths

    existing = tmp_path / "market_research.json"
    existing.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(core.paths, "market_research_path", lambda _pid: existing)

    agent = MarketResearchAgent(object())
    agent._run_research = AsyncMock(return_value="fresh-research")
    agent._run_monitoring = AsyncMock(return_value="monitoring")

    inp = AgentInput(
        task_id="t-money",
        product_id="p1",
        agent_type="analyst",
        data={"idea": "roofing leads", "empire_research_lens": "money", "assignment_directive": "Research unit economics."},
    )
    result = asyncio.run(agent.execute(inp))

    assert result == "fresh-research"
    agent._run_research.assert_awaited_once()
    agent._run_monitoring.assert_not_awaited()
