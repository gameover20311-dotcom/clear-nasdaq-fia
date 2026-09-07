from __future__ import annotations

from typing import Any, Dict, List, Optional

from .macro_vintage import build_macro_vintage_snapshot
from .official_sources import verify_primary_event


async def execute_controlled_investigation(hub: Any, initial_report: Dict[str, Any], as_of: Any) -> Dict[str, Any]:
    """Run one bounded reinvestigation pass.

    The plan is intentionally allow-listed: deeper normalized news, official-source
    identification, and FRED/ALFRED vintages. It does not browse arbitrary sites,
    tune weights, or consult future outcome labels.
    """
    critic = initial_report.get("critic") or {}
    queue = list(critic.get("reinvestigate") or [])
    hypotheses = initial_report.get("hypotheses") or {}
    queue.extend(
        str(x.get("specialist") or "")
        for x in hypotheses.get("controlled_investigation_queue") or []
        if isinstance(x, dict)
    )
    queue = sorted({x for x in queue if x})
    result: Dict[str, Any] = {
        "triggered": bool(queue),
        "queue": queue,
        "bounded_passes": 1,
        "news_items": [],
        "macro_vintage": None,
        "primary_source_verification": None,
        "errors": [],
        "policy": "Only allow-listed providers/sources are queried; no arbitrary web browsing and no outcome-aware tuning.",
    }
    if not queue:
        return result

    if any("news" in q.lower() or "contradict" in q.lower() for q in queue):
        try:
            items = await hub.unified_news_feed(company_days=5, market_limit=100, company_limit=35)
            try:
                items = hub.apply_news_trust_scores(items)
            except Exception:
                pass
            result["news_items"] = items
            symbols = set()
            for item in items:
                if isinstance(item, dict) and item.get("symbol"):
                    symbols.add(str(item.get("symbol")).upper())
                ctx = item.get("fia_context") if isinstance(item, dict) else None
                if isinstance(ctx, dict):
                    symbols.update(str(x).upper() for x in (ctx.get("affected_symbols") or []) if x)
            if symbols:
                result["primary_source_verification"] = await verify_primary_event(sorted(symbols)[:12], as_of)
        except Exception as exc:
            result["errors"].append(f"news reinvestigation failed: {exc}")

    if any("macro" in q.lower() or "fed" in q.lower() or "yield" in q.lower() for q in queue):
        try:
            result["macro_vintage"] = await build_macro_vintage_snapshot(as_of, series=["CPI", "CORE_PCE", "PAYROLLS", "UNEMPLOYMENT", "FED_FUNDS", "US10Y"])
        except Exception as exc:
            result["errors"].append(f"macro reinvestigation failed: {exc}")
    return result
