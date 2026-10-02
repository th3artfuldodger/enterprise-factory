import sqlite3

import pytest

from web.backend.services import funding_utility as funding


@pytest.fixture
def isolated_funding(tmp_path, monkeypatch):
    db = tmp_path / "funding.db"
    monkeypatch.setattr(funding, "funding_db_path", lambda: db)
    monkeypatch.setattr(funding, "notify_owner_if_required", lambda _request: None)
    return db


def _submit(amount, *, preapproved=False):
    if preapproved:
        funding.create_preapproved_budget(
            workspace_id="ws",
            department="small_business",
            product_id="prod-1",
            ceiling_usd=1000,
            approved_by="owner",
        )
    return funding.submit_funding_request(
        workspace_id="ws",
        product_id="prod-1",
        department="small_business",
        requested_by="factory-manager",
        requested_by_label="Factory Manager",
        amount_usd=amount,
        purpose="Fund validated work",
        source_preference="grant",
        restrictions=["research only"],
        preapproved_budget=preapproved,
    )


def test_exact_funding_bands():
    assert funding.funding_band(50, preapproved_budget=True) == "budget_auto"
    assert funding.funding_band(50, preapproved_budget=False) == "enhanced_verification"
    assert funding.funding_band(500) == "enhanced_verification"
    assert funding.funding_band(2500) == "owner_approval"
    assert funding.funding_band(6000) == "owner_locked"


def test_under_100_auto_only_with_preapproved_budget(isolated_funding):
    auto = _submit(50, preapproved=True)
    assert auto["status"] == "authorized"
    assert funding.reconcile_request(auto["id"])["matched"] is True

    manual = _submit(75, preapproved=False)
    assert manual["status"] == "verification_required"


def test_100_to_999_requires_verification_then_authorizes(isolated_funding):
    req = _submit(500)
    assert req["status"] == "verification_required"
    verified = funding.record_verification(
        req["id"], verifier_id="funding:verifier", passed=True, evidence={"eligible": True}
    )
    assert verified["status"] == "authorized"
    assert funding.reconcile_request(req["id"])["matched"] is True


def test_1000_to_4999_requires_owner_after_verification(isolated_funding):
    req = _submit(2500)
    verified = funding.record_verification(
        req["id"], verifier_id="funding:verifier", passed=True, evidence={"eligible": True}
    )
    assert verified["status"] == "owner_approval_required"
    approved = funding.owner_decide(req["id"], approved=True, owner_id="owner")
    assert approved["status"] == "authorized"
    assert funding.reconcile_request(req["id"])["matched"] is True


def test_5000_plus_requires_full_decision_card(isolated_funding):
    req = _submit(6000)
    funding.record_verification(
        req["id"], verifier_id="funding:verifier", passed=True, evidence={"eligible": True}
    )
    with pytest.raises(ValueError, match="decision-card"):
        funding.owner_decide(req["id"], approved=True, owner_id="owner")

    card = funding.build_capital_decision_card(
        funding.get_request(req["id"]),
        roi_low_pct=10,
        roi_high_pct=35,
        break_even_months=18,
        maximum_loss_usd=6000,
        confidence=72,
        risk_score=44,
        market_evidence_summary="Evidence from target customers and competitors.",
        capital_efficiency_summary="Lower-cost path was compared.",
        independent_audit_summary="Funding auditor challenged assumptions.",
        cheaper_alternatives=["Pilot at $1,500", "Delay noncritical spend"],
        plain_language_rationale="Proceed only if the owner accepts the downside.",
    )
    funding.save_decision_card(req["id"], card)
    approved = funding.owner_decide(req["id"], approved=True, owner_id="owner")
    assert approved["status"] == "authorized"


def test_dual_ledgers_are_append_only_and_mismatch_halts(isolated_funding):
    req = _submit(50, preapproved=True)
    with sqlite3.connect(str(isolated_funding)) as conn:
        with pytest.raises(sqlite3.DatabaseError):
            conn.execute(
                "UPDATE factory_capital_ledger SET amount_usd = 999 WHERE request_id = ?",
                (req["id"],),
            )

    with sqlite3.connect(str(isolated_funding)) as conn:
        conn.execute(
            """
            INSERT INTO factory_capital_ledger
            (entry_id, request_id, workspace_id, entry_type, amount_usd, source, destination, restrictions_json, ref, created_at)
            VALUES ('forced-mismatch', ?, 'ws', 'authorization', 1, 'x', 'y', '[]', 'mismatch', 1)
            """,
            (req["id"],),
        )
        conn.commit()
    rec = funding.reconcile_request(req["id"])
    assert rec["matched"] is False
    assert rec["halted"] is True


def test_ai_requester_cannot_impersonate_owner(isolated_funding):
    with pytest.raises(ValueError, match="Factory personnel"):
        funding.submit_funding_request(
            workspace_id="ws",
            product_id="p",
            department="finance",
            requested_by="owner",
            requested_by_label="Owner",
            amount_usd=10,
            purpose="bad",
        )


def test_preapproved_budget_is_real_and_consumed(isolated_funding):
    budget = funding.create_preapproved_budget(
        workspace_id="ws",
        department="small_business",
        product_id="prod-1",
        ceiling_usd=80,
        approved_by="owner",
    )
    first = funding.submit_funding_request(
        workspace_id="ws", product_id="prod-1", department="small_business",
        requested_by="factory-manager", requested_by_label="Factory Manager",
        amount_usd=50, purpose="first", preapproved_budget=True,
    )
    assert first["status"] == "authorized"
    budgets = funding.list_preapproved_budgets(workspace_id="ws")
    assert budgets[0]["id"] == budget["id"]
    assert budgets[0]["used_usd"] == 50

    second = funding.submit_funding_request(
        workspace_id="ws", product_id="prod-1", department="small_business",
        requested_by="factory-manager", requested_by_label="Factory Manager",
        amount_usd=50, purpose="second", preapproved_budget=True,
    )
    assert second["status"] == "verification_required"
    assert second["preapproved_budget"] is False


def test_funding_opportunity_lifecycle_is_ordered(isolated_funding):
    opp = funding.create_funding_opportunity(
        workspace_id="ws",
        scout_id="funding:grant-scout",
        opportunity_type="grant",
        title="Innovation grant",
        amount_estimate_usd=50000,
        evidence={"source": "official"},
    )
    assert opp["status"] == "found"
    for state in ("eligible", "application_ready", "submitted", "awarded", "received"):
        opp = funding.advance_funding_opportunity(opp["id"], next_status=state)
        assert opp["status"] == state
    with pytest.raises(ValueError, match="Invalid funding transition"):
        funding.advance_funding_opportunity(opp["id"], next_status="eligible")
