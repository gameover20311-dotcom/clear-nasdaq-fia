"""Research-only JSON/Markdown/HTML reporting for SIMONS SHADOW LAB V2 HYBRID."""
from __future__ import annotations

import html
from typing import Any, Dict, Sequence

from .causal_discovery import state_distribution, state_transition_candidates
from .research_metrics import full_research_diagnostic


def build_snapshot_report(rows: Sequence[Dict[str, Any]], snapshot_id: str) -> Dict[str, Any]:
    return {
        "lab_version": "SIMONS_SHADOW_LAB_V2_HYBRID",
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
        "lock_time_structural_barrier": True,
        "state_transition_research_is_descriptive": True,
        "automatic_strategy_selection": False,
        "automatic_production_promotion": False,
        "predictive_edge_proven": False,
        "profitability_proven": False,
        "scientific_status": "DISCOVERY_ONLY_NOT_PROVEN",
        "warning": "Research instrument only. No live signal, entry, sizing, or production authorization is produced by this report.",
    }


def render_markdown(report: Dict[str, Any]) -> str:
    lines = [
        "# SIMONS SHADOW LAB V2 HYBRID — Research Report",
        "",
        f"- Snapshot: `{report.get('snapshot_id')}`",
        f"- Rows: **{report.get('row_count', 0)}**",
        "- Predictive edge: **NOT PROVEN**",
        "- Profitability: **NOT PROVEN**",
        "- Automatic strategy selection: **DISABLED**",
        "- Automatic production promotion: **DISABLED**",
        "- Lock-time structural leakage barrier: **ENABLED**",
        "",
    ]
    for key, label in (("h8", "8H PRIMARY"), ("h4", "4H SECONDARY")):
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
    lines.extend([
        "State-transition analysis is descriptive discovery, not untouched forward validation.",
        "",
        "This report is research evidence only. It contains no live signal, entry, position sizing, or authorization to change production.",
    ])
    return "\n".join(lines)


def render_html(report: Dict[str, Any]) -> str:
    def cell(horizon: str, label: str) -> str:
        diag = ((report.get(horizon) or {}).get("diagnostic") or {})
        cal = diag.get("calibration") or {}
        return f"""<section class='card'><h2>{label}</h2><div class='big'>N={html.escape(str(cal.get('n', 0)))}</div><p>Brier: {html.escape(str(cal.get('brier_score')))}</p><p>Log loss: {html.escape(str(cal.get('log_loss')))}</p><p>ECE: {html.escape(str(cal.get('ece')))}</p><span class='status'>NOT PROVEN</span></section>"""
    return """<!doctype html><html><head><meta charset='utf-8'><title>SIMONS SHADOW LAB V2 HYBRID</title><style>body{font-family:system-ui;background:#080a0d;color:#e8edf2;margin:0;padding:32px}.top{display:flex;justify-content:space-between;gap:24px;align-items:end}.muted{color:#87909b}.warn{border:1px solid #5d6672;border-radius:10px;padding:12px 14px;margin-top:18px}.grid{display:grid;grid-template-columns:1fr 1fr;gap:18px;margin-top:22px}.card{background:#10141a;border:1px solid #252c35;border-radius:14px;padding:22px}.big{font-size:32px;font-weight:700}.status{display:inline-block;margin-top:10px;padding:6px 10px;border:1px solid #5d6672;border-radius:999px;font-size:12px}@media(max-width:700px){.grid{grid-template-columns:1fr}}</style></head><body>""" + f"<div class='top'><div><h1>SIMONS SHADOW LAB V2 HYBRID</h1><div class='muted'>Snapshot {html.escape(str(report.get('snapshot_id')))} · Research instrument</div></div><strong>EDGE: NOT PROVEN</strong></div><div class='warn'>No live signal, entry, sizing, or production authorization. Lock-time leakage barrier enabled. Automatic promotion disabled.</div><div class='grid'>" + cell("h8", "8H PRIMARY") + cell("h4", "4H SECONDARY") + "</div><p class='muted'>State transitions are descriptive discovery. Historical discovery is not forward validation.</p></body></html>"
