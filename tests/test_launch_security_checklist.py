"""Regression checks for the pre-launch security checklist."""

from pathlib import Path

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from web.backend.api.customer import _enforce_bot_honeypot
from web.backend.schemas.api_requests import CustomerLoginRequest, CustomerRegisterRequest

ROOT = Path(__file__).resolve().parents[1]


def test_request_models_reject_unknown_fields():
    with pytest.raises(ValidationError):
        CustomerLoginRequest(
            email="person@example.test",
            password="correct-horse",
            unexpected_admin=True,
        )


def test_auth_honeypot_blocks_automated_form_fillers():
    _enforce_bot_honeypot("")
    with pytest.raises(HTTPException) as exc:
        _enforce_bot_honeypot("https://spam.example")
    assert exc.value.status_code == 400


def test_customer_auth_models_bound_honeypot_field():
    for model in (CustomerLoginRequest, CustomerRegisterRequest):
        field = model.model_fields["website"]
        assert field.exclude is True
        assert field.metadata


def test_frontend_has_no_direct_privileged_database_credentials():
    forbidden = (
        "process.env.DATABASE_URL",
        "process.env.POSTGRES_PASSWORD",
        "SUPABASE_SERVICE_ROLE",
        "service_role_key",
        "service-role-key",
    )
    for path in (ROOT / "web/frontend").rglob("*"):
        if not path.is_file() or "node_modules" in path.parts or ".next" in path.parts:
            continue
        if path.suffix not in {".ts", ".tsx", ".js", ".jsx"}:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for needle in forbidden:
            assert needle not in text, f"{needle} exposed in browser source: {path}"


def test_frontend_does_not_render_raw_user_html():
    for path in (ROOT / "web/frontend").rglob("*"):
        if not path.is_file() or "node_modules" in path.parts or ".next" in path.parts:
            continue
        if path.suffix not in {".ts", ".tsx", ".js", ".jsx"}:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        assert "dangerouslySetInnerHTML" not in text, f"raw HTML rendering found: {path}"


def test_https_enforcement_and_hsts_are_wired():
    src = (ROOT / "web/backend/main.py").read_text(encoding="utf-8")
    assert "AIFACTORY_FORCE_HTTPS" in src
    assert "RedirectResponse" in src
    assert "Strict-Transport-Security" in src
