"""URL safety validators (git remote SSRF guards)."""

from __future__ import annotations

import pytest

from web.backend.services.url_safety import validate_capture_base_url, validate_git_remote_url


def test_validate_git_remote_accepts_github_https():
    assert validate_git_remote_url("https://github.com/org/repo.git") == (
        "https://github.com/org/repo.git"
    )


def test_validate_git_remote_rejects_private_ip():
    with pytest.raises(ValueError, match="private"):
        validate_git_remote_url("https://192.168.1.1/repo.git")


def test_validate_git_remote_rejects_localhost():
    with pytest.raises(ValueError, match="not allowed"):
        validate_git_remote_url("https://localhost/repo.git")


def test_validate_git_remote_rejects_http():
    with pytest.raises(ValueError, match="https"):
        validate_git_remote_url("http://github.com/org/repo.git")


def test_validate_git_remote_rejects_unknown_host():
    with pytest.raises(ValueError, match="github"):
        validate_git_remote_url("https://evil.example.com/repo.git")


def test_capture_url_allows_factory_loopback_ports():
    assert validate_capture_base_url("http://127.0.0.1:8080") == "http://127.0.0.1:8080"
    assert validate_capture_base_url("http://localhost:9080") == "http://localhost:9080"


def test_capture_url_rejects_private_ip():
    with pytest.raises(ValueError, match="private"):
        validate_capture_base_url("http://10.0.0.4:8080")


def test_capture_url_rejects_metadata_host():
    with pytest.raises(ValueError, match="not allowed"):
        validate_capture_base_url("http://metadata.google.internal/")


def test_capture_url_rejects_credentials():
    with pytest.raises(ValueError, match="Credentials"):
        validate_capture_base_url("https://user:pass@example.com/")


def test_capture_url_rejects_dns_to_private(monkeypatch):
    monkeypatch.setattr(
        "web.backend.services.url_safety.socket.getaddrinfo",
        lambda *_a, **_k: [(2, 1, 6, "", ("192.168.1.40", 443))],
    )
    with pytest.raises(ValueError, match="private"):
        validate_capture_base_url("https://example.test")
