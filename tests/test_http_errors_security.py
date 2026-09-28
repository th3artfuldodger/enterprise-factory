"""Client-facing error detail must not reflect host paths or credentials."""

from web.backend.core.http_errors import client_error_detail


def test_client_error_detail_keeps_short_validation_message():
    assert client_error_detail(ValueError("product not found")) == "product not found"


def test_client_error_detail_hides_host_path():
    exc = ValueError("failed to read /Users/example/private/config.yaml")
    assert client_error_detail(exc, fallback="Invalid request") == "Invalid request"


def test_client_error_detail_hides_credential_url():
    exc = ValueError("cannot connect to postgresql://alice:secret@db.internal/app")
    assert client_error_detail(exc, fallback="Connection failed") == "Connection failed"


def test_client_error_detail_hides_secret_assignment():
    fake_secret = "sk" + "-" + ("a" * 26)
    exc = ValueError("api_key=" + fake_secret)
    assert client_error_detail(exc, fallback="Invalid request") == "Invalid request"


def test_client_error_detail_hides_non_validation_exception():
    assert client_error_detail(RuntimeError("internal detail"), fallback="Failed") == "Failed"
