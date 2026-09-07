from typing import Any, Dict


REQUIRED_SIGNAL_FIELDS = (
    "nq_structure",
    "liquidity_evidence_available",
    "mega_cap",
    "semis",
    "breadth",
    "macro",
)


def data_quality_score(data: Dict[str, Any]) -> float:
    """Simple transparent Phase-1 coverage score, not predictive accuracy."""
    if not data:
        return 0.0

    available = 0
    for field in REQUIRED_SIGNAL_FIELDS:
        value = data.get(field)
        if value is None:
            continue
        if field == "liquidity_evidence_available" and value is False:
            continue
        available += 1

    return round(100.0 * available / len(REQUIRED_SIGNAL_FIELDS), 2)


def provider_quality(data: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "quotes_available": data.get("provider_quotes_available", 0),
        "quotes_requested": data.get("provider_quotes_requested", 0),
        "candle_evidence": data.get("provider_candle_evidence", "missing"),
        "liquidity_evidence": bool(data.get("liquidity_evidence_available")),
        "macro_status": data.get("macro_status"),
    }
