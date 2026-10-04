from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import os
import time
import uuid
from collections import defaultdict, deque
from pathlib import Path
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from fastapi.responses import FileResponse

from core.pipeline_state_writer import append_product_to_pipeline_state
from web.backend.schemas.api_requests import (
    CustomerCreateRunRequest,
    CustomerFactoryMissionRequest,
    CustomerFundingRequest,
    CustomerPersonnelRequest,
    CustomerManagerDelegationRequest,
    CustomerOwnerDecisionRequest,
    CustomerProjectControlRequest,
    CustomerPersonnelControlRequest,
    CustomerOnboardingRequest,
    CustomerLoginRequest,
    CustomerRegisterRequest,
    DemoNoteCreateRequest,
    DemoNotePatchRequest,
    StripeCheckoutRequest,
)
from web.backend.services.commerce import CommerceService
from web.backend.middleware.csrf import CSRF_COOKIE, new_csrf_token
from web.backend.core.http_errors import client_error_detail

router = APIRouter(prefix="/api/customer", tags=["customer"])
commerce = CommerceService()
logger = logging.getLogger(__name__)

_REG_MAX_PER_HOUR = int(os.environ.get("AIFACTORY_CUSTOMER_REGISTER_MAX_PER_HOUR", "5"))
_REG_WINDOW_SEC = 3600.0
_register_attempts: dict[str, deque[float]] = defaultdict(deque)
_LOGIN_MAX_PER_15_MIN = int(os.environ.get("AIFACTORY_CUSTOMER_LOGIN_MAX_PER_15_MIN", "15"))


def _client_ip(request: Request) -> str:
    # Canonical resolver: the RIGHTMOST non-trusted X-Forwarded-For entry.
    # The inline parser this replaces trusted the LEFTMOST value, which the client
    # controls -- nginx `proxy_add_x_forwarded_for` APPENDS what it saw, so a caller
    # that sends its own X-Forwarded-For lands leftmost and can rotate a spoofed IP
    # past this per-IP limit. See web/backend/http/client_ip.py.
    from web.backend.http.client_ip import client_ip as _resolve

    return _resolve(request)


def _enforce_register_rate_limit(ip: str) -> None:
    now = time.time()
    window = _register_attempts[ip]
    while window and now - window[0] > _REG_WINDOW_SEC:
        window.popleft()
    if len(window) >= _REG_MAX_PER_HOUR:
        raise HTTPException(status_code=429, detail="Too many registration attempts. Try again later.")
    window.append(now)


def _enforce_factory_write_limit(customer_id: str, bucket: str, *, max_hits: int = 60, window_seconds: float = 3600.0) -> None:
    from web.backend.services.shared_rate_limit import enforce_shared_rate_limit
    enforce_shared_rate_limit(
        f"customer-factory:{customer_id}:{bucket}", max_hits=max_hits, window_seconds=window_seconds,
        detail="Too many Factory actions. Try again shortly.",
    )


CUSTOMER_SESSION_COOKIE = "customer_token"


def _customer_cookie_secure(request: Request) -> bool:
    if (os.environ.get("AIFACTORY_PROD") or "").strip() == "1":
        return True
    forwarded = (request.headers.get("x-forwarded-proto") or "").split(",", 1)[0].strip().lower()
    return request.url.scheme == "https" or forwarded == "https"


def _browser_session_request(request: Request) -> bool:
    return bool(request.headers.get("origin") or request.headers.get("referer"))


def _enforce_login_rate_limit(request: Request) -> None:
    from web.backend.services.shared_rate_limit import enforce_shared_rate_limit
    enforce_shared_rate_limit(
        f"customer-login:{_client_ip(request)}",
        max_hits=_LOGIN_MAX_PER_15_MIN,
        window_seconds=900.0,
        detail="Too many login attempts. Try again later.",
    )


def _enforce_bot_honeypot(value: str) -> None:
    """Reject automated form fillers that populate the invisible website field."""
    if (value or "").strip():
        raise HTTPException(status_code=400, detail="Invalid authentication request")


def _set_customer_session(request: Request, response: Response, token: str) -> None:
    # Browser fetches carry Origin/Referer; command-line/API clients normally do not.
    # Keep bearer-only clients stateless while moving browser sessions into HttpOnly cookies.
    if not _browser_session_request(request):
        return
    secure = _customer_cookie_secure(request)
    max_age = int(getattr(commerce, "jwt_expiry_seconds", 0) or 86400)
    response.set_cookie(
        key=CUSTOMER_SESSION_COOKIE, value=token, httponly=True, secure=secure,
        samesite="strict", max_age=max_age, path="/",
    )
    response.set_cookie(
        key=CSRF_COOKIE, value=new_csrf_token(), httponly=False, secure=secure,
        samesite="strict", max_age=max_age, path="/",
    )


