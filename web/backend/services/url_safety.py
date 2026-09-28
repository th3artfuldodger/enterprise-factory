"""Validate outbound URLs (git remotes, webhooks) against SSRF and unsafe hosts."""

from __future__ import annotations

import ipaddress
import re
import socket
from urllib.parse import urlparse

_ALLOWED_GIT_HOST_SUFFIXES = (
    "github.com",
    "gitlab.com",
    "bitbucket.org",
)

_BLOCKED_HOSTNAMES = frozenset({"localhost", "metadata.google.internal"})


def validate_git_remote_url(url: str) -> str:
    """
    Allow only HTTPS remotes on public git hosts (GitHub / GitLab / Bitbucket).
    Blocks private IPs, loopback, and metadata endpoints.
    """
    raw = (url or "").strip()
    if not raw:
        return ""
    if len(raw) > 2048:
        raise ValueError("remote_url too long")
    parsed = urlparse(raw)
    if parsed.scheme != "https":
        raise ValueError("Git remote must use https://")
    host = (parsed.hostname or "").strip().lower()
    if not host:
        raise ValueError("Git remote URL missing host")
    if host in _BLOCKED_HOSTNAMES or host.endswith(".local"):
        raise ValueError("Git remote host not allowed")
    if "%" in host:
        raise ValueError("Invalid git remote host")

    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        ip = None
    if ip is not None:
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            raise ValueError("Git remote must not target a private or reserved IP")
    else:
        if not any(host == suffix or host.endswith(f".{suffix}") for suffix in _ALLOWED_GIT_HOST_SUFFIXES):
            raise ValueError(
                "Git remote host must be github.com, gitlab.com, or bitbucket.org "
                "(optionally a subdomain)"
            )
    if parsed.username or parsed.password:
        raise ValueError("Credentials in git remote URL are not allowed")
    if re.search(r"[\x00-\x1f]", raw):
        raise ValueError("Invalid characters in remote_url")
    return raw


def validate_capture_base_url(url: str) -> str:
    """Validate an operator-supplied capture base URL against SSRF targets.

    Public HTTP(S) hosts are allowed. Loopback is allowed only on the factory's
    own frontend ports (8080/9080), which preserves local screenshot workflows
    without allowing arbitrary access to services on the host/private network.
    """
    raw = (url or "").strip().rstrip("/")
    if not raw:
        raise ValueError("base_url is required")
    if len(raw) > 2048 or re.search(r"[\x00-\x1f]", raw):
        raise ValueError("Invalid base_url")
    parsed = urlparse(raw)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("base_url must use http:// or https://")
    host = (parsed.hostname or "").strip().lower()
    if not host:
        raise ValueError("base_url missing host")
    if parsed.username or parsed.password:
        raise ValueError("Credentials in base_url are not allowed")
    if host in {"metadata.google.internal", "metadata.aws.internal"} or host.endswith(".local"):
        raise ValueError("base_url host not allowed")

    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    loopback_factory = host in {"localhost", "127.0.0.1", "::1"} and port in {8080, 9080}
    if loopback_factory:
        return raw

    try:
        literal = ipaddress.ip_address(host)
        ips = [literal]
    except ValueError:
        try:
            infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
        except OSError as exc:
            raise ValueError("base_url host could not be resolved") from exc
        ips = []
        for info in infos:
            try:
                ips.append(ipaddress.ip_address(info[4][0]))
            except ValueError:
                continue
        if not ips:
            raise ValueError("base_url host could not be resolved")

    for ip in ips:
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            raise ValueError("base_url must not target a private or reserved IP")
    return raw
