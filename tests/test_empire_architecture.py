from web.backend.services.empire_architecture import (
    DEPARTMENTS,
    FUNDING_UTILITY_ROLES,
    RESEARCH_AGENT_KINDS,
    architecture_summary,
)


def test_empire_has_exact_organization_shape():
    summary = architecture_summary()
    assert len(DEPARTMENTS) == 15
    assert len(RESEARCH_AGENT_KINDS) == 5
    assert summary["department_count"] == 15
    assert summary["research_agents_per_department"] == 5
    assert summary["research_agent_count"] == 75
    labels = [d["label"] for d in summary["departments"]]
    assert "Health & Wellness" in labels
    assert "Entertainment & Hobbies" in labels
    assert summary["ultron_id"] == "ultron"
    assert summary["factory_manager_id"] == "factory-manager"


def test_every_department_has_manager_and_five_research_workers():
    summary = architecture_summary()
    nodes = summary["nodes"]
    for department in DEPARTMENTS:
        slug = department["slug"]
        managers = [n for n in nodes if n["id"] == f"department-manager:{slug}"]
        workers = [n for n in nodes if n.get("division") == slug and n.get("kind") == "research_agent"]
        assert len(managers) == 1
        assert managers[0]["reports_to"] == "factory-manager"
        assert len(workers) == 5
        assert {w["research_lens"] for w in workers} == {a["slug"] for a in RESEARCH_AGENT_KINDS}
        assert all(w["reports_to"] == managers[0]["id"] for w in workers)


def test_funding_utility_is_separate_and_request_only():
    summary = architecture_summary()
    funding = summary["funding_utility"]
    assert funding["separate_from_factory"] is True
    assert funding["ai_authority"] == "request_only"
    role_ids = {r["id"] for r in FUNDING_UTILITY_ROLES}
    assert "funding:verifier" in role_ids
    assert "funding:auditor" in role_ids
    assert "funding:capital-router" in role_ids