def _clear_customer_session(request: Request, response: Response) -> None:
    secure = _customer_cookie_secure(request)
    response.delete_cookie(CUSTOMER_SESSION_COOKIE, path="/", httponly=True, secure=secure, samesite="strict")
    response.delete_cookie(CSRF_COOKIE, path="/", secure=secure, samesite="strict")


def _get_token_payload(request: Request, authorization: Optional[str] = Header(default=None)) -> dict:
    token = ""
    if authorization and authorization.startswith("Bearer "):
        token = authorization.split(" ", 1)[1].strip()
    if not token:
        token = (request.cookies.get(CUSTOMER_SESSION_COOKIE) or "").strip()
    if not token:
        raise HTTPException(status_code=401, detail="Missing customer session")
    payload = commerce.decode_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired customer token")
    return payload


def _stripe_price_catalog() -> dict[str, int]:
    return {
        "maker": int(os.environ.get("AIFACTORY_STRIPE_MAKER_PRICE_CENTS", "1900")),
        "studio": int(os.environ.get("AIFACTORY_STRIPE_STUDIO_PRICE_CENTS", "9900")),
        "enterprise": int(os.environ.get("AIFACTORY_STRIPE_ENTERPRISE_PRICE_CENTS", "49900")),
    }


def _verify_stripe_signature(payload: bytes, sig_header: str, secret: str) -> bool:
    if not sig_header or not secret:
        return False
    parts: dict[str, str] = {}
    for piece in sig_header.split(","):
        if "=" not in piece:
            continue
        k, v = piece.split("=", 1)
        parts[k.strip()] = v.strip()
    ts = parts.get("t")
    sig = parts.get("v1")
    if not ts or not sig:
        return False
    try:
        ts_int = int(ts)
    except ValueError:
        return False
    if abs(time.time() - ts_int) > 300:
        return False
    signed_payload = f"{ts}.{payload.decode('utf-8')}".encode("utf-8")
    expected = hmac.new(secret.encode("utf-8"), signed_payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, sig)


def _auth_response(request: Request, customer: dict, token: str) -> dict:
    if _browser_session_request(request):
        # The browser gets only the HttpOnly session cookie. Do not duplicate the JWT
        # into a JavaScript-readable response body.
        return {"customer": customer, "token_type": "cookie"}
    return {"customer": customer, "access_token": token, "token_type": "bearer"}


@router.post("/register")
async def register(body: CustomerRegisterRequest, request: Request, response: Response):
    _enforce_bot_honeypot(body.website)
    _enforce_register_rate_limit(_client_ip(request))
    try:
        customer = commerce.register_customer(body.email, body.password)
    except ValueError as exc:
        raise HTTPException(
            status_code=409,
            detail=client_error_detail(exc, fallback="Unable to register customer"),
        ) from exc
    token = commerce.create_token(customer["id"], customer["email"])
    _set_customer_session(request, response, token)
    return _auth_response(request, customer, token)


@router.post("/login")
async def login(body: CustomerLoginRequest, request: Request, response: Response):
    _enforce_bot_honeypot(body.website)
    _enforce_login_rate_limit(request)
    customer = commerce.authenticate_customer(body.email, body.password)
    if not customer:
        raise HTTPException(status_code=401, detail="Invalid email or password")
    token = commerce.create_token(customer["id"], customer["email"])
    _set_customer_session(request, response, token)
    return _auth_response(request, customer, token)


@router.get("/me")
async def me(payload: dict = Depends(_get_token_payload)):
    from web.backend.services.tenant_workspaces import customer_workspace_id
    profile = commerce.get_customer(payload["sub"]) or {}
    usage = commerce.get_monthly_run_usage(payload["sub"])
    return {
        "id": payload["sub"],
        "email": payload.get("email"),
        "plan": profile.get("plan", "free"),
        "workspace_id": customer_workspace_id(payload["sub"]),
        "usage": usage,
    }


@router.post("/logout")
async def customer_logout(request: Request, response: Response):
    """Clear the browser customer session; bearer clients may discard their token."""
    _clear_customer_session(request, response)
    return {"ok": True}


@router.post("/demo-notes")
async def demo_notes_create(body: DemoNoteCreateRequest, payload: dict = Depends(_get_token_payload)):
    try:
        note = commerce.create_demo_note(payload["sub"], body.title, body.body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=client_error_detail(exc)) from exc
    return {"note": note}


@router.get("/demo-notes")
async def demo_notes_list(payload: dict = Depends(_get_token_payload)):
    notes = commerce.list_demo_notes(payload["sub"])
    return {"notes": notes, "count": len(notes)}


@router.patch("/demo-notes/{note_id}")
async def demo_notes_patch(
    note_id: str,
    body: DemoNotePatchRequest,
    payload: dict = Depends(_get_token_payload),
):
    try:
        updated = commerce.update_demo_note(
            payload["sub"],
            note_id.strip(),
            body.title,
            body.body,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=client_error_detail(exc)) from exc
    if not updated:
        raise HTTPException(status_code=404, detail="Note not found")
    return {"note": updated}


