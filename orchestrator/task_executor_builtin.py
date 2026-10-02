"""
Built-in pipeline tasks (__complete__, __runtime_test__).
"""

from __future__ import annotations

import logging
import time
import uuid
from typing import TYPE_CHECKING

from core.agent_roles import is_developer_agent

if TYPE_CHECKING:
    from orchestrator.task_executor_helpers import PipelineTaskExecutorHost

logger = logging.getLogger("pipeline-worker")


async def run_builtin_task(
    host: PipelineTaskExecutorHost,
    *,
    agent_type: str,
    task: dict,
    products: dict,
    task_queue: list,
    product: dict,
    pid: str,
    task_id: str,
) -> bool:
    """Run built-in task types. Returns True when ``agent_type`` was handled."""
    if agent_type == "__complete__":
        task["status"] = "completed"
        task["completed_at"] = time.time()
        task["output_data"] = {"completed": True, "product_id": pid}
        task["output_summary"] = f"Product {pid} pipeline completed"
        products[pid]["state"] = "COMPLETED"
        products[pid]["updated_at"] = time.time()
        logger.info(f"Product {pid} pipeline completed!")
        return True

    if agent_type == "__landing_spec__":
        from core.paths import resolve_data_root
        from orchestrator.landing_fast_flow import resolve_style_preset, write_landing_mini_spec

        preset_id = str(product.get("style_preset_id") or "").strip() or None
        preset = resolve_style_preset(
            preset_id,
            product_id=pid,
            idea=str(product.get("idea") or ""),
        )
        spec_inner = write_landing_mini_spec(
            pid,
            idea=str(product.get("idea") or ""),
            preset=preset,
            data_root=resolve_data_root(host.data_root),
            admin_instructions=str(product.get("admin_instructions") or ""),
            agent_to_website=bool(product.get("agent_to_website")),
        )
        product["spec"] = spec_inner
        product["style_preset_id"] = preset.get("id", "")
        product["state"] = "SPEC_WRITTEN"
        product["updated_at"] = time.time()
        task["status"] = "completed"
        task["completed_at"] = time.time()
        task["output_data"] = {"specification": spec_inner, "style_preset": preset}
        task["output_summary"] = f"Landing mini-spec written ({preset.get('id', 'preset')})"
        next_task = host._create_next_task(product)
        if next_task and not any(
            t.get("product_id") == pid
            and t.get("agent_type") == next_task["agent_type"]
            and t.get("state") == next_task["state"]
            and t.get("status") in ("pending", "running")
            for t in task_queue
        ):
            task_queue.append(next_task)
            host._audit_agent_handoff(
                product_id=pid,
                from_agent="__landing_spec__",
                from_state="IDEA_RECEIVED",
                next_task=next_task,
                task_id=task_id,
                reason="landing_mini_spec_ready",
            )
        logger.info("Landing mini-spec ready for %s (preset=%s)", pid, preset.get("id"))
        return True

    if agent_type == "__department_manager_review__":
        import json
        # SQL workers intentionally load only runnable tasks for efficiency. Empire manager
        # review is different: it must see the completed research rows that fed this stage.
        review_tasks = task_queue
        persistence = getattr(host, "_persistence", None)
        store = getattr(persistence, "_async_store", None)
        get_all_tasks = getattr(store, "get_all_tasks", None)
        if callable(get_all_tasks):
            try:
                persisted_tasks = await get_all_tasks()
                if isinstance(persisted_tasks, list):
                    review_tasks = persisted_tasks
            except Exception:
                logger.debug("Empire manager could not load completed task history", exc_info=True)
        research: dict[str, dict] = {}
        for prior in review_tasks:
            if prior.get("product_id") != pid or str(prior.get("status") or "").lower() != "completed":
                continue
            inp = prior.get("input_data") or {}
            lens = str(inp.get("empire_research_lens") or "")
            if not lens:
                continue
            out = prior.get("output_data") or {}
            if isinstance(out, dict) and "factory_assignment_result" in out:
                out = out.get("factory_assignment_result") or {}
            evidence = (out.get("evidence") if isinstance(out, dict) else None) or []
            if not evidence and isinstance(out, dict):
                market_research = out.get("market_research") or {}
                nested_evidence = market_research.get("evidence") if isinstance(market_research, dict) else None
                if isinstance(nested_evidence, dict):
                    evidence = nested_evidence.get("sources") or []
                elif nested_evidence:
                    evidence = nested_evidence
            research[lens] = {
                "agent_id": inp.get("personnel_id") or prior.get("assigned_to"),
                "directive": inp.get("assignment_directive"),
                "result": out,
                "evidence": evidence if isinstance(evidence, list) else [evidence],
            }
        required = {"need", "money", "competition", "ai_advantage", "feasibility"}
        missing = sorted(required - set(research))
        evidence_missing = sorted(
            lens for lens in required
            if lens in research and not (research[lens].get("evidence") or [])
        )
        coverage_confidence = max(0.0, 100.0 - len(missing) * 20.0)
        evidence_confidence = max(0.0, 100.0 - len(evidence_missing) * 20.0)
        confidence = round(min(coverage_confidence, evidence_confidence), 1)
        primary_risk = {
            "risk_score_0_100": round(max(30.0 + len(missing) * 14.0, 100.0 - confidence), 1),
            "missing_research_lenses": missing,
            "lenses_without_evidence": evidence_missing,
        }
        challenge_notes = [f"Missing research lens: {name}" for name in missing]
        challenge_notes += [f"Research lens has no supporting evidence: {name}" for name in evidence_missing]
        if not challenge_notes:
            challenge_notes = ["All five research lenses reported with supporting evidence; package ready for Ultron review."]
        review = {
            "manager_id": (task.get("input_data") or {}).get("manager_id") or task.get("assigned_to"),
            "confidence": confidence,
            "challenge_notes": challenge_notes,
            "reviewed_at": time.time(),
        }
        product["empire_research_packet"] = research
        product["empire_primary_risk"] = primary_risk
        product["empire_manager_review"] = review
        product["updated_at"] = time.time()
        task["status"] = "completed"
        task["completed_at"] = time.time()
        task["output_data"] = {"research_packet": research, "primary_risk": primary_risk, "manager_review": review}
        task["output_summary"] = f"Department manager review complete; confidence={confidence:.0f}"
        return True

    if agent_type == "__ultron_review__":
        from web.backend.services.ultron_oversight import audit_package, consolidate_decision
        inp = task.get("input_data") or {}
        research_packet = dict(product.get("empire_research_packet") or {})
        primary_risk = dict(product.get("empire_primary_risk") or {})
        manager_review = dict(product.get("empire_manager_review") or {})
        funding = None
        funding_request_id = str(inp.get("funding_request_id") or "")
        if funding_request_id:
            try:
                from web.backend.services.funding_utility import get_request
                funding = get_request(funding_request_id)
            except Exception:
                funding = None
        audit = audit_package(
            workspace_id=str(product.get("workspace_id") or inp.get("workspace_id") or "default"),
            product_id=pid,
            department=str(inp.get("department") or product.get("empire_department") or "general"),
            research_packet=research_packet,
            manager_review=manager_review,
            funding_request=funding,
        )
        package = consolidate_decision(
            research_packet=research_packet,
            primary_risk=primary_risk,
            manager_review=manager_review,
            ultron_audit=audit,
            funding_review=funding,
        )
        product["ultron_audit"] = audit
        product["empire_decision_package"] = package
        product["updated_at"] = time.time()
        task["status"] = "completed"
        task["completed_at"] = time.time()
        task["output_data"] = {"audit": audit, "consolidated": package}
        task["output_summary"] = f"Ultron review: {audit.get('recommendation')}"
        return True

    # Runtime test stage between developer and hardening.
    if agent_type == "__runtime_test__":
        runtime_result = host._run_runtime_tests(pid, task_queue)
        task["status"] = "completed" if runtime_result.get("passed") else "failed"
        task["completed_at"] = time.time()
        task["output_data"] = runtime_result
        task["output_summary"] = "runtime tests passed" if runtime_result.get("passed") else "runtime tests failed"
        if runtime_result.get("passed"):
            products[pid]["state"] = "CODE_TESTING"
            products[pid]["updated_at"] = time.time()
            next_task = host._create_next_task(products[pid])
            if next_task and not any(
                t.get("product_id") == pid
                and t.get("agent_type") == next_task["agent_type"]
                and t.get("state") == next_task["state"]
                and t.get("status") in ("pending", "running")
                for t in task_queue
            ):
                task_queue.append(next_task)
                host._audit_agent_handoff(
                    product_id=pid,
                    from_agent="__runtime_test__",
                    from_state="CODE_COMMITTED",
                    next_task=next_task,
                    task_id=task_id,
                    reason="runtime_test_passed",
                )
            logger.info("Runtime tests passed for %s", pid)
        else:
            products[pid]["state"] = "BUG_FOUND"
            products[pid]["updated_at"] = time.time()
            products[pid]["last_bug_context"] = {
                "source": "runtime_test",
                "runtime_test_results": runtime_result.get("results", []),
            }
            exists = any(
                t.get("product_id") == pid
                and is_developer_agent(t.get("agent_type"))
                and t.get("state") == "DEV_FIXING"
                and t.get("status") in ("pending", "running")
                for t in task_queue
            )
            if not exists:
                runtime_dev_task = {
                    "id": f"task-{uuid.uuid4().hex[:12]}",
                    "product_id": pid,
                    "agent_type": "developer",
                    "state": "DEV_FIXING",
                    "status": "pending",
                    "retry_count": 0,
                    "max_retries": 3,
                    "input_data": {
                        "product_id": pid,
                        "idea": product.get("idea", ""),
                        "runtime_test_results": runtime_result.get("results", []),
                        "admin_instructions": (
                            "Runtime tests failed. Fix import/runtime issues and make tests pass before hardening."
                        ),
                    },
                    "created_at": time.time(),
                    "priority": host._get_priority("developer"),
                }
                task_queue.append(runtime_dev_task)
                host._audit_agent_handoff(
                    product_id=pid,
                    from_agent="__runtime_test__",
                    from_state="CODE_COMMITTED",
                    next_task=runtime_dev_task,
                    task_id=task_id,
                    reason="runtime_test_failed",
                    success=False,
                )
            logger.warning("Runtime tests failed for %s; queued developer fix", pid)
        return True

    return False
