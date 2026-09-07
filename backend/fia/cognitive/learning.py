from __future__ import annotations

from collections import Counter
from typing import Any, Dict, Iterable, List

from .utils import as_float, truthy


def classify_error(row: Dict[str,Any], horizon: str = "8h") -> str:
    actual=str(row.get(f"actual_{horizon}") or "").upper()
    predicted=str(row.get("cognitive_direction") or row.get("predicted") or "").upper()
    if actual not in {"BULLISH","BEARISH"} or predicted not in {"BULLISH","BEARISH"}:
        return "unresolved_or_invalid"
    if actual==predicted:
        return "correct"
    coverage=as_float(row.get("data_coverage"),1.0) or 0.0
    critic=str(row.get("critic_severity") or "").upper()
    regime=str(row.get("cognitive_regime") or row.get("regime") or "").upper()
    macro=str(row.get("macro_source_status") or "").lower()
    if coverage<.75: return "missing_or_stale_data"
    if "missing" in macro or "unavailable" in macro:
        if regime=="MACRO_EVENT": return "macro_context_missing"
    if critic in {"HIGH","CRITICAL"}: return "ignored_contradiction_or_overconfidence"
    raw=as_float(row.get("raw_probability_8h") or row.get("bullish_probability"),50.0) or 50.0
    cal=as_float(row.get("calibrated_probability_8h"),raw) or raw
    if abs(cal-50)>=20: return "overconfidence"
    chart=str(row.get("chart_data_status") or "").lower()
    if "missing" in chart: return "chart_or_liquidity_context_missing"
    return "valid_evidence_market_moved_opposite"


def mistake_attribution(rows: Iterable[Dict[str,Any]], horizon: str = "8h") -> Dict[str,Any]:
    counts=Counter()
    examples={}
    for row in rows:
        label=classify_error(row,horizon)
        counts[label]+=1
        if label not in examples and label!="correct":
            examples[label]={"timestamp":row.get("timestamp"),"predicted":row.get("cognitive_direction") or row.get("predicted"),"actual":row.get(f"actual_{horizon}")}
    errors=sum(v for k,v in counts.items() if k not in {"correct","unresolved_or_invalid"})
    return {"horizon":horizon,"counts":dict(counts),"errors":errors,"examples":examples,
            "policy":"Mistakes are attributed first. No live weight is changed unless a development hypothesis improves untouched out-of-sample validation."}