@router.delete("/demo-notes/{note_id}")
async def demo_notes_delete(note_id: str, payload: dict = Depends(_get_token_payload)):
    ok = commerce.delete_demo_note(payload["sub"], note_id.strip())
    if not ok:
        raise HTTPException(status_code=404, detail="Note not found")
    return {"ok": True, "id": note_id}


@router.post("/billing/stripe/checkout")
async def create_stripe_checkout_session(body: StripeCheckoutRequest, payload: dict = Depends(_get_token_payload)):
    secret_key = os.environ.get("STRIPE_SECRET_KEY", "").strip()
    if not secret_key:
        raise HTTPException(status_code=503, detail="Stripe is not configured")

    target_plan = body.target_plan
    prices = _stripe_price_catalog()
    amount = prices.get(target_plan, prices["maker"])
    if amount <= 0:
        raise HTTPException(status_code=500, detail="Stripe price catalog misconfigured")

    customer = commerce.get_customer(payload["sub"])
    if not customer:
        raise HTTPException(status_code=401, detail="Customer not found")

    idem = f"cust:{payload['sub']}:plan:{target_plan}:{int(time.time() // 30)}"
    req_body = {
        "mode": "payment",
        "success_url": body.success_url,
        "cancel_url": body.cancel_url,
        "client_reference_id": payload["sub"],
        "customer_email": customer.get("email") or payload.get("email"),
        "metadata[customer_id]": payload["sub"],
        "metadata[target_plan]": target_plan,
        "metadata[source]": "aifactory_checkout",
        "line_items[0][price_data][currency]": "usd",
        "line_items[0][price_data][product_data][name]": f"AI-Factory {target_plan.title()} plan",
        "line_items[0][price_data][unit_amount]": str(amount),
        "line_items[0][quantity]": "1",
    }
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                "https://api.stripe.com/v1/checkout/sessions",
                data=req_body,
                headers={
                    "Authorization": f"Bearer {secret_key}",
                    "Idempotency-Key": idem,
                },
            )
        if resp.status_code >= 400:
            logger.warning("Stripe checkout upstream rejected request (status=%s)", resp.status_code)
            raise HTTPException(status_code=502, detail="Stripe checkout is temporarily unavailable")
        data = resp.json()
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Stripe checkout request failed")
        raise HTTPException(status_code=502, detail="Stripe checkout is temporarily unavailable") from exc

    session_id = str(data.get("id") or "")
    if not session_id:
        raise HTTPException(status_code=502, detail="Stripe session id missing")
    commerce.save_stripe_checkout_session(
        session_id=session_id,
        customer_id=payload["sub"],
        customer_email=customer.get("email") or payload.get("email") or "",
        target_plan=target_plan,
        amount_total=int(data.get("amount_total") or amount),
        currency=str(data.get("currency") or "usd"),
        status=str(data.get("status") or "open"),
        payment_status=str(data.get("payment_status") or "unpaid"),
        idempotency_key=idem,
    )
    return {
        "session_id": session_id,
        "checkout_url": data.get("url"),
        "amount_total": int(data.get("amount_total") or amount),
        "currency": str(data.get("currency") or "usd"),
        "target_plan": target_plan,
    }


@router.post("/billing/stripe/webhook")
async def stripe_webhook(request: Request):
    secret = os.environ.get("STRIPE_WEBHOOK_SECRET", "").strip()
    if not secret:
        raise HTTPException(status_code=503, detail="Stripe webhook secret is not configured")
    payload = await request.body()
    signature = request.headers.get("Stripe-Signature", "")
    if not _verify_stripe_signature(payload, signature, secret):
        raise HTTPException(status_code=400, detail="Invalid Stripe signature")
    try:
        event = json.loads(payload.decode("utf-8"))
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid webhook payload")

    event_type = str(event.get("type") or "")
    event_id = str(event.get("id") or "")
    obj = ((event.get("data") or {}).get("object") or {})
    session_id = str(obj.get("id") or "")
    payment_status = str(obj.get("payment_status") or "")
    session_status = str(obj.get("status") or "")
    customer_email = obj.get("customer_email")
    metadata = obj.get("metadata") if isinstance(obj.get("metadata"), dict) else {}
    if not event_id or not session_id:
        raise HTTPException(status_code=400, detail="Webhook payload missing event/session ids")

    result = commerce.apply_stripe_webhook_event(
        event_id=event_id,
        event_type=event_type,
        session_id=session_id,
        payment_status=payment_status,
        session_status=session_status,
        customer_email=customer_email,
        metadata=metadata,
    )
    return {"ok": True, "event_type": event_type, **result}


