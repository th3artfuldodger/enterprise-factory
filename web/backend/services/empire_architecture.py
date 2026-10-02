"""Canonical Trimble Enterprise organization for the Factory game layer.

This is the product architecture agreed in Building my AI empire:
owner -> Ultron -> Factory Manager -> 15 Department Managers ->
five specialist research agents per department.

The definitions here are data, not decoration.  Other services use the same IDs
for routing, oversight, reports and customer-facing visualization.
"""
from __future__ import annotations

from typing import Any

RESEARCH_AGENT_KINDS: tuple[dict[str, str], ...] = (
    {
        "slug": "need",
        "label": "Need Scout",
        "mission": "Find concrete unmet needs, recurring pain, urgency, and evidence of demand.",
    },
    {
        "slug": "money",
        "label": "Money Scout",
        "mission": "Assess willingness to pay, pricing, market size, revenue paths, and capital needs.",
    },
    {
        "slug": "competition",
        "label": "Competition Scout",
        "mission": "Map direct and indirect competitors, substitutes, gaps, and defensibility.",
    },
    {
        "slug": "ai_advantage",
        "label": "AI Advantage Scout",
        "mission": "Identify where AI creates a material speed, cost, quality, personalization, or automation advantage.",
    },
    {
        "slug": "feasibility",
        "label": "Feasibility Scout",
        "mission": "Assess implementation difficulty, legal/safety constraints, operating requirements, and viability.",
    },
)

DEPARTMENTS: tuple[dict[str, str], ...] = (
    {"slug": "health_wellness", "label": "Health & Wellness"},
    {"slug": "personal_safety", "label": "Personal Safety & Preparedness"},
    {"slug": "personal_finance", "label": "Personal Finance"},
    {"slug": "small_business", "label": "Small Business"},
    {"slug": "education_learning", "label": "Education & Learning"},
    {"slug": "careers_employment", "label": "Careers & Employment"},
    {"slug": "home_household", "label": "Home & Household"},
    {"slug": "pets", "label": "Pets"},
    {"slug": "automotive_transportation", "label": "Automotive & Transportation"},
    {"slug": "gaming_digital_assets", "label": "Gaming & Digital Assets"},
    {"slug": "creators_social_media", "label": "Creators & Social Media"},
    {"slug": "ecommerce_digital_products", "label": "E-commerce & Digital Products"},
    {"slug": "travel_local_experiences", "label": "Travel & Local Experiences"},
    {"slug": "productivity_organization", "label": "Productivity & Organization"},
    {"slug": "entertainment_hobbies", "label": "Entertainment & Hobbies"},
)

FACTORY_MANAGER_ID = "factory-manager"
ULTRON_ID = "ultron"

FUNDING_UTILITY_ROLES: tuple[dict[str, str], ...] = (
    {"id": "funding:grant-scout", "label": "Grant Scout", "mission": "Find grants and public/non-dilutive funding."},
    {"id": "funding:credit-scout", "label": "Credit & Incentive Scout", "mission": "Find tax credits, rebates, and permissible incentives."},
    {"id": "funding:competition-scout", "label": "Competition Scout", "mission": "Find prize competitions and challenge funding."},
    {"id": "funding:accelerator-scout", "label": "Accelerator Scout", "mission": "Find accelerators and programs with legitimate funding or credits."},
    {"id": "funding:sponsorship-scout", "label": "Sponsorship Scout", "mission": "Find sponsorships and partnership funding."},
    {"id": "funding:ai-donation-scout", "label": "AI Donation Scout", "mission": "Find permissible AI-to-AI donations or credits; never solicit loans or contracts."},
    {"id": "funding:verifier", "label": "Funding Verifier", "mission": "Verify eligibility, source, restrictions, destination, duplicates, and amount."},
    {"id": "funding:auditor", "label": "Independent Funding Auditor", "mission": "Independently challenge risk, ROI, evidence, and capital efficiency."},
    {"id": "funding:capital-router", "label": "Capital Router", "mission": "Route only authorized capital and emit matched ledger/tube records."},
)


def department_manager_id(department_slug: str) -> str:
    return f"department-manager:{department_slug}"


def research_agent_id(department_slug: str, agent_slug: str) -> str:
    return f"research:{department_slug}:{agent_slug}"


