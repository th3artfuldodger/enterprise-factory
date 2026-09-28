"""Static authorization invariants for security-critical route families.

These tests deliberately inspect source instead of importing the full app so they
remain cheap enough for the dedicated security CI job.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _text(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def test_admin_dashboard_router_requires_rbac():
    src = _text("web/backend/api/admin/dashboard/_router.py")
    assert "dependencies=[Depends(require_admin_with_rbac)]" in src


def test_admin_metrics_websocket_authenticates_before_accept():
    src = _text("web/backend/main.py")
    start = src.index('@app.websocket("/api/admin/ws/metrics")')
    end = src.index("# Config endpoint", start)
    block = src[start:end]
    assert "await require_admin_websocket(websocket)" in block
    assert block.index("await require_admin_websocket(websocket)") < block.index("websocket.accept(")


def test_ai_market_refund_ledger_requires_admin_role():
    src = _text("web/backend/api/ai_market_protocol_v1.py")
    assert "def _require_liability_admin(admin: dict = Depends(require_admin_with_rbac))" in src
    assert 'Depends(_require_liability_admin)' in src
    assert "AdminRole.ADMIN" in src and "AdminRole.SUPER_ADMIN" in src


def test_customer_mutations_require_customer_identity():
    src = _text("web/backend/api/customer.py")
    required_fragments = (
        'async def demo_notes_create(body: DemoNoteCreateRequest, payload: dict = Depends(_get_token_payload))',
        'payload: dict = Depends(_get_token_payload)',
        'async def create_stripe_checkout_session(body: StripeCheckoutRequest, payload: dict = Depends(_get_token_payload))',
        'async def customer_pipeline_run(body: CustomerCreateRunRequest, payload: dict = Depends(_get_token_payload))',
    )
    for fragment in required_fragments:
        assert fragment in src


def test_stripe_webhook_requires_signature_verification():
    src = _text("web/backend/api/customer.py")
    start = src.index('async def stripe_webhook(request: Request):')
    end = src.index("@router.", start + 1)
    block = src[start:end]
    assert 'request.headers.get("Stripe-Signature"' in block
    assert "_verify_stripe_signature(payload, signature, secret)" in block