@router.get("/orders")
async def list_orders(payload: dict = Depends(_get_token_payload)):
    orders = commerce.get_orders_for_customer(payload["sub"])
    return {"orders": orders, "count": len(orders)}


@router.get("/referrals/me")
async def my_referral_dashboard(payload: dict = Depends(_get_token_payload)):
    customer = commerce.get_customer(payload["sub"])
    if not customer:
        raise HTTPException(status_code=401, detail="Customer not found")
    return commerce.get_referral_stats(
        customer_id=payload["sub"],
        customer_email=customer.get("email") or payload.get("email") or "",
    )



@router.get("/factory")
async def customer_factory(payload: dict = Depends(_get_token_payload)):
    """Return this customer's isolated, game-facing Factory state."""
    from web.backend.services.empire_architecture import architecture_summary
    from web.backend.services.funding_utility import funding_status_summary, list_requests
    from web.backend.services.tenant_workspaces import (
        customer_workspace_id,
        read_customer_pipeline_state,
    )

    customer_id = str(payload["sub"])
    ws = customer_workspace_id(customer_id)
    state = read_customer_pipeline_state(customer_id)
    products = list((state.get("products") or {}).values())
    tasks = list(state.get("task_queue") or [])
    funding_requests = list_requests(workspace_id=ws, limit=500)
    from web.backend.services.provider_health import local_ollama_health
    from web.backend.services.customer_factory_establishment import (
        limits_for, maybe_daily_snapshot, read_audit, snapshot_status, stall_for, usage_summary, audit_provider_transition, MISSION_TEMPLATES,
    )
    provider_health = local_ollama_health()
    audit_provider_transition(customer_id, provider_health)
    from web.backend.services.production_readiness import customer_readiness_summary
    system_health = customer_readiness_summary(customer_id)
    profile = commerce.get_customer(customer_id) or {}
    plan = str(profile.get("plan") or "free").lower()
    try:
        maybe_daily_snapshot(customer_id)
    except Exception:
        logger.exception("Tenant daily snapshot failed for %s", ws)
    active_by_product: dict[str, list[dict]] = {}
    for task in tasks:
        pid = str(task.get("product_id") or "")
        if not pid:
            continue
        if str(task.get("status") or "").lower() in {"pending", "running", "blocked"}:
            active_by_product.setdefault(pid, []).append(task)

    project_nodes = []
    for product in products:
        pid = str(product.get("id") or "")
        live = active_by_product.get(pid) or []
        product_tasks = [t for t in tasks if str(t.get("product_id") or "") == pid]
        timeline: list[dict] = []
        for task in product_tasks:
            status = str(task.get("status") or "pending").lower()
            inp = task.get("input_data") or {}
            out = task.get("output_data") or {}
            assignment = out.get("factory_assignment_result") if isinstance(out, dict) else {}
            evidence = (assignment or {}).get("evidence_sources") if isinstance(assignment, dict) else []
            timeline.append({
                "id": f"task:{task.get('id')}",
                "kind": "task",
                "timestamp": task.get("completed_at") or task.get("updated_at") or task.get("started_at") or task.get("created_at") or 0,
                "status": status,
                "actor": task.get("assigned_to") or task.get("agent_type") or "AI",
                "agent_type": task.get("agent_type"),
                "label": inp.get("assignment_directive") or inp.get("directive") or inp.get("empire_research_lens") or task.get("agent_type") or "Task",
                "evidence_count": len(evidence or []),
                "retry_count": int(task.get("retry_count") or 0),
                "error": task.get("error"),
                "retryable": status in {"failed", "blocked"},
                "task_id": task.get("id"),
            })
        manager_review = product.get("empire_manager_review") or {}
        if manager_review:
            timeline.append({
                "id": "manager-review", "kind": "manager_review",
                "timestamp": manager_review.get("reviewed_at") or 0,
                "status": "completed", "actor": manager_review.get("manager_id") or "Department Manager",
                "label": "Manager evidence review",
            })
        ultron_audit = product.get("ultron_audit") or {}
        if ultron_audit:
            timeline.append({
                "id": "ultron-audit", "kind": "ultron_review",
                "timestamp": ultron_audit.get("audited_at") or 0,
                "status": "completed", "actor": "Ultron",
                "label": f"Ultron: {str(ultron_audit.get('recommendation') or 'review').replace('_', ' ')}",
                "evidence_count": ((ultron_audit.get("secondary_risk") or {}).get("evidence_items") or 0),
            })
        for idx, decision in enumerate(product.get("owner_decision_history") or []):
            timeline.append({
                "id": f"owner:{idx}", "kind": "owner_decision",
                "timestamp": decision.get("decided_at") or 0,
                "status": decision.get("action") or "recorded", "actor": "Factory Owner",
                "label": decision.get("note") or str(decision.get("action") or "Owner decision").replace("_", " "),
            })
        timeline.sort(key=lambda event: float(event.get("timestamp") or 0))
        project_funding = [req for req in funding_requests if str(req.get("product_id") or "") == pid]
        status_counts: dict[str, int] = {}
        for task in product_tasks:
            key = str(task.get("status") or "pending").lower()
            status_counts[key] = status_counts.get(key, 0) + 1
        project_nodes.append(
            {
                "id": f"product:{pid}",
                "kind": "product",
                "product_id": pid,
                "label": str(product.get("idea") or pid)[:120],
                "state": product.get("state"),
                "department": product.get("empire_department") or product.get("category") or "general",
                "active_task_count": len(live),
                "active_tasks": [
                    {
                        "id": t.get("id"),
                        "agent_type": t.get("agent_type"),
                        "assigned_to": t.get("assigned_to"),
                        "status": t.get("status"),
                    }
                    for t in live[:20]
                ],
                "decision_ready": bool(product.get("empire_decision_package")),
                "manager_review": product.get("empire_manager_review"),
                "primary_risk": product.get("empire_primary_risk"),
                "ultron_audit": product.get("ultron_audit"),
                "decision_package": product.get("empire_decision_package"),
                "owner_decision": product.get("owner_decision"),
                "funding_requests": project_funding[:20],
                "task_summary": status_counts,
                "timeline": timeline[-limits_for(plan)["history"]:],
                "stall": stall_for(product, product_tasks),
                "paused": bool(product.get("factory_paused")),
                "archived": bool(product.get("archived")),
            }
        )

    from web.backend.services.customer_workforce import list_customer_personnel
    workforce = list_customer_personnel(customer_id)
    usage = usage_summary(customer_id, plan, workforce)
    from web.backend.services.customer_factory_canary import read_customer_factory_canary
    qa_canary = read_customer_factory_canary()
    return {
        "workspace_id": ws,
        "tenant_isolated": True,
        "organization": architecture_summary(),
        "projects": project_nodes,
        "task_count": len(tasks),
        "workforce": workforce,
        "funding": funding_status_summary(workspace_id=ws),
        "provider_health": provider_health,
        "system_health": system_health,
        "plan": plan,
        "usage": usage,
        "mission_templates": MISSION_TEMPLATES,
        "audit_log": read_audit(customer_id, limit=100),
        "backup": snapshot_status(customer_id),
        "qa_canary": qa_canary,
        "model_failover": {"router_enabled": True, "primary": "local_ollama", "degraded_mode": not bool(provider_health.get("online")), "note": "Router failover is used when another configured authenticated provider is available; otherwise tasks remain recoverable instead of gaining unsafe authority."},
        "customer_permissions": {
            "may_create_projects": True,
            "may_create_ai_personnel": True,
            "may_delegate_tasks": True,
            "may_request_funding": True,
            "may_authorize_funding": False,
            "may_move_money": False,
        },
    }


