from __future__ import annotations

import logging

from core.security_redaction import install_secret_redaction, redact_structure, redact_text


def test_redact_text_masks_common_secret_shapes() -> None:
    provider_token = "sk-" + ("a" * 26)
    value = f"Authorization: Bearer secret-bearer-token? token=abc123456789 {provider_token}"
    out = redact_text(value)
    assert "secret-bearer-token" not in out
    assert "abc123456789" not in out
    assert provider_token not in out
    assert "<redacted>" in out


def test_redact_structure_masks_secret_named_fields_recursively() -> None:
    raw = {
        "provider": {"api_key": "live-key-value", "model": "deepseek-chat"},
        "password": "customer-password",
        "nested": [{"token": "jwt-ish-value", "name": "safe"}],
    }
    out = redact_structure(raw)
    assert out["provider"]["api_key"] == "<configured>"
    assert out["password"] == "<configured>"
    assert out["nested"][0]["token"] == "<configured>"
    assert out["provider"]["model"] == "deepseek-chat"


def test_log_record_factory_redacts_before_handlers(caplog) -> None:
    install_secret_redaction()
    logger = logging.getLogger("security-redaction-test")
    with caplog.at_level(logging.INFO):
        token = "sk-" + ("b" * 26)
        logger.info("credential=%s", token)
    text = caplog.text
    assert token not in text
    assert "<redacted>" in text

def test_log_redaction_preserves_numeric_format_arguments(caplog) -> None:
    install_secret_redaction()
    logger = logging.getLogger("security-redaction-numeric-test")
    with caplog.at_level(logging.INFO):
        token = "sk-" + ("c" * 26)
        logger.info("status=%d secret=%s", 200, token)
    assert "status=200" in caplog.text
    assert token not in caplog.text



def test_redact_structure_masks_database_urls_and_sessions() -> None:
    raw = {
        "database_url": "postgresql://alice:super-secret@db.internal/app",
        "session_secret": "browser-session-secret",
        "safe_url": "https://example.test/public",
    }
    out = redact_structure(raw)
    assert out["database_url"] == "<configured>"
    assert out["session_secret"] == "<configured>"
    assert out["safe_url"] == "https://example.test/public"


def test_exception_traceback_is_redacted(caplog) -> None:
    install_secret_redaction()
    logger = logging.getLogger("security-redaction-exception-test")
    token = "sk-" + ("z" * 26)
    with caplog.at_level(logging.ERROR):
        try:
            raise RuntimeError(f"provider failed with {token}")
        except RuntimeError:
            logger.exception("provider request failed")
    assert token not in caplog.text
    assert "<redacted>" in caplog.text
