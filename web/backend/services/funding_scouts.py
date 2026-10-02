"""Funding Utility scouts: public-source discovery into the funding lifecycle."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from director.discovery_pipeline import _search_rss_fallback
from web.backend.services.funding_utility import create_funding_opportunity

_SCOUT_QUERIES: tuple[tuple[str, str, str], ...] = (
    ("funding:grant-scout", "grant", "grants funding opportunities"),
    ("funding:credit-scout", "credit_incentive", "tax credits rebates incentives"),
    ("funding:competition-scout", "competition", "prize competition challenge funding"),
    ("funding:accelerator-scout", "accelerator", "accelerator program startup funding"),
    ("funding:sponsorship-scout", "sponsorship", "sponsorship partnership funding"),
    ("funding:ai-donation-scout", "ai_credit", "AI startup cloud credits compute credits programs"),
)


def discover_funding_opportunities(
    *,
    workspace_id: str,
    project_idea: str,
    product_id: str | None = None,
    max_per_scout: int = 3,
) -> dict[str, Any]:
    idea = str(project_idea or "").strip()
    if not idea:
        raise ValueError("Project idea is required")
    limit = max(1, min(int(max_per_scout), 5))

    def search(row: tuple[str, str, str]) -> tuple[str, str, list[dict[str, str]]]:
        scout_id, opportunity_type, suffix = row
        query = f"{idea[:260]} {suffix}"
        return scout_id, opportunity_type, _search_rss_fallback(query, max_results=limit)

    results: list[tuple[str, str, list[dict[str, str]]]] = []
    with ThreadPoolExecutor(max_workers=len(_SCOUT_QUERIES)) as pool:
        futures = [pool.submit(search, row) for row in _SCOUT_QUERIES]
        for future in as_completed(futures):
            try:
                results.append(future.result())
            except Exception:
                continue

    created: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    for scout_id, opportunity_type, hits in results:
        for hit in hits[:limit]:
            url = str(hit.get("url") or "").strip()
            title = str(hit.get("title") or "").strip()
            if not url or not title or url in seen_urls:
                continue
            seen_urls.add(url)
            created.append(
                create_funding_opportunity(
                    workspace_id=workspace_id,
                    scout_id=scout_id,
                    opportunity_type=opportunity_type,
                    title=title,
                    source_url=url,
                    restrictions=[],
                    evidence={
                        "product_id": product_id,
                        "project_idea": idea[:1000],
                        "snippet": str(hit.get("snippet") or "")[:1200],
                        "discovery_method": "public_rss_search",
                    },
                )
            )
    return {
        "workspace_id": workspace_id,
        "product_id": product_id,
        "scouts_run": len(_SCOUT_QUERIES),
        "opportunities_found": len(created),
        "opportunities": created,
    }