@router.get("/factory/reports/{product_id}.pdf")
async def customer_factory_report_pdf(
    product_id: str,
    payload: dict = Depends(_get_token_payload),
):
    from web.backend.services.empire_reports import build_empire_report, render_empire_report_pdf
    from web.backend.services.funding_utility import list_requests
    from web.backend.services.tenant_workspaces import customer_workspace_id, read_customer_pipeline_state

    customer_id = str(payload["sub"])
    state = read_customer_pipeline_state(customer_id)
    product = (state.get("products") or {}).get(product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Project not found")
    ws = customer_workspace_id(customer_id)
    funding = [r for r in list_requests(workspace_id=ws, limit=500) if r.get("product_id") == product_id]
    report = build_empire_report(product, funding_requests=funding)
    return Response(
        content=render_empire_report_pdf(report),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="empire-{product_id}.pdf"'},
    )


@router.post("/factory/personnel")
async def customer_create_personnel(
    body: CustomerPersonnelRequest,
    payload: dict = Depends(_get_token_payload),
):
    from web.backend.services.customer_workforce import create_customer_personnel, list_customer_personnel
    from web.backend.services.customer_factory_establishment import enforce_capacity, emit_audit
    customer_id = str(payload["sub"]); _enforce_factory_write_limit(customer_id, "personnel", max_hits=30)
    plan = str((commerce.get_customer(customer_id) or {}).get("plan") or "free").lower()
    workforce = list_customer_personnel(customer_id)
    try:
        enforce_capacity(customer_id, plan, "personnel", workforce)
        if body.role_class == "manager":
            enforce_capacity(customer_id, plan, "manager", workforce)
        row = create_customer_personnel(
            str(payload["sub"]),
            body.description,
            role_class=body.role_class,
            label=body.label,
        )
        emit_audit(customer_id, "personnel_created", detail={"personnel_id": row.get("id"), "role_class": row.get("role_class")})
        return row
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=client_error_detail(exc)) from exc


