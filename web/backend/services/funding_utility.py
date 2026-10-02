"""Separate Funding Utility for Trimble Enterprise.

Factory AI may submit requests.  It cannot authorize, spend, transfer, borrow,
invest, sign contracts, or make payouts.  Authorization lives here, outside the
Factory hierarchy, and every authorized/paid request gets matching append-only
Factory and Funding ledger entries that must reconcile.
"""
from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Literal

from core.paths import data_root

OWNER_APPROVAL_THRESHOLD_USD = 1000.0
OWNER_LOCK_THRESHOLD_USD = 5000.0

FundingBand = Literal[
    "budget_auto",
    "enhanced_verification",
    "owner_approval",
    "owner_locked",
]

FINAL_STATUSES = {"rejected", "paid", "cancelled"}


def funding_db_path() -> Path:
    path = data_root() / "funding" / "state" / "funding_utility.db"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(str(funding_db_path()), timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS funding_requests (
            id TEXT PRIMARY KEY,
            workspace_id TEXT NOT NULL,
            product_id TEXT,
            department TEXT,
            requested_by TEXT NOT NULL,
            requested_by_label TEXT,
            amount_usd REAL NOT NULL,
            purpose TEXT NOT NULL,
            source_preference TEXT,
            restrictions_json TEXT NOT NULL DEFAULT '[]',
            preapproved_budget INTEGER NOT NULL DEFAULT 0,
            band TEXT NOT NULL,
            status TEXT NOT NULL,
            verification_json TEXT NOT NULL DEFAULT '{}',
            decision_card_json TEXT NOT NULL DEFAULT '{}',
            owner_decision TEXT,
            owner_decision_note TEXT,
            authorized_amount_usd REAL,
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_funding_requests_workspace
            ON funding_requests(workspace_id, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_funding_requests_status
            ON funding_requests(status, created_at DESC);

        CREATE TABLE IF NOT EXISTS factory_capital_ledger (
            entry_id TEXT PRIMARY KEY,
            request_id TEXT NOT NULL,
            workspace_id TEXT NOT NULL,
            entry_type TEXT NOT NULL,
            amount_usd REAL NOT NULL,
            source TEXT,
            destination TEXT,
            restrictions_json TEXT NOT NULL DEFAULT '[]',
            ref TEXT NOT NULL,
            created_at REAL NOT NULL
        );

        CREATE TABLE IF NOT EXISTS funding_capital_ledger (
            entry_id TEXT PRIMARY KEY,
            request_id TEXT NOT NULL,
            workspace_id TEXT NOT NULL,
            entry_type TEXT NOT NULL,
            amount_usd REAL NOT NULL,
            source TEXT,
            destination TEXT,
            restrictions_json TEXT NOT NULL DEFAULT '[]',
            ref TEXT NOT NULL,
            created_at REAL NOT NULL
        );

        CREATE TABLE IF NOT EXISTS funding_reconciliations (
            id TEXT PRIMARY KEY,
            request_id TEXT NOT NULL,
            workspace_id TEXT NOT NULL,
            factory_total_usd REAL NOT NULL,
            funding_total_usd REAL NOT NULL,
            matched INTEGER NOT NULL,
            detail TEXT,
            created_at REAL NOT NULL
        );

        CREATE TABLE IF NOT EXISTS capital_route_events (
            id TEXT PRIMARY KEY,
            request_id TEXT NOT NULL,
            workspace_id TEXT NOT NULL,
            source TEXT,
            destination TEXT,
            amount_usd REAL NOT NULL,
            restrictions_json TEXT NOT NULL DEFAULT '[]',
            status TEXT NOT NULL,
            created_at REAL NOT NULL
        );

        CREATE TABLE IF NOT EXISTS funding_budgets (
            id TEXT PRIMARY KEY,
            workspace_id TEXT NOT NULL,
            department TEXT,
            product_id TEXT,
            ceiling_usd REAL NOT NULL,
            used_usd REAL NOT NULL DEFAULT 0,
            active INTEGER NOT NULL DEFAULT 1,
            approved_by TEXT NOT NULL,
            note TEXT,
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_funding_budgets_scope
            ON funding_budgets(workspace_id, department, product_id, active);

        CREATE TABLE IF NOT EXISTS funding_opportunities (
            id TEXT PRIMARY KEY,
            workspace_id TEXT NOT NULL,
            scout_id TEXT NOT NULL,
            opportunity_type TEXT NOT NULL,
            title TEXT NOT NULL,
            source_url TEXT,
            amount_estimate_usd REAL,
            restrictions_json TEXT NOT NULL DEFAULT '[]',
            status TEXT NOT NULL,
            evidence_json TEXT NOT NULL DEFAULT '{}',
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_funding_opportunities_workspace
            ON funding_opportunities(workspace_id, status, created_at DESC);

        CREATE TRIGGER IF NOT EXISTS factory_capital_ledger_no_update
        BEFORE UPDATE ON factory_capital_ledger
        BEGIN
          SELECT RAISE(ABORT, 'factory_capital_ledger is append-only');
        END;
        CREATE TRIGGER IF NOT EXISTS factory_capital_ledger_no_delete
        BEFORE DELETE ON factory_capital_ledger
        BEGIN
          SELECT RAISE(ABORT, 'factory_capital_ledger is append-only');
        END;
        CREATE TRIGGER IF NOT EXISTS funding_capital_ledger_no_update
        BEFORE UPDATE ON funding_capital_ledger
        BEGIN
          SELECT RAISE(ABORT, 'funding_capital_ledger is append-only');
        END;
        CREATE TRIGGER IF NOT EXISTS funding_capital_ledger_no_delete
        BEFORE DELETE ON funding_capital_ledger
        BEGIN
          SELECT RAISE(ABORT, 'funding_capital_ledger is append-only');
        END;
        """
    )
    conn.commit()
    return conn


FUNDING_OPPORTUNITY_STATES = (
    "found",
    "eligible",
    "application_ready",
    "submitted",
    "awarded",
    "received",
    "rejected",
)
_OPPORTUNITY_TRANSITIONS = {
    "found": {"eligible", "rejected"},
    "eligible": {"application_ready", "rejected"},
    "application_ready": {"submitted", "rejected"},
    "submitted": {"awarded", "rejected"},
    "awarded": {"received", "rejected"},
    "received": set(),
    "rejected": set(),
}


def create_preapproved_budget(
    *,
    workspace_id: str,
    ceiling_usd: float,
    approved_by: str,
    department: str | None = None,
    product_id: str | None = None,
    note: str = "",
) -> dict[str, Any]:
    ws = str(workspace_id or "").strip()
    owner = str(approved_by or "").strip()
    ceiling = round(float(ceiling_usd), 2)
    if not ws or not owner:
        raise ValueError("workspace_id and approved_by are required")
    if ceiling <= 0:
        raise ValueError("Budget ceiling must be positive")
    now = time.time()
    budget_id = f"budget-{uuid.uuid4().hex[:16]}"
    with _connect() as conn:
        conn.execute(
            """INSERT INTO funding_budgets
               (id, workspace_id, department, product_id, ceiling_usd, used_usd,
                active, approved_by, note, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, 0, 1, ?, ?, ?, ?)""",
            (
                budget_id, ws, str(department or "") or None,
                str(product_id or "") or None, ceiling, owner,
                str(note or "")[:2000], now, now,
            ),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM funding_budgets WHERE id = ?", (budget_id,)).fetchone()
    return dict(row) if row else {}


def list_preapproved_budgets(*, workspace_id: str | None = None) -> list[dict[str, Any]]:
    with _connect() as conn:
        if workspace_id:
            rows = conn.execute(
                "SELECT * FROM funding_budgets WHERE workspace_id = ? ORDER BY created_at DESC",
                (workspace_id,),
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM funding_budgets ORDER BY created_at DESC").fetchall()
    return [{**dict(row), "active": bool(row["active"])} for row in rows]


def _matching_budget(
    conn: sqlite3.Connection,
    *,
    workspace_id: str,
    department: str,
    product_id: str | None,
    amount_usd: float,
) -> dict[str, Any] | None:
    rows = conn.execute(
        """SELECT * FROM funding_budgets
           WHERE workspace_id = ? AND active = 1
           ORDER BY
             CASE WHEN product_id = ? THEN 0 WHEN product_id IS NULL THEN 1 ELSE 2 END,
             CASE WHEN department = ? THEN 0 WHEN department IS NULL THEN 1 ELSE 2 END,
             created_at ASC""",
        (workspace_id, product_id, department),
    ).fetchall()
    amount = round(float(amount_usd), 2)
    for row in rows:
        data = dict(row)
        pscope = data.get("product_id")
        dscope = data.get("department")
        if pscope and pscope != product_id:
            continue
        if dscope and dscope != department:
            continue
        remaining = round(float(data["ceiling_usd"]) - float(data["used_usd"]), 2)
        if remaining + 1e-9 >= amount:
            data["remaining_usd"] = remaining
            return data
    return None


def deactivate_budget(budget_id: str) -> dict[str, Any]:
    with _connect() as conn:
        cur = conn.execute(
            "UPDATE funding_budgets SET active = 0, updated_at = ? WHERE id = ?",
            (time.time(), budget_id),
        )
        if cur.rowcount < 1:
            raise ValueError("Budget not found")
        conn.commit()
        row = conn.execute("SELECT * FROM funding_budgets WHERE id = ?", (budget_id,)).fetchone()
    return dict(row) if row else {}


def create_funding_opportunity(
    *,
    workspace_id: str,
    scout_id: str,
    opportunity_type: str,
    title: str,
    source_url: str | None = None,
    amount_estimate_usd: float | None = None,
    restrictions: list[str] | None = None,
    evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    ws = str(workspace_id or "").strip()
    scout = str(scout_id or "").strip()
    title_clean = str(title or "").strip()
    if not ws or not scout or not title_clean:
        raise ValueError("workspace_id, scout_id, and title are required")
    if not scout.startswith("funding:"):
        raise ValueError("Funding opportunities must originate from a Funding Utility scout")
    now = time.time()
    oid = f"opp-{uuid.uuid4().hex[:16]}"
    with _connect() as conn:
        conn.execute(
            """INSERT INTO funding_opportunities
               (id, workspace_id, scout_id, opportunity_type, title, source_url,
                amount_estimate_usd, restrictions_json, status, evidence_json,
                created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'found', ?, ?, ?)""",
            (
                oid, ws, scout, str(opportunity_type or "")[:80],
                title_clean[:500], str(source_url or "")[:2000] or None,
                None if amount_estimate_usd is None else round(float(amount_estimate_usd), 2),
                json.dumps([str(x)[:240] for x in (restrictions or [])][:20]),
                json.dumps(dict(evidence or {})), now, now,
            ),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM funding_opportunities WHERE id = ?", (oid,)).fetchone()
    return _opportunity_row(row) or {}


def _opportunity_row(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    data = dict(row)
    try:
        data["restrictions"] = json.loads(data.pop("restrictions_json") or "[]")
    except Exception:
        data["restrictions"] = []
    try:
        data["evidence"] = json.loads(data.pop("evidence_json") or "{}")
    except Exception:
        data["evidence"] = {}
    return data


def get_funding_opportunity(opportunity_id: str) -> dict[str, Any] | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM funding_opportunities WHERE id = ?",
            (str(opportunity_id or "").strip(),),
        ).fetchone()
    return _opportunity_row(row)


def advance_funding_opportunity(
    opportunity_id: str,
    *,
    next_status: str,
    evidence_update: dict[str, Any] | None = None,
) -> dict[str, Any]:
    desired = str(next_status or "").strip().lower()
    if desired not in FUNDING_OPPORTUNITY_STATES:
        raise ValueError("Unknown funding opportunity status")
    with _connect() as conn:
        current = _opportunity_row(
            conn.execute("SELECT * FROM funding_opportunities WHERE id = ?", (opportunity_id,)).fetchone()
        )
        if not current:
            raise ValueError("Funding opportunity not found")
        allowed = _OPPORTUNITY_TRANSITIONS.get(str(current["status"]), set())
        if desired not in allowed:
            raise ValueError(f"Invalid funding transition {current['status']} -> {desired}")
        evidence = dict(current.get("evidence") or {})
        evidence.update(dict(evidence_update or {}))
        conn.execute(
            "UPDATE funding_opportunities SET status = ?, evidence_json = ?, updated_at = ? WHERE id = ?",
            (desired, json.dumps(evidence), time.time(), opportunity_id),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM funding_opportunities WHERE id = ?", (opportunity_id,)).fetchone()
    return _opportunity_row(row) or {}


def list_funding_opportunities(
    *, workspace_id: str | None = None, status: str | None = None, limit: int = 200
) -> list[dict[str, Any]]:
    lim = max(1, min(int(limit), 500))
    clauses: list[str] = []
    params: list[Any] = []
    if workspace_id:
        clauses.append("workspace_id = ?")
        params.append(workspace_id)
    if status:
        clauses.append("status = ?")
        params.append(status)
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    with _connect() as conn:
        rows = conn.execute(
            f"SELECT * FROM funding_opportunities{where} ORDER BY created_at DESC LIMIT ?",
            (*params, lim),
        ).fetchall()
    return [_opportunity_row(row) or {} for row in rows]


def funding_band(amount_usd: float, *, preapproved_budget: bool = False) -> FundingBand:
    amount = float(amount_usd)
    if amount <= 0:
        raise ValueError("Funding amount must be positive")
    if amount < 100:
        return "budget_auto" if preapproved_budget else "enhanced_verification"
    if amount < 1000:
        return "enhanced_verification"
    if amount < 5000:
        return "owner_approval"
    return "owner_locked"


def _initial_status(band: FundingBand) -> str:
    if band == "budget_auto":
        return "authorized"
    if band == "enhanced_verification":
        return "verification_required"
    return "owner_approval_required"


def _row(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    out = dict(row)
    for key in ("restrictions_json", "verification_json", "decision_card_json"):
        raw = out.pop(key, None)
        name = key.removesuffix("_json")
        try:
            out[name] = json.loads(raw or ("[]" if key == "restrictions_json" else "{}"))
        except Exception:
            out[name] = [] if key == "restrictions_json" else {}
    for key in ("preapproved_budget",):
        out[key] = bool(out.get(key))
    return out


def _assert_factory_requester(requested_by: str) -> None:
    actor = str(requested_by or "").strip()
    if not actor:
        raise ValueError("requested_by is required")
    # Explicitly block attempts to smuggle an authorizer into a Factory request.
    lowered = actor.lower()
    if lowered.startswith(("funding-authorizer", "owner", "treasury-dispatcher")):
        raise ValueError("Factory funding requests must originate from Factory personnel")


def notify_owner_if_required(request: dict[str, Any]) -> None:
    """Best-effort phone/web + Telegram alert for every $100+ capital request."""
    amount = float(request.get("amount_usd") or 0)
    if amount < 100:
        return
    body = (
        f"Funding request {request.get('id')} · USD {amount:,.2f} · "
        f"{request.get('department') or 'Factory'} · {request.get('status')}"
    )

    def run() -> None:
        try:
            from web.backend.services.web_push_service import broadcast_payload
            broadcast_payload(title="Trimble Enterprise · Funding", body=body, url="/admin")
        except Exception:
            pass
        try:
            from web.backend.services.telegram_pipeline_notify import send_telegram_message_sync
            send_telegram_message_sync("Trimble Enterprise · Funding\n" + body)
        except Exception:
            pass

    threading.Thread(target=run, daemon=True).start()


def submit_funding_request(
    *,
    workspace_id: str,
    product_id: str | None,
    department: str,
    requested_by: str,
    requested_by_label: str | None,
    amount_usd: float,
    purpose: str,
    source_preference: str | None = None,
    restrictions: list[str] | None = None,
    preapproved_budget: bool = False,
) -> dict[str, Any]:
    _assert_factory_requester(requested_by)
    ws = str(workspace_id or "").strip()
    if not ws:
        raise ValueError("workspace_id is required")
    purpose_clean = str(purpose or "").strip()
    if not purpose_clean:
        raise ValueError("Funding purpose is required")
    amount = round(float(amount_usd), 2)
    now = time.time()
    request_id = f"fund-{uuid.uuid4().hex[:16]}"
    restrictions_clean = [str(v).strip()[:240] for v in (restrictions or []) if str(v).strip()][:20]

    with _connect() as conn:
        # A boolean alone never grants automatic spending authority. Under-$100
        # auto-routing requires a real owner-created budget with enough remaining
        # headroom for this workspace/department/product.
        budget = None
        if amount < 100 and preapproved_budget:
            budget = _matching_budget(
                conn,
                workspace_id=ws,
                department=str(department or ""),
                product_id=product_id,
                amount_usd=amount,
            )
        budget_authorized = budget is not None
        band = funding_band(amount, preapproved_budget=budget_authorized)
        status = _initial_status(band)
        conn.execute(
            """
            INSERT INTO funding_requests (
                id, workspace_id, product_id, department, requested_by,
                requested_by_label, amount_usd, purpose, source_preference,
                restrictions_json, preapproved_budget, band, status,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                request_id, ws, product_id, str(department or "")[:80],
                str(requested_by), str(requested_by_label or "")[:120],
                amount, purpose_clean[:4000], str(source_preference or "")[:240],
                json.dumps(restrictions_clean), 1 if budget_authorized else 0,
                band, status, now, now,
            ),
        )
        if status == "authorized":
            if budget is not None:
                updated = conn.execute(
                    """UPDATE funding_budgets
                       SET used_usd = used_usd + ?, updated_at = ?
                       WHERE id = ? AND active = 1 AND used_usd + ? <= ceiling_usd""",
                    (amount, now, budget["id"], amount),
                )
                if updated.rowcount != 1:
                    raise ValueError("Preapproved budget no longer has sufficient headroom")
            _append_matching_entries(
                conn,
                request_id=request_id,
                workspace_id=ws,
                entry_type="authorization",
                amount_usd=amount,
                source=source_preference or "preapproved_budget",
                destination=department or product_id or "factory",
                restrictions=restrictions_clean,
                ref=f"{request_id}:auto-authorized",
            )
            conn.execute(
                "UPDATE funding_requests SET authorized_amount_usd = ? WHERE id = ?",
                (amount, request_id),
            )
            _append_route_event(
                conn,
                request_id=request_id,
                workspace_id=ws,
                source=source_preference or "preapproved_budget",
                destination=department or product_id or "factory",
                amount_usd=amount,
                restrictions=restrictions_clean,
                status="authorized",
            )
        conn.commit()
        row = conn.execute("SELECT * FROM funding_requests WHERE id = ?", (request_id,)).fetchone()
    result = _row(row) or {}
    source_id = str(result.get("source_preference") or "").strip()
    if result.get("status") == "verification_required" and source_id.startswith("opp-"):
        opportunity = get_funding_opportunity(source_id)
        if (
            opportunity
            and opportunity.get("workspace_id") == ws
            and opportunity.get("status") == "received"
        ):
            estimate = opportunity.get("amount_estimate_usd")
            amount_ok = estimate is None or float(estimate) + 1e-9 >= amount
            if amount_ok:
                return record_verification(
                    request_id,
                    verifier_id="funding:verifier",
                    passed=True,
                    evidence={
                        "funding_opportunity_id": source_id,
                        "opportunity_status": "received",
                        "source_url": opportunity.get("source_url"),
                        "source_verified": True,
                    },
                    note="Automatically verified against a received Funding Utility opportunity.",
                )
    notify_owner_if_required(result)
    return result


def verification_requirements(request: dict[str, Any]) -> list[str]:
    band = str(request.get("band") or "")
    base = [
        "confirm_source_and_eligibility",
        "confirm_amount_and_destination",
        "confirm_restrictions",
        "conflict_or_duplicate_check",
    ]
    if band in {"owner_approval", "owner_locked"}:
        base.extend(["market_evidence_review", "capital_efficiency_review", "risk_review"])
    if band == "owner_locked":
        base.extend([
            "roi_range",
            "break_even_analysis",
            "maximum_loss",
            "confidence_score",
            "cheaper_alternatives",
            "independent_audit",
        ])
    return base


def record_verification(
    request_id: str,
    *,
    verifier_id: str,
    passed: bool,
    evidence: dict[str, Any] | None = None,
    note: str = "",
) -> dict[str, Any]:
    rid = str(request_id or "").strip()
    verifier = str(verifier_id or "").strip()
    if not verifier:
        raise ValueError("Funding verifier identity is required")
    with _connect() as conn:
        existing = _row(conn.execute("SELECT * FROM funding_requests WHERE id = ?", (rid,)).fetchone())
        if not existing:
            raise ValueError("Funding request not found")
        if existing["status"] in FINAL_STATUSES:
            raise ValueError("Funding request is already final")
        verification = {
            "verifier_id": verifier,
            "passed": bool(passed),
            "note": str(note or "")[:2000],
            "requirements": verification_requirements(existing),
            "evidence": dict(evidence or {}),
            "verified_at": time.time(),
        }
        if not passed:
            next_status = "verification_failed"
        elif existing["band"] == "enhanced_verification":
            next_status = "authorized"
        else:
            next_status = "owner_approval_required"
        now = time.time()
        conn.execute(
            "UPDATE funding_requests SET verification_json = ?, status = ?, updated_at = ? WHERE id = ?",
            (json.dumps(verification), next_status, now, rid),
        )
        if next_status == "authorized":
            amount = float(existing["amount_usd"])
            restrictions = list(existing.get("restrictions") or [])
            _append_matching_entries(
                conn,
                request_id=rid,
                workspace_id=existing["workspace_id"],
                entry_type="authorization",
                amount_usd=amount,
                source=existing.get("source_preference") or "verified_funding",
                destination=existing.get("department") or existing.get("product_id") or "factory",
                restrictions=restrictions,
                ref=f"{rid}:verified-authorized",
            )
            conn.execute(
                "UPDATE funding_requests SET authorized_amount_usd = ? WHERE id = ?",
                (amount, rid),
            )
            _append_route_event(
                conn,
                request_id=rid,
                workspace_id=existing["workspace_id"],
                source=existing.get("source_preference") or "verified_funding",
                destination=existing.get("department") or existing.get("product_id") or "factory",
                amount_usd=amount,
                restrictions=restrictions,
                status="authorized",
            )
        conn.commit()
        row = conn.execute("SELECT * FROM funding_requests WHERE id = ?", (rid,)).fetchone()
    result = _row(row) or {}
    notify_owner_if_required(result)
    return result


def build_capital_decision_card(
    request: dict[str, Any],
    *,
    roi_low_pct: float | None = None,
    roi_high_pct: float | None = None,
    break_even_months: float | None = None,
    maximum_loss_usd: float | None = None,
    confidence: float | None = None,
    risk_score: float | None = None,
    market_evidence_summary: str = "",
    capital_efficiency_summary: str = "",
    independent_audit_summary: str = "",
    cheaper_alternatives: list[str] | None = None,
    plain_language_rationale: str = "",
) -> dict[str, Any]:
    amount = float(request.get("amount_usd") or 0)
    return {
        "request_id": request.get("id"),
        "amount_usd": amount,
        "risk_meter_0_100": None if risk_score is None else max(0.0, min(100.0, float(risk_score))),
        "roi_range_pct": [roi_low_pct, roi_high_pct],
        "break_even_months": break_even_months,
        "maximum_loss_usd": maximum_loss_usd if maximum_loss_usd is not None else amount,
        "confidence_0_100": None if confidence is None else max(0.0, min(100.0, float(confidence))),
        "market_evidence": str(market_evidence_summary or "")[:4000],
        "capital_efficiency": str(capital_efficiency_summary or "")[:4000],
        "independent_audit": str(independent_audit_summary or "")[:4000],
        "cheaper_alternatives": [str(x)[:500] for x in (cheaper_alternatives or [])][:12],
        "plain_language_rationale": str(plain_language_rationale or "")[:2000],
        "owner_only": amount >= OWNER_LOCK_THRESHOLD_USD,
    }


def save_decision_card(request_id: str, card: dict[str, Any]) -> dict[str, Any]:
    with _connect() as conn:
        cur = conn.execute(
            "UPDATE funding_requests SET decision_card_json = ?, updated_at = ? WHERE id = ?",
            (json.dumps(dict(card or {})), time.time(), request_id),
        )
        if cur.rowcount < 1:
            raise ValueError("Funding request not found")
        conn.commit()
        row = conn.execute("SELECT * FROM funding_requests WHERE id = ?", (request_id,)).fetchone()
    return _row(row) or {}


def owner_decide(
    request_id: str,
    *,
    approved: bool,
    owner_id: str,
    note: str = "",
) -> dict[str, Any]:
    if not str(owner_id or "").strip():
        raise ValueError("Owner identity is required")
    rid = str(request_id or "").strip()
    with _connect() as conn:
        existing = _row(conn.execute("SELECT * FROM funding_requests WHERE id = ?", (rid,)).fetchone())
        if not existing:
            raise ValueError("Funding request not found")
        if existing["band"] not in {"owner_approval", "owner_locked"}:
            raise ValueError("This funding band does not require an owner decision")
        verification = dict(existing.get("verification") or {})
        if not verification.get("passed"):
            raise ValueError("Funding verification must pass before owner decision")
        if existing["band"] == "owner_locked":
            card = dict(existing.get("decision_card") or {})
            required = (
                "risk_meter_0_100",
                "roi_range_pct",
                "break_even_months",
                "maximum_loss_usd",
                "confidence_0_100",
                "market_evidence",
                "capital_efficiency",
                "independent_audit",
                "cheaper_alternatives",
                "plain_language_rationale",
            )
            missing = [key for key in required if card.get(key) in (None, "", [], {})]
            if missing:
                raise ValueError("Owner-locked request is missing decision-card analysis: " + ", ".join(missing))
        now = time.time()
        next_status = "authorized" if approved else "rejected"
        conn.execute(
            """
            UPDATE funding_requests
            SET status = ?, owner_decision = ?, owner_decision_note = ?,
                authorized_amount_usd = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                next_status,
                "approved" if approved else "rejected",
                str(note or "")[:2000],
                float(existing["amount_usd"]) if approved else None,
                now,
                rid,
            ),
        )
        if approved:
            restrictions = list(existing.get("restrictions") or [])
            _append_matching_entries(
                conn,
                request_id=rid,
                workspace_id=existing["workspace_id"],
                entry_type="authorization",
                amount_usd=float(existing["amount_usd"]),
                source=existing.get("source_preference") or "owner_approved_funding",
                destination=existing.get("department") or existing.get("product_id") or "factory",
                restrictions=restrictions,
                ref=f"{rid}:owner-authorized",
            )
            _append_route_event(
                conn,
                request_id=rid,
                workspace_id=existing["workspace_id"],
                source=existing.get("source_preference") or "owner_approved_funding",
                destination=existing.get("department") or existing.get("product_id") or "factory",
                amount_usd=float(existing["amount_usd"]),
                restrictions=restrictions,
                status="authorized",
            )
        conn.commit()
        row = conn.execute("SELECT * FROM funding_requests WHERE id = ?", (rid,)).fetchone()
    result = _row(row) or {}
    notify_owner_if_required(result)
    return result


def record_payment(
    request_id: str,
    *,
    dispatcher_id: str,
    payment_ref: str,
    source: str,
    destination: str,
    amount_usd: float | None = None,
) -> dict[str, Any]:
    """Record an externally executed payment.  This function never moves money."""
    if not str(dispatcher_id or "").strip():
        raise ValueError("Treasury dispatcher identity is required")
    if not str(payment_ref or "").strip():
        raise ValueError("Payment reference is required")
    with _connect() as conn:
        existing = _row(conn.execute("SELECT * FROM funding_requests WHERE id = ?", (request_id,)).fetchone())
        if not existing:
            raise ValueError("Funding request not found")
        if existing["status"] != "authorized":
            raise ValueError("Funding request must be authorized before payment can be recorded")
        amount = round(float(amount_usd if amount_usd is not None else existing["amount_usd"]), 2)
        if amount <= 0 or amount > float(existing["authorized_amount_usd"] or 0) + 1e-9:
            raise ValueError("Payment amount exceeds authorized amount")
        restrictions = list(existing.get("restrictions") or [])
        _append_matching_entries(
            conn,
            request_id=request_id,
            workspace_id=existing["workspace_id"],
            entry_type="payment",
            amount_usd=amount,
            source=source,
            destination=destination,
            restrictions=restrictions,
            ref=str(payment_ref),
        )
        _append_route_event(
            conn,
            request_id=request_id,
            workspace_id=existing["workspace_id"],
            source=source,
            destination=destination,
            amount_usd=amount,
            restrictions=restrictions,
            status="paid",
        )
        conn.execute(
            "UPDATE funding_requests SET status = 'paid', updated_at = ? WHERE id = ?",
            (time.time(), request_id),
        )
        conn.commit()
    return reconcile_request(request_id)


def _append_matching_entries(
    conn: sqlite3.Connection,
    *,
    request_id: str,
    workspace_id: str,
    entry_type: str,
    amount_usd: float,
    source: str | None,
    destination: str | None,
    restrictions: list[str],
    ref: str,
) -> None:
    now = time.time()
    common = (
        request_id, workspace_id, entry_type, round(float(amount_usd), 2),
        source, destination, json.dumps(restrictions), ref, now,
    )
    conn.execute(
        """
        INSERT INTO factory_capital_ledger
        (entry_id, request_id, workspace_id, entry_type, amount_usd, source, destination, restrictions_json, ref, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (f"fcl-{uuid.uuid4().hex[:16]}", *common),
    )
    conn.execute(
        """
        INSERT INTO funding_capital_ledger
        (entry_id, request_id, workspace_id, entry_type, amount_usd, source, destination, restrictions_json, ref, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (f"ful-{uuid.uuid4().hex[:16]}", *common),
    )


def _append_route_event(
    conn: sqlite3.Connection,
    *,
    request_id: str,
    workspace_id: str,
    source: str,
    destination: str,
    amount_usd: float,
    restrictions: list[str],
    status: str,
) -> None:
    conn.execute(
        """
        INSERT INTO capital_route_events
        (id, request_id, workspace_id, source, destination, amount_usd, restrictions_json, status, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            f"route-{uuid.uuid4().hex[:16]}", request_id, workspace_id, source,
            destination, round(float(amount_usd), 2), json.dumps(restrictions),
            status, time.time(),
        ),
    )


def reconcile_request(request_id: str) -> dict[str, Any]:
    with _connect() as conn:
        request = _row(conn.execute("SELECT * FROM funding_requests WHERE id = ?", (request_id,)).fetchone())
        if not request:
            raise ValueError("Funding request not found")
        factory_rows = conn.execute(
            "SELECT entry_type, amount_usd, ref FROM factory_capital_ledger WHERE request_id = ? ORDER BY created_at",
            (request_id,),
        ).fetchall()
        funding_rows = conn.execute(
            "SELECT entry_type, amount_usd, ref FROM funding_capital_ledger WHERE request_id = ? ORDER BY created_at",
            (request_id,),
        ).fetchall()
        f_sig = [(r["entry_type"], round(float(r["amount_usd"]), 2), r["ref"]) for r in factory_rows]
        u_sig = [(r["entry_type"], round(float(r["amount_usd"]), 2), r["ref"]) for r in funding_rows]
        matched = f_sig == u_sig
        factory_total = round(sum(float(r["amount_usd"]) for r in factory_rows), 2)
        funding_total = round(sum(float(r["amount_usd"]) for r in funding_rows), 2)
        detail = "matched" if matched else "LEDGER_MISMATCH: funding flow halted pending owner review"
        rec_id = f"rec-{uuid.uuid4().hex[:16]}"
        conn.execute(
            """
            INSERT INTO funding_reconciliations
            (id, request_id, workspace_id, factory_total_usd, funding_total_usd, matched, detail, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                rec_id, request_id, request["workspace_id"], factory_total,
                funding_total, 1 if matched else 0, detail, time.time(),
            ),
        )
        conn.commit()
    return {
        "id": rec_id,
        "request_id": request_id,
        "workspace_id": request["workspace_id"],
        "factory_total_usd": factory_total,
        "funding_total_usd": funding_total,
        "matched": matched,
        "detail": detail,
        "halted": not matched,
    }


def list_requests(*, workspace_id: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
    lim = max(1, min(int(limit), 500))
    with _connect() as conn:
        if workspace_id:
            rows = conn.execute(
                "SELECT * FROM funding_requests WHERE workspace_id = ? ORDER BY created_at DESC LIMIT ?",
                (workspace_id, lim),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM funding_requests ORDER BY created_at DESC LIMIT ?",
                (lim,),
            ).fetchall()
    return [_row(row) or {} for row in rows]


def get_request(request_id: str) -> dict[str, Any] | None:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM funding_requests WHERE id = ?", (request_id,)).fetchone()
    return _row(row)


def capital_route_events(*, workspace_id: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
    lim = max(1, min(int(limit), 500))
    with _connect() as conn:
        if workspace_id:
            rows = conn.execute(
                "SELECT * FROM capital_route_events WHERE workspace_id = ? ORDER BY created_at DESC LIMIT ?",
                (workspace_id, lim),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM capital_route_events ORDER BY created_at DESC LIMIT ?",
                (lim,),
            ).fetchall()
    out: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        try:
            item["restrictions"] = json.loads(item.pop("restrictions_json") or "[]")
        except Exception:
            item["restrictions"] = []
        out.append(item)
    return out


def funding_status_summary(*, workspace_id: str | None = None) -> dict[str, Any]:
    requests = list_requests(workspace_id=workspace_id, limit=500)
    counts: dict[str, int] = {}
    for req in requests:
        counts[str(req.get("status") or "unknown")] = counts.get(str(req.get("status") or "unknown"), 0) + 1
    pending_owner = [r for r in requests if r.get("status") == "owner_approval_required"]
    pending_verification = [r for r in requests if r.get("status") == "verification_required"]
    latest_routes = capital_route_events(workspace_id=workspace_id, limit=20)
    budgets = list_preapproved_budgets(workspace_id=workspace_id)
    opportunities = list_funding_opportunities(workspace_id=workspace_id, limit=100)
    opportunity_counts: dict[str, int] = {}
    for opportunity in opportunities:
        state = str(opportunity.get("status") or "unknown")
        opportunity_counts[state] = opportunity_counts.get(state, 0) + 1
    return {
        "request_count": len(requests),
        "status_counts": counts,
        "owner_approval_count": len(pending_owner),
        "owner_approval_requests": pending_owner[:20],
        "verification_required_count": len(pending_verification),
        "verification_requests": pending_verification[:20],
        "capital_routes": latest_routes,
        "preapproved_budgets": budgets,
        "funding_opportunities": opportunities,
        "opportunity_status_counts": opportunity_counts,
        "opportunity_lifecycle": list(FUNDING_OPPORTUNITY_STATES),
        "approval_bands": {
            "0_99": "auto only inside a preapproved budget; otherwise enhanced verification",
            "100_999": "enhanced Funding Utility verification + owner notification",
            "1000_4999": "explicit owner approval",
            "5000_plus": "owner-only approval + full capital decision card and independent audit",
        },
        "ai_financial_authority": "request_only",
    }
