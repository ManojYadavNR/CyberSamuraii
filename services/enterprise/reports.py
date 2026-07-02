"""Enterprise case and investigation reports."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from services.enterprise.cases import get_case, list_case_investigations
from services.enterprise.evidence_governance import list_evidence
from services.enterprise.workspace import list_comments, list_notes, list_pins, list_tasks


def generate_case_report(case_id: str, *, format: str = "json") -> dict[str, Any]:
    case = get_case(case_id)
    if not case:
        return {}
    investigations = list_case_investigations(case_id)
    evidence = list_evidence(case_id)
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "case": case,
        "investigations": investigations,
        "evidence_chain": evidence,
        "notes": list_notes(case_id),
        "comments": list_comments(case_id),
        "tasks": list_tasks(case_id),
        "pinned_findings": list_pins(case_id),
    }
    if format == "html":
        html = _case_html(payload)
        return {"format": "html", "content": html, "filename": f"{case['case_number']}_report.html"}
    if format == "docx":
        return {"format": "docx", "content": _case_docx_text(payload), "filename": f"{case['case_number']}_report.docx"}
    return {"format": "json", "content": payload, "filename": f"{case['case_number']}_report.json"}


def _case_html(data: dict) -> str:
    case = data["case"]
    rows = "".join(f"<tr><td>{e['evidence_id'][:8]}</td><td>{e['sha256'][:16]}…</td><td>{e['source']}</td></tr>" for e in data["evidence_chain"])
    return f"""<!DOCTYPE html><html><head><meta charset="utf-8"><title>{case['case_number']}</title>
<style>body{{font-family:system-ui;background:#0f172a;color:#e2e8f0;padding:2rem}}table{{border-collapse:collapse;width:100%}}td,th{{border:1px solid #334155;padding:8px}}</style></head>
<body><h1>Case Report — {case['case_number']}</h1><p><b>{case['title']}</b> — {case['status']} / {case['priority']}</p>
<p>{case.get('description','')}</p><h2>Investigations ({len(data['investigations'])})</h2>
<ul>{''.join(f"<li>{i.get('query','')}</li>" for i in data['investigations'])}</ul>
<h2>Evidence Chain</h2><table><tr><th>ID</th><th>SHA256</th><th>Source</th></tr>{rows}</table>
<p><small>Generated {data['generated_at']}</small></p></body></html>"""


def _case_docx_text(data: dict) -> str:
    """Minimal plain-text DOCX-friendly export (opened as .docx via frontend blob)."""
    return json.dumps(data, indent=2, default=str)