@router.post("/factory/managers/{manager_id}/delegate")
async def customer_manager_delegate(
    manager_id: str,
    body: CustomerManagerDelegationRequest,
    payload: dict = Depends(_get_token_payload),
):
    from web.backend.services.customer_workforce import delegate_customer_manager_task, list_customer_personnel
    from web.backend.services.customer_factory_establishment import emit_audit, enforce_capacity
    customer_id = str(payload["sub"]); _enforce_factory_write_limit(customer_id, "delegate", max_hits=120)
    plan=str((commerce.get_customer(customer_id) or {}).get("plan") or "free").lower()
    try:
        enforce_capacity(customer_id,plan,"active_task",list_customer_personnel(customer_id))
        result = delegate_customer_manager_task(
            customer_id,
            manager_id=manager_id,
            worker_id=body.worker_id,
            product_id=body.product_id,
            directive=body.directive,
        )
        emit_audit(customer_id, "manager_delegation", actor=manager_id, product_id=body.product_id, task_id=result.get("task_id"), detail={"worker_id": body.worker_id})
        return result
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=client_error_detail(exc)) from exc


@router.post("/factory/tasks/{task_id}/retry")
async def customer_factory_retry_task(
    task_id: str,
    payload: dict = Depends(_get_token_payload),
):
    from web.backend.services.customer_task_recovery import retry_customer_task
    from web.backend.services.customer_factory_establishment import emit_audit, limits_for
    customer_id=str(payload["sub"]); plan=str((commerce.get_customer(customer_id) or {}).get("plan") or "free").lower()
    _enforce_factory_write_limit(customer_id, "retry", max_hits=limits_for(plan)["retries_per_hour"], window_seconds=3600)
    try:
        result=retry_customer_task(customer_id, task_id)
        emit_audit(customer_id, "task_retry", task_id=result.get("task_id"), detail={"retry_of": task_id, "deduplicated": result.get("deduplicated")})
        return result
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=client_error_detail(exc)) from exc


@router.post("/factory/projects/{product_id}/owner-decision")
async def customer_factory_owner_decision(
    product_id: str,
    body: CustomerOwnerDecisionRequest,
    payload: dict = Depends(_get_token_payload),
):
    """Record a non-financial owner decision for a mission package."""
    from web.backend.services.tenant_workspaces import read_customer_pipeline_state, write_customer_product

    customer_id = str(payload["sub"]); _enforce_factory_write_limit(str(payload["sub"]), "owner-decision", max_hits=60)
    state = read_customer_pipeline_state(customer_id)
    product = (state.get("products") or {}).get(product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Project not found")
    if body.action == "accept_package" and not product.get("empire_decision_package"):
        raise HTTPException(status_code=409, detail="Decision package is not ready")
    decision = {
        "action": body.action,
        "note": (body.note or "").strip() or None,
        "decided_at": time.time(),
        "financial_authority": False,
    }
    history = list(product.get("owner_decision_history") or [])
    history.append(decision)
    product["owner_decision"] = decision
    product["owner_decision_history"] = history[-100:]
    if body.action == "archive":
        product["archived"] = True
    write_customer_product(customer_id, product)
    from web.backend.services.customer_factory_establishment import emit_audit
    emit_audit(customer_id, "owner_decision", product_id=product_id, detail={"action": body.action})
    return {"decision": decision, "financial_authority": False, "may_move_money": False}


@router.post("/factory/mission")
async def customer_factory_mission(
    body: CustomerFactoryMissionRequest,
    payload: dict = Depends(_get_token_payload),
):
    """Turn a customer prompt into a five-lens department mission + management reviews."""
    from web.backend.services.empire_missions import create_customer_mission
    from web.backend.services.customer_factory_establishment import enforce_mission_capacity, emit_audit
    from web.backend.services.prompt_safety import (
        prepare_untrusted_plain_text,
        rejection_reason_if_blocked,
    )

    customer_id = str(payload["sub"])
    _enforce_factory_write_limit(customer_id, "mission", max_hits=20)
    profile = commerce.get_customer(customer_id)
    if not profile:
        raise HTTPException(status_code=401, detail="Customer not found")
    plan = str(profile.get("plan") or "free").lower()
    try:
        enforce_mission_capacity(customer_id, plan)
    except ValueError as exc:
        raise HTTPException(status_code=402, detail=str(exc)) from exc
    if plan == "free":
        quota = commerce.consume_monthly_run(customer_id, limit=3)
        if not quota.get("allowed"):
            raise HTTPException(
                status_code=402,
                detail="Free tier limit reached (3 pipeline runs/month). Upgrade required.",
            )

    raw = (body.prompt or "").strip()
    blocked = rejection_reason_if_blocked(raw, context="customer_empire_mission")
    if blocked:
        raise HTTPException(status_code=400, detail=blocked)
    prompt = prepare_untrusted_plain_text(raw, max_len=8000)
    try:
        result = create_customer_mission(customer_id, prompt)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=client_error_detail(exc)) from exc
    emit_audit(customer_id, "mission_created", product_id=result.get("product_id"), detail={"department": result.get("department")})
    return {**result, "plan": plan, "tenant_isolated": True}


