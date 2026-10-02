from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field

from web.backend.core.admin_roles import AdminRole, normalize_role, require_admin_with_rbac
from web.backend.core.http_errors import client_error_detail
from web.backend.services.empire_architecture import architecture_summary
from web.backend.services.funding_utility import (
    advance_funding_opportunity,
    build_capital_decision_card,
    create_funding_opportunity,
    create_preapproved_budget,
    deactivate_budget,
    funding_status_summary,
    get_request,
    list_requests,
    owner_decide,
    reconcile_request,
    record_payment,
    record_verification,
    save_decision_card,
    submit_funding_request,
)
from web.backend.services.ultron_oversight import audit_package, consolidate_decision

router = APIRouter(prefix="/api/admin/empire", tags=["admin-empire"])


class FundingRequestBody(BaseModel):
    workspace_id: str = Field(default="default", min_length=1, max_length=128)
    product_id: str | None = Field(default=None, max_length=128)
    department: str = Field(..., min_length=1, max_length=80)
    requested_by: str = Field(..., min_length=1, max_length=128)
    requested_by_label: str | None = Field(default=None, max_length=120)
    amount_usd: float = Field(..., gt=0, le=10_000_000)
    purpose: str = Field(..., min_length=3, max_length=4000)
    source_preference: str | None = Field(default=None, max_length=240)
    restrictions: list[str] = Field(default_factory=list, max_length=20)
    preapproved_budget: bool = False


class FundingVerificationBody(BaseModel):
    verifier_id: str = Field(..., min_length=1, max_length=128)
    passed: bool
    evidence: dict[str, Any] = Field(default_factory=dict)
    note: str = Field(default="", max_length=2000)


class DecisionCardBody(BaseModel):
    roi_low_pct: float | None = None
    roi_high_pct: float | None = None
    break_even_months: float | None = Field(default=None, ge=0)
    maximum_loss_usd: float | None = Field(default=None, ge=0)
    confidence: float | None = Field(default=None, ge=0, le=100)
    risk_score: float | None = Field(default=None, ge=0, le=100)
    market_evidence_summary: str = Field(default="", max_length=4000)
    capital_efficiency_summary: str = Field(default="", max_length=4000)
    independent_audit_summary: str = Field(default="", max_length=4000)
    cheaper_alternatives: list[str] = Field(default_factory=list, max_length=12)
    plain_language_rationale: str = Field(default="", max_length=2000)


class OwnerDecisionBody(BaseModel):
    approved: bool
    note: str = Field(default="", max_length=2000)


class PaymentRecordBody(BaseModel):
    dispatcher_id: str = Field(..., min_length=1, max_length=128)
    payment_ref: str = Field(..., min_length=1, max_length=240)
    source: str = Field(..., min_length=1, max_length=240)
    destination: str = Field(..., min_length=1, max_length=240)
    amount_usd: float | None = Field(default=None, gt=0)


class PreapprovedBudgetBody(BaseModel):
    workspace_id: str = Field(default="default", min_length=1, max_length=128)
    ceiling_usd: float = Field(..., gt=0, le=10_000_000)
    department: str | None = Field(default=None, max_length=80)
    product_id: str | None = Field(default=None, max_length=128)
    note: str = Field(default="", max_length=2000)


class FundingOpportunityBody(BaseModel):
    workspace_id: str = Field(default="default", min_length=1, max_length=128)
    scout_id: str = Field(..., min_length=1, max_length=128)
    opportunity_type: str = Field(..., min_length=1, max_length=80)
    title: str = Field(..., min_length=1, max_length=500)
    source_url: str | None = Field(default=None, max_length=2000)
    amount_estimate_usd: float | None = Field(default=None, ge=0, le=1_000_000_000)
    restrictions: list[str] = Field(default_factory=list, max_length=20)
    evidence: dict[str, Any] = Field(default_factory=dict)


class FundingOpportunityAdvanceBody(BaseModel):
    next_status: str = Field(..., min_length=1, max_length=40)
    evidence_update: dict[str, Any] = Field(default_factory=dict)


class UltronAuditBody(BaseModel):
    workspace_id: str = Field(default="default", min_length=1, max_length=128)
    product_id: str = Field(..., min_length=1, max_length=128)
    department: str = Field(..., min_length=1, max_length=80)
    research_packet: dict[str, Any]
    primary_risk: dict[str, Any] = Field(default_factory=dict)
    manager_review: dict[str, Any] = Field(default_factory=dict)
    funding_request_id: str | None = None


@router.get("/architecture")
async def get_architecture(_admin: dict = Depends(require_admin_with_rbac)):
    return architecture_summary()


@router.get("/funding")
async def get_funding_status(_admin: dict = Depends(require_admin_with_rbac)):
    return funding_status_summary()


@router.post("/funding/budgets")
async def create_funding_budget(
    body: PreapprovedBudgetBody,
    admin: dict = Depends(require_admin_with_rbac),
):
    if normalize_role(admin.get("role")) != AdminRole.SUPER_ADMIN:
        raise HTTPException(status_code=403, detail="Preapproved capital budgets require super_admin")
    owner_id = str(admin.get("sub") or admin.get("username") or admin.get("email") or "owner")
    try:
        return create_preapproved_budget(approved_by=owner_id, **body.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=client_error_detail(exc)) from exc