def department_map() -> dict[str, dict[str, str]]:
    return {str(d["slug"]): dict(d) for d in DEPARTMENTS}


def organization_nodes() -> list[dict[str, Any]]:
    """Return stable hierarchy nodes for Factory Floor / customer game clients."""
    nodes: list[dict[str, Any]] = [
        {
            "id": ULTRON_ID,
            "kind": "overseer",
            "label": "Ultron",
            "role_class": "overseer",
            "division": "command",
            "authority": "audit_only",
            "reports_to": "owner",
            "permissions": [
                "audit_factory",
                "challenge_management",
                "independent_risk_review",
                "consolidate_decisions",
                "escalate_to_owner",
            ],
            "prompt_line": "Independent oversight: challenge assumptions, compare evidence and risk, escalate owner decisions.",
            "virtual_personnel": True,
        },
        {
            "id": FACTORY_MANAGER_ID,
            "kind": "factory_manager",
            "label": "Factory Manager",
            "role_class": "manager",
            "division": "command",
            "authority": "factory_operations",
            "reports_to": ULTRON_ID,
            "permissions": [
                "coordinate_departments",
                "assign_work",
                "review_department_packages",
                "request_funding",
                "escalate_to_ultron",
            ],
            "prompt_line": "Coordinates department managers, task flow, staffing, handoffs, and delivery.",
            "virtual_personnel": True,
        },
    ]
    for department in DEPARTMENTS:
        slug = department["slug"]
        manager_id = department_manager_id(slug)
        nodes.append(
            {
                "id": manager_id,
                "kind": "department_manager",
                "label": f"{department['label']} Manager",
                "role_class": "manager",
                "division": slug,
                "authority": "department",
                "reports_to": FACTORY_MANAGER_ID,
                "permissions": [
                    "assign_department_work",
                    "review_research_packet",
                    "challenge_evidence",
                    "request_cross_department_support",
                    "request_funding",
                ],
                "prompt_line": f"Manages the {department['label']} research team and packages evidence for Factory Manager review.",
                "virtual_personnel": True,
            }
        )
        for agent in RESEARCH_AGENT_KINDS:
            nodes.append(
                {
                    "id": research_agent_id(slug, agent["slug"]),
                    "kind": "research_agent",
                    "label": f"{department['label']} · {agent['label']}",
                    "short_label": agent["label"],
                    "role_class": "worker",
                    "division": slug,
                    "authority": "research_only",
                    "reports_to": manager_id,
                    "permissions": ["perform_research", "attach_evidence", "submit_findings"],
                    "research_lens": agent["slug"],
                    "prompt_line": agent["mission"],
                    "virtual_personnel": True,
                }
            )
    return nodes


def organization_edges() -> list[dict[str, str]]:
    edges: list[dict[str, str]] = [
        {"from": FACTORY_MANAGER_ID, "to": ULTRON_ID, "kind": "management_report"},
    ]
    for department in DEPARTMENTS:
        slug = department["slug"]
        manager_id = department_manager_id(slug)
        edges.append({"from": manager_id, "to": FACTORY_MANAGER_ID, "kind": "management_report"})
        for agent in RESEARCH_AGENT_KINDS:
            edges.append(
                {
                    "from": research_agent_id(slug, agent["slug"]),
                    "to": manager_id,
                    "kind": "research_report",
                }
            )
    return edges


def architecture_summary() -> dict[str, Any]:
    return {
        "owner": {"id": "owner", "label": "Owner"},
        "ultron_id": ULTRON_ID,
        "factory_manager_id": FACTORY_MANAGER_ID,
        "department_count": len(DEPARTMENTS),
        "research_agents_per_department": len(RESEARCH_AGENT_KINDS),
        "research_agent_count": len(DEPARTMENTS) * len(RESEARCH_AGENT_KINDS),
        "departments": [dict(d) for d in DEPARTMENTS],
        "research_lenses": [dict(a) for a in RESEARCH_AGENT_KINDS],
        "nodes": organization_nodes(),
        "edges": organization_edges(),
        "funding_utility": {
            "separate_from_factory": True,
            "ai_authority": "request_only",
            "roles": [dict(role) for role in FUNDING_UTILITY_ROLES],
            "forbidden_without_owner": ["loans", "contracts", "borrowing", "investments", "direct payouts"],
        },
    }