@router.post("/factory/funding/scout/{product_id}")
async def customer_factory_funding_scout(
    product_id: str,
    payload: dict = Depends(_get_token_payload),
):
    from web.backend.services.funding_scouts import discover_funding_opportunities
    from web.backend.services.tenant_workspaces import customer_workspace_id, read_customer_pipeline_state

    customer_id = str(payload["sub"]); _enforce_factory_write_limit(str(payload["sub"]), "funding-scout", max_hits=12)
    state = read_customer_pipeline_state(customer_id)
    product = (state.get("products") or {}).get(product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Project not found")
    result = await asyncio.to_thread(
        discover_funding_opportunities,
        workspace_id=customer_workspace_id(customer_id),
        project_idea=str(product.get("idea") or ""),
        product_id=product_id,
    )
    from web.backend.services.customer_factory_establishment import emit_audit
    emit_audit(customer_id, "funding_scout", product_id=product_id, detail={"opportunities_found": result.get("opportunities_found", 0) if isinstance(result, dict) else 0})
    return result


@router.post("/factory/funding/request")
async def customer_factory_funding_request(
    body: CustomerFundingRequest,
    payload: dict = Depends(_get_token_payload),
):
    """Factory-side funding request only. Customers/AI do not authorize capital here."""
    from web.backend.services.funding_utility import submit_funding_request
    from web.backend.services.tenant_workspaces import customer_workspace_id

    customer_id = str(payload["sub"]); _enforce_factory_write_limit(str(payload["sub"]), "funding-request", max_hits=30)
    ws = customer_workspace_id(customer_id)
    try:
        request = submit_funding_request(
            workspace_id=ws,
            product_id=body.product_id,
            department=body.department,
            requested_by=f"customer-factory:{customer_id}",
            requested_by_label="Customer Factory",
            amount_usd=body.amount_usd,
            purpose=body.purpose,
            source_preference=body.source_preference,
            restrictions=body.restrictions,
            # A client cannot self-declare a preapproved budget. That flag is
            # reserved for Funding Utility/owner-side policy.
            preapproved_budget=False,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=client_error_detail(exc)) from exc
    from web.backend.services.customer_factory_establishment import emit_audit
    emit_audit(customer_id, "funding_request", product_id=body.product_id, detail={"request_id": request.get("id") if isinstance(request, dict) else None, "amount_usd": body.amount_usd, "customer_may_authorize": False})
    return {
        "request": request,
        "authorization": "pending_funding_utility",
        "customer_may_authorize": False,
    }


@router.get("/factory/templates")
async def customer_factory_templates(payload: dict = Depends(_get_token_payload)):
    from web.backend.services.customer_factory_establishment import MISSION_TEMPLATES
    return {"templates": MISSION_TEMPLATES}


@router.post("/factory/onboarding")
async def customer_factory_onboarding(body: CustomerOnboardingRequest, payload: dict = Depends(_get_token_payload)):
    from web.backend.services.customer_factory_establishment import onboarding
    customer_id=str(payload["sub"]); _enforce_factory_write_limit(customer_id,"onboarding",max_hits=5)
    plan=str((commerce.get_customer(customer_id) or {}).get("plan") or "free").lower()
    if plan == "free":
        quota=commerce.consume_monthly_run(customer_id,limit=3)
        if not quota.get("allowed"): raise HTTPException(status_code=402,detail="Free tier limit reached (3 pipeline runs/month). Upgrade required.")
    try: return onboarding(customer_id, body.goal, plan)
    except ValueError as exc: raise HTTPException(status_code=400, detail=client_error_detail(exc)) from exc


@router.post("/factory/projects/{product_id}/control")
async def customer_factory_project_control(product_id: str, body: CustomerProjectControlRequest, payload: dict = Depends(_get_token_payload)):
    from web.backend.services.customer_factory_establishment import project_control
    customer_id=str(payload["sub"]); _enforce_factory_write_limit(customer_id,"control",max_hits=60)
    try: return project_control(customer_id, product_id, body.action)
    except ValueError as exc: raise HTTPException(status_code=400, detail=client_error_detail(exc)) from exc


@router.post("/factory/projects/{product_id}/auto-delegate")
async def customer_factory_auto_delegate(product_id: str, payload: dict = Depends(_get_token_payload)):
    from web.backend.services.customer_factory_establishment import auto_delegate
    customer_id=str(payload["sub"]); _enforce_factory_write_limit(customer_id,"auto-delegate",max_hits=30)
    try: return auto_delegate(customer_id, product_id)
    except ValueError as exc: raise HTTPException(status_code=400, detail=client_error_detail(exc)) from exc


@router.post("/factory/projects/{product_id}/retry-failed")
async def customer_factory_retry_failed(product_id: str, payload: dict = Depends(_get_token_payload)):
    from web.backend.services.customer_factory_establishment import retry_failed_for_project, limits_for
    customer_id=str(payload["sub"]); plan=str((commerce.get_customer(customer_id) or {}).get("plan") or "free").lower()
    _enforce_factory_write_limit(customer_id,"retry",max_hits=limits_for(plan)["retries_per_hour"],window_seconds=3600)
    try: return retry_failed_for_project(customer_id,product_id)
    except ValueError as exc: raise HTTPException(status_code=400,detail=client_error_detail(exc)) from exc


@router.post("/factory/personnel/{agent_id}/control")
async def customer_factory_personnel_control(agent_id: str, body: CustomerPersonnelControlRequest, payload: dict = Depends(_get_token_payload)):
    from web.backend.services.customer_workforce import set_customer_personnel_enabled
    from web.backend.services.customer_factory_establishment import emit_audit
    customer_id=str(payload["sub"]); _enforce_factory_write_limit(customer_id,"personnel-control",max_hits=60)
    try: row=set_customer_personnel_enabled(customer_id,agent_id,body.enabled)
    except ValueError as exc: raise HTTPException(status_code=400, detail=client_error_detail(exc)) from exc
    emit_audit(customer_id,"personnel_enabled" if body.enabled else "personnel_disabled",detail={"personnel_id":agent_id})
    return row


@router.post("/factory/backup")
async def customer_factory_backup(payload: dict = Depends(_get_token_payload)):
    from web.backend.services.customer_factory_establishment import tenant_snapshot
    customer_id=str(payload["sub"]); _enforce_factory_write_limit(customer_id,"backup",max_hits=6)
    return tenant_snapshot(customer_id)


@router.post("/pipeline/run")
async def customer_pipeline_run(body: CustomerCreateRunRequest, payload: dict = Depends(_get_token_payload)):
    customer_id = payload["sub"]
    profile = commerce.get_customer(customer_id)
    if not profile:
        raise HTTPException(status_code=401, detail="Customer not found")
    plan = str(profile.get("plan") or "free").lower()
    # Immediate revenue model: free has strict 3 runs/month.
    if plan == "free":
        quota = commerce.consume_monthly_run(customer_id, limit=3)
        if not quota.get("allowed"):
            raise HTTPException(
                status_code=402,
                detail="Free tier limit reached (3 pipeline runs/month). Upgrade required.",
            )

    from web.backend.services.prompt_safety import (
        prepare_untrusted_plain_text,
        rejection_reason_if_blocked,
    )

    idea_raw = (body.idea or "").strip()
    blocked = rejection_reason_if_blocked(idea_raw, context="customer_idea")
    if blocked:
        raise HTTPException(status_code=400, detail=blocked)
    idea_clean = prepare_untrusted_plain_text(idea_raw, max_len=8000)
    if len(idea_clean) < 8:
        raise HTTPException(status_code=422, detail="Idea is too short.")

    product_id = f"prod-{uuid.uuid4().hex[:12]}"
    ts = time.time()
    product = {
        "id": product_id,
        "idea": idea_clean,
        "admin_instructions": None,
        "delivery_profile": "full_software",
        "production_mode": False,
        "category": "saas",
        "tags": [],
        "state": "IDEA_RECEIVED",
        "created_at": ts,
        "updated_at": ts,
        "tasks": [],
        "spec": None,
        "architecture": None,
        "code": None,
        "marketing": None,
        "pricing": None,
        "evolution_history": [],
        "metadata": {
            "owner_customer_id": customer_id,
            "owner_email": profile.get("email"),
            "owner_plan": plan,
            "watermark_policy": "on" if plan == "free" else "off",
        },
    }
    from web.backend.services.tenant_workspaces import (
        customer_workspace_id,
        write_customer_product,
    )
    try:
        stored = write_customer_product(customer_id, product)
    except Exception as exc:
        logger.exception("Tenant pipeline enqueue failed for customer=%s", customer_id)
        raise HTTPException(status_code=503, detail="Pipeline store unavailable. Try again shortly.") from exc
    return {
        "product_id": product_id,
        "state": "IDEA_RECEIVED",
        "plan": plan,
        "workspace_id": customer_workspace_id(customer_id),
        "tenant_isolated": True,
    }


@router.get("/orders/{order_id}/download")
async def download_order(order_id: str, payload: dict = Depends(_get_token_payload)):
    orders = commerce.get_orders_for_customer(payload["sub"])
    order = next((o for o in orders if o["id"] == order_id), None)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    archive = commerce.build_download_archive(order)
    return FileResponse(
        path=str(archive),
        media_type="application/zip",
        filename=archive.name,
    )
