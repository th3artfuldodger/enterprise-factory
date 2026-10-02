"""Unified Empire evidence/funding report generation.

Uses a tiny dependency-free PDF writer so report export works in the hardened
runtime without adding a document engine to the attack/dependency surface.
"""
from __future__ import annotations

import json
import textwrap
import time
from typing import Any


def build_empire_report(
    product: dict[str, Any],
    *,
    funding_requests: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "report_version": 1,
        "generated_at": time.time(),
        "product": {
            "id": product.get("id"),
            "idea": product.get("idea"),
            "state": product.get("state"),
            "department": product.get("empire_department") or product.get("category"),
        },
        "research_packet": product.get("empire_research_packet") or {},
        "primary_risk": product.get("empire_primary_risk") or {},
        "department_manager_review": product.get("empire_manager_review") or {},
        "ultron_audit": product.get("ultron_audit") or {},
        "decision_package": product.get("empire_decision_package") or {},
        "funding_requests": list(funding_requests or []),
    }


def _ascii(value: Any) -> str:
    text = str(value if value is not None else "")
    return text.encode("ascii", "replace").decode("ascii")


def _flat_lines(report: dict[str, Any]) -> list[str]:
    product = report.get("product") or {}
    lines = [
        "TRIMBLE ENTERPRISE - EMPIRE DECISION REPORT",
        "",
        f"Product: {product.get('id') or '-'}",
        f"Department: {product.get('department') or '-'}",
        f"State: {product.get('state') or '-'}",
        "",
        "MISSION",
        str(product.get("idea") or "-"),
        "",
        "FIVE-LENS RESEARCH",
    ]
    research = report.get("research_packet") or {}
    for lens in ("need", "money", "competition", "ai_advantage", "feasibility"):
        section = research.get(lens) or {}
        lines.append(f"{lens.replace('_', ' ').upper()}:")
        result = section.get("result") if isinstance(section, dict) else section
        if isinstance(result, (dict, list)):
            result = json.dumps(result, sort_keys=True, default=str)
        lines.append(str(result or "No completed result recorded."))
        lines.append("")

    lines.extend([
        "PRIMARY RISK",
        json.dumps(report.get("primary_risk") or {}, sort_keys=True, default=str),
        "",
        "DEPARTMENT MANAGER REVIEW",
        json.dumps(report.get("department_manager_review") or {}, sort_keys=True, default=str),
        "",
        "ULTRON INDEPENDENT REVIEW",
        json.dumps(report.get("ultron_audit") or {}, sort_keys=True, default=str),
        "",
        "CONSOLIDATED DECISION PACKAGE",
        json.dumps(report.get("decision_package") or {}, sort_keys=True, default=str),
        "",
        "FUNDING UTILITY",
    ])
    funding = report.get("funding_requests") or []
    if not funding:
        lines.append("No funding requests linked to this mission.")
    for request in funding:
        lines.extend([
            f"Request {request.get('id')}: USD {float(request.get('amount_usd') or 0):,.2f}",
            f"Band: {request.get('band')} | Status: {request.get('status')}",
            f"Purpose: {request.get('purpose') or '-'}",
            f"Restrictions: {', '.join(request.get('restrictions') or []) or 'none'}",
            f"Owner decision: {request.get('owner_decision') or 'not recorded'}",
            "",
        ])
    return lines


def _pdf_escape(text: str) -> str:
    return _ascii(text).replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def render_empire_report_pdf(report: dict[str, Any]) -> bytes:
    """Render a readable text PDF using built-in PDF Helvetica."""
    wrapped: list[str] = []
    for line in _flat_lines(report):
        if not line:
            wrapped.append("")
            continue
        wrapped.extend(textwrap.wrap(_ascii(line), width=92, break_long_words=True) or [""])

    lines_per_page = 54
    pages = [wrapped[i : i + lines_per_page] for i in range(0, len(wrapped), lines_per_page)] or [[]]
    page_ids = [4 + i * 2 for i in range(len(pages))]
    content_ids = [pid + 1 for pid in page_ids]
    max_obj = content_ids[-1]

    objects: dict[int, bytes] = {
        1: b"<< /Type /Catalog /Pages 2 0 R >>",
        2: (
            f"<< /Type /Pages /Kids [{' '.join(f'{pid} 0 R' for pid in page_ids)}] "
            f"/Count {len(page_ids)} >>"
        ).encode("ascii"),
        3: b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    }
    for index, page_lines in enumerate(pages):
        pid = page_ids[index]
        cid = content_ids[index]
        content_parts = ["BT", "/F1 9 Tf", "48 748 Td", "12 TL"]
        for line in page_lines:
            content_parts.append(f"({_pdf_escape(line)}) Tj")
            content_parts.append("T*")
        content_parts.append("ET")
        stream = "\n".join(content_parts).encode("ascii", "replace")
        objects[pid] = (
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            f"/Resources << /Font << /F1 3 0 R >> >> /Contents {cid} 0 R >>"
        ).encode("ascii")
        objects[cid] = b"<< /Length " + str(len(stream)).encode("ascii") + b" >>\nstream\n" + stream + b"\nendstream"

    output = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0] * (max_obj + 1)
    for obj_id in range(1, max_obj + 1):
        offsets[obj_id] = len(output)
        output.extend(f"{obj_id} 0 obj\n".encode("ascii"))
        output.extend(objects[obj_id])
        output.extend(b"\nendobj\n")
    xref = len(output)
    output.extend(f"xref\n0 {max_obj + 1}\n".encode("ascii"))
    output.extend(b"0000000000 65535 f \n")
    for obj_id in range(1, max_obj + 1):
        output.extend(f"{offsets[obj_id]:010d} 00000 n \n".encode("ascii"))
    output.extend(
        (
            f"trailer\n<< /Size {max_obj + 1} /Root 1 0 R >>\n"
            f"startxref\n{xref}\n%%EOF\n"
        ).encode("ascii")
    )
    return bytes(output)
