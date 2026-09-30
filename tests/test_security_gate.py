from __future__ import annotations

import importlib.util
from pathlib import Path


def _gate():
    path = Path(__file__).resolve().parents[1] / "scripts" / "security_gate.py"
    spec = importlib.util.spec_from_file_location("security_gate_under_test", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_forbidden_runtime_paths_and_live_env() -> None:
    gate = _gate()
    assert gate.forbidden_path(".env")
    assert gate.forbidden_path(".env.demo")
    assert gate.forbidden_path("production.env")
    assert gate.forbidden_path(".npmrc")
    assert gate.forbidden_path("credentials.json")
    assert gate.forbidden_path("data/users.json")
    assert gate.forbidden_path("data/state/pipeline.db")
    assert gate.forbidden_path("notes.sqlite3")
    assert gate.forbidden_path("thing.before-security")
    assert gate.forbidden_path(".env.example") is None
    assert gate.forbidden_path(".env.demo.example") is None
    assert gate.forbidden_path(".env.demo", history=True) is None
    assert gate.forbidden_path("deploy/hub-payment.env.example") is None
    assert gate.forbidden_path("deploy/hub-zk.env.example") is None
    assert gate.forbidden_path("deploy/hub-payment.env.example") is None
    assert gate.forbidden_path("deploy/hub-payment.env")


def test_scanner_blocks_realistic_token_but_allows_placeholders() -> None:
    gate = _gate()
    token = "ghp_" + ("A" * 30)
    assert gate.scan_text("x.txt", f"GITHUB_TOKEN={token}")
    assert gate.scan_text(".env.example", "DEEPSEEK_API_KEY=") == []
    assert gate.scan_text("x.sh", "DEEPSEEK_API_KEY=${DEEPSEEK_API_KEY:-}") == []


def test_history_mode_ignores_legacy_test_fixture_but_not_github_token() -> None:
    gate = _gate()
    assert gate.scan_text("tests/test_x.py", "sk-test-placeholder-not-a-real-key", history=True) == []
    token = "github_pat_" + ("B" * 36)
    issues = gate.scan_text("src.txt", token, history=True)
    assert "GitHub token" in issues


def test_unknown_sk_token_in_test_file_is_not_blanket_allowlisted() -> None:
    gate = _gate()
    token = "sk-" + ("Z9" * 16)
    assert "provider sk token" in gate.scan_text("tests/some_test.py", token, history=True)