@router.post("/funding/budgets/{budget_id}/deactivate")
async def stop_funding_budget(
    budget_id: str,
    admin: dict = Depends(require_admin_with_rbac),
):
    if normalize_role(admin.get("role")) != AdminRole.SUPER_ADMIN:
        raise HTTPException(status_code=403, detail="Preapproved capital budgets require super_admin")
    try:
        return deactivate_budget(budget_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=client_error_detail(exc)) from exc


@router.post("/funding/scout/{product_id}")
async def run_funding_scouts(
    product_id: str,
    _admin: dict = Depends(require_admin_with_rbac),
):
    from core.paths import pipeline_db_path, workspace_id
    from orchestrator.sqlite_manager import SQLiteManager
    from web.backend.services.funding_scouts import discover_funding_opportunities

    ws = workspace_id()
    sm = SQLiteManager(str(pipeline_db_path()), workspace_id=ws)
    sm.connect()
    try:
        product = sm.get_product(product_id)
    finally:
        sm.close()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return await asyncio.to_thread(
        discover_funding_opportunities,
        workspace_id=ws,
        project_idea=str(product.get("idea") or ""),
        product_id=product_id,
    )


@router.post("/funding/opportunities")
async def add_funding_opportunity(
    body: FundingOpportunityBody,
    _admin: dict = Depends(require_admin_with_rbac),
):
    try:
        return create_funding_opportunity(**body.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=client_error_detail(exc)) from exc


@router.post("/funding/opportunities/{opportunity_id}/advance")
async def move_funding_opportunity(
    opportunity_id: str,
    body: FundingOpportunityAdvanceBody,
    _admin: dict = Depends(require_admin_with_rbac),
):
    try:
        return advance_funding_opportunity(opportunity_id, **body.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=client_error_detail(exc)) from exc


@router.post("/funding/requests")
async def create_funding_request(body: FundingRequestBody, _admin: dict = Depends(require_admin_with_rbac)):
    try:
        request = submit_funding_request(**body.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=client_error_detail(exc)) from exc
    return request


@router.post("/funding/requests/{request_id}/verify")
async def verify_funding_request(
    request_id: str,
    body: FundingVerificationBody,
    _admin: dict = Depends(require_admin_with_rbac),
):
    try:
        request = record_verification(request_id, **body.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=client_error_detail(exc)) from exc
    return request


@router.post("/funding/requests/{request_id}/decision-card")
async def put_decision_card(
    request_id: str,
    body: DecisionCardBody,
    _admin: dict = Depends(require_admin_with_rbac),
):
    request = get_request(request_id)
    if not request:
        raise HTTPException(status_code=404, detail="Funding request not found")
    card = build_capital_decision_card(request, **body.model_dump())
    try:
        return save_decision_card(request_id, card)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=client_error_detail(exc)) from exc


@router.post("/funding/requests/{request_id}/owner-decision")
async def decide_funding_request(
    request_id: str,
    body: OwnerDecisionBody,
    admin: dict = Depends(require_admin_with_rbac),
):
    if normalize_role(admin.get("role")) != AdminRole.SUPER_ADMIN:
        raise HTTPException(status_code=403, detail="Owner funding decisions require super_admin")
    owner_id = str(admin.get("sub") or admin.get("username") or admin.get("email") or "owner")
    try:
        result = owner_decide(request_id, approved=body.approved, owner_id=owner_id, note=body.note)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=client_error_detail(exc)) from exc
    return result


@router.post("/funding/requests/{request_id}/record-payment")
async def record_funding_payment(
    request_id: str,
    body: PaymentRecordBody,
    admin: dict = Depends(require_admin_with_rbac),
):
    if normalize_role(admin.get("role")) != AdminRole.SUPER_ADMIN:
        raise HTTPException(status_code=403, detail="Recording capital movement requires super_admin")
    try:
        return record_payment(request_id, **body.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=client_error_detail(exc)) from exc


@router.post("/funding/requests/{request_id}/reconcile")
async def reconcile_funding_request(
    request_id: str,
    _admin: dict = Depends(require_admin_with_rbac),
):
    try:
        return reconcile_request(request_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=client_error_detail(exc)) from exc


@router.get("/reports/{product_id}.pdf")
async def empire_product_report_pdf(
    product_id: str,
    _admin: dict = Depends(require_admin_with_rbac),
):
    from core.paths import pipeline_db_path, workspace_id
    from orchestrator.sqlite_manager import SQLiteManager
    from web.backend.services.empire_reports import build_empire_report, render_empire_report_pdf

    sm = SQLiteManager(str(pipeline_db_path()), workspace_id=workspace_id())
    sm.connect()
    try:
        product = sm.get_product(product_id)
    finally:
        sm.close()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    funding = [r for r in list_requests(workspace_id=workspace_id(), limit=500) if r.get("product_id") == product_id]
    report = build_empire_report(product, funding_requests=funding)
    pdf = render_empire_report_pdf(report)
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="empire-{product_id}.pdf"'},
    )


@router.post("/ultron/audit")
async def run_ultron_audit(body: UltronAuditBody, _admin: dict = Depends(require_admin_with_rbac)):
    funding = get_request(body.funding_request_id) if body.funding_request_id else None
    audit = audit_package(
        workspace_id=body.workspace_id,
        product_id=body.product_id,
        department=body.department,
        research_packet=body.research_packet,
        manager_review=body.manager_review,
        funding_request=funding,
    )
    consolidated = consolidate_decision(
        research_packet=body.research_packet,
        primary_risk=body.primary_risk,
        manager_review=body.manager_review,
        ultron_audit=audit,
        funding_review=funding,
    )
    return {"audit": audit, "consolidated": consolidated}
