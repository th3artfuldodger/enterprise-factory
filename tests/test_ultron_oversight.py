from web.backend.services.ultron_oversight import audit_package


def _packet(feasibility_score: float = 6.0):
    lenses = ("need", "money", "competition", "ai_advantage", "feasibility")
    packet = {}
    for lens in lenses:
        research = {
            "lens": lens,
            "opportunity_score_0_10": feasibility_score if lens == "feasibility" else 7,
            "confidence_0_100": 85,
        }
        packet[lens] = {
            "result": {"market_research": research},
            "evidence": [{"url": f"https://example.test/{lens}"}],
        }
    return packet


def test_ultron_reads_nested_empire_feasibility_score():
    audit = audit_package(
        workspace_id="ws",
        product_id="prod",
        department="small_business",
        research_packet=_packet(6),
        manager_review={"confidence": 100},
    )
    assert audit["secondary_risk"]["secondary_risk_score_0_100"] == 50.0
    assert audit["recommendation"] == "proceed_to_owner"
    assert audit["challenges"] == []


def test_ultron_challenges_high_secondary_risk_even_with_complete_evidence():
    audit = audit_package(
        workspace_id="ws",
        product_id="prod",
        department="small_business",
        research_packet=_packet(2),
        manager_review={"confidence": 100},
    )
    assert audit["secondary_risk"]["secondary_risk_score_0_100"] >= 70
    assert audit["recommendation"] == "challenge_and_revise"
    assert any("Secondary risk" in note for note in audit["challenges"])
