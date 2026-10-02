"""Independent Ultron review layer.

Ultron does not execute spending. It audits evidence and management packages,
challenges assumptions, performs a secondary risk assessment, and escalates
owner decisions.
"""
from __future__ import annotations

import hashlib
import json
import time
from typing import Any

from web.backend.services.empire_architecture import ULTRON_ID

_REQUIRED_RESEARCH_LENSES = ("need", "money", "competition", "ai_advantage", "feasibility")


def _evidence_count(packet: dict[str, Any]) -> int:
    total = 0
    for lens in _REQUIRED_RESEARCH_LENSES:
        section = packet.get(lens) or {}
        if isinstance(section, dict):
            total += len(section.get("evidence") or [])
    return total


def _lens_research(packet: dict[str, Any], lens: str) -> dict[str, Any]:
    """Return the model-produced research body from an Empire lens wrapper."""
    section = packet.get(lens) or {}
    if not isinstance(section, dict):
        return {}
    result = section.get("result") or {}
    if not isinstance(result, dict):
        return {}
    research = result.get("market_research") or result
    return research if isinstance(research, dict) else {}


def _score_risk(packet: dict[str, Any], manager_review: dict[str, Any]) -> dict[str, Any]:
    feasibility_research = _lens_research(packet, "feasibility")
    competition_research = _lens_research(packet, "competition")
    feasibility = float(
        feasibility_research.get("score")
        or feasibility_research.get("opportunity_score_0_10")
        or 0
    )
    competition_raw = competition_research.get("intensity_score")
    competition = float(competition_raw) if competition_raw is not None else 0.0
    confidence = float(manager_review.get("confidence") or 0)
    evidence = _evidence_count(packet)
    missing = [lens for lens in _REQUIRED_RESEARCH_LENSES if not isinstance(packet.get(lens), dict)]
    risk = 50.0
    risk += max(0.0, 6.0 - feasibility) * 6.0
    risk += max(0.0, competition - 6.0) * 3.0
    risk += max(0.0, 60.0 - confidence) * 0.25
    risk += len(missing) * 12.0
    if evidence < 5:
        risk += (5 - evidence) * 4.0
    return {
        "secondary_risk_score_0_100": round(max(0.0, min(100.0, risk)), 1),
        "missing_research_lenses": missing,
        "evidence_items": evidence,
    }


def audit_package(
    *,
    workspace_id: str,
    product_id: str,
    department: str,
    research_packet: dict[str, Any],
    manager_review: dict[str, Any],
    funding_request: dict[str, Any] | None = None,
) -> dict[str, Any]:
    risk = _score_risk(research_packet, manager_review)
    challenges: list[str] = []
    if risk["missing_research_lenses"]:
        challenges.append("Research packet is incomplete across required lenses.")
    if risk["evidence_items"] < 5:
        challenges.append("Evidence density is too low for a high-confidence decision.")
    if float(manager_review.get("confidence") or 0) < 60:
        challenges.append("Manager confidence is below 60; assumptions require challenge.")
    if float(risk.get("secondary_risk_score_0_100") or 0) >= 70:
        challenges.append("Secondary risk score is 70 or higher; assumptions require challenge.")
    if funding_request and float(funding_request.get("amount_usd") or 0) >= 5000:
        challenges.append("Capital request is owner-locked and requires full decision-card analysis.")
    recommendation = "proceed_to_owner" if not challenges else "challenge_and_revise"
    payload = {
        "overseer_id": ULTRON_ID,
        "workspace_id": workspace_id,
        "product_id": product_id,
        "department": department,
        "secondary_risk": risk,
        "challenges": challenges,
        "recommendation": recommendation,
        "manager_review": manager_review,
        "funding_request_id": (funding_request or {}).get("id"),
        "audited_at": time.time(),
    }
    payload["audit_fingerprint"] = hashlib.sha256(
        json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()
    return payload


def consolidate_decision(
    *,
    research_packet: dict[str, Any],
    primary_risk: dict[str, Any],
    manager_review: dict[str, Any],
    ultron_audit: dict[str, Any],
    funding_review: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "research_packet": research_packet,
        "primary_risk": primary_risk,
        "manager_review": manager_review,
        "ultron_secondary_risk": ultron_audit.get("secondary_risk"),
        "ultron_challenges": ultron_audit.get("challenges") or [],
        "funding_review": funding_review,
        "owner_action_required": bool(
            (funding_review or {}).get("status") == "owner_approval_required"
            or ultron_audit.get("recommendation") == "challenge_and_revise"
        ),
        "assembled_at": time.time(),
    }
