"""Research-only JSON/Markdown/HTML reporting for SIMONS SHADOW LAB V1."""
from __future__ import annotations

import html
from typing import Any, Dict, Sequence

from .causal_discovery import state_distribution, state_transition_candidates
from .research_metrics import full_research_diagnostic


def build_snapshot_report(rows: Sequence[Dict[str, Any]], snapshot_id: str) -> Dict[str, Any]:
    return {
        "snapshot_id": snapshot_id,
        "row_count": len(rows),
        "h4": {
            "diagnostic": full_research_diagnostic(rows, 4),
            "states": state_distribution(rows, 4),
            "transitions": state_transition_candidates(rows, 4),
        },
        "h8": {
            "diagnostic": full_research_diagnostic(rows, 8),
            "states": state_distribution(rows, 8),
            "transitions": state_transition_candidates(rows, 8),
        },
        "automatic_strategy_selection": False,
        "predictive_edge_proven": False,
        "profitability_proven": False,
        "scientific_status": "DISCOVERY_ONLY_NOT_PROVEN",
    }


def render_markdown(report: Dict[str, Any]) -> str:
    lines = [
        "# SIMONS SHADOW LAB V1 — Research Report",
        "",
        f"- Snapshot: `{report.get('snapshot_id')}`",
        f"- Rows: **{report.get('row_count', 0)}**",
        "- Predictive edge: **NOT PROVEN**",
        "- Profitability: **NOT PROVEN**",
        "- Automatic strategy selection: **DISABLED**",
        "",
    ]
    for key, label in (("h8", "8H"), ("h4", "4H")):
        diag = ((report.get(key) or {}).get("diagnostic") or {})
        cal = diag.get("calibration") or {}
        lines.extend([
            f"## {label}",
            f"- Resolved N: {cal.get('n', 0)}",
            f"- Brier: {cal.get('brier_score')}",
            f"- Log loss: {cal.get('log_loss')}",
            f"- ECE: {cal.get('ece')}",
            f"- Status: `{diag.get('scientific_status', 'NOT_PROVEN')}`",
            "",
        ])
    lines.append("This report is research evidence only. Historical discovery is not forward validation.")
    return "\n".join(lines)


def render_html(report: Dict[str, Any]) -> str:
    def cell(horizon: str, label: str) -> str:
        diag = ((report.get(horizon) or {}).get("diagnostic") or {})
        cal = diag.get("calibration") or {}
        return f"""<section class='card'><h2>{label}</h2><div class='big'>N={html.escape(str(cal.get('n', 0)))}</div><p>Brier: {html.escape(str(cal.get('brier_score')))}</p><p>Log loss: {html.escape(str(cal.get('log_loss')))}</p><p>ECE: {html.escape(str(cal.get('ece')))}</p><span class='status'>NOT PROVEN</span></section>"""
    return """<!doctype html><html><head><meta charset='utf-8'><title>SIMONS SHADOW LAB V1</title><style>body{font-family:system-ui;background:#080a0d;color:#e8edf2;margin:0;padding:32px}.top{display:flex;justify-content:space-between;gap:24px;align-items:end}.muted{color:#87909b}.grid{display:grid;grid-template-columns:1fr 1fr;gap:18px;margin-top:22px}.card{background:#10141a;border:1px solid #252c35;border-radius:14px;padding:22px}.big{font-size:32px;font-weight:700}.status{display:inline-block;margin-top:10px;padding:6px 10px;border:1px solid #5d6672;border-radius:999px;font-size:12px}@media(max-width:700px){.grid{grid-template-columns:1fr}}</style></head><body>""" + f"<div class='top'><div><h1>SIMONS SHADOW LAB V1</h1><div class='muted'>Snapshot {html.escape(str(report.get('snapshot_id')))} · Research only</div></div><strong>EDGE: NOT PROVEN</strong></div><div class='grid'>" + cell("h8", "8H PRIMARY") + cell("h4", "4H SECONDARY") + "</div><p class='muted'>No automatic production promotion. Discovery data is not forward validation.</p></body></html>"
