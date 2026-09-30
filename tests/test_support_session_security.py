from __future__ import annotations

import hashlib
import os
from pathlib import Path

import pytest
from fastapi import HTTPException

from web.backend.api import support_chat


def test_support_session_token_is_verified_by_hash() -> None:
    token = "temporary-support-token-for-test-only"
    sess = {
        "id": "spt-test1234567890",
        "created_at": support_chat.time.time(),
        "access_token_sha256": hashlib.sha256(token.encode("utf-8")).hexdigest(),
    }
    support_chat._verify_session_token(sess, token)
    with pytest.raises(HTTPException) as exc:
        support_chat._verify_session_token(sess, token + "-wrong")
    assert exc.value.status_code == 401


def test_support_session_file_is_owner_only_and_contains_no_plaintext_token(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(support_chat, "_SESSIONS_DIR", tmp_path / "support")
    token = "another-temporary-token-for-test-only"
    sess = {
        "id": "spt-test9876543210",
        "created_at": support_chat.time.time(),
        "access_token_sha256": hashlib.sha256(token.encode("utf-8")).hexdigest(),
        "messages": [],
    }
    support_chat._save_session(sess)
    path = support_chat._session_path(sess["id"])
    content = path.read_text(encoding="utf-8")
    assert token not in content
    if os.name == "posix":
        assert path.stat().st_mode & 0o077 == 0
        assert path.parent.stat().st_mode & 0o077 == 0


def test_legacy_support_session_plaintext_token_is_migrated_on_load(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(support_chat, "_SESSIONS_DIR", tmp_path / "support")
    token = "legacy-support-token-for-test-only"
    sid = "spt-legacy123456789"
    path = support_chat._session_path(sid)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        __import__("json").dumps({"id": sid, "created_at": support_chat.time.time(), "access_token": token, "messages": []}),
        encoding="utf-8",
    )

    loaded = support_chat._load_session(sid)
    assert "access_token" not in loaded
    assert loaded["access_token_sha256"] == hashlib.sha256(token.encode("utf-8")).hexdigest()
    assert token not in path.read_text(encoding="utf-8")
