from __future__ import annotations
from typing import Any, Dict, List, Tuple, Set

VALID_DIRECTIONS = {"BULLISH", "BEARISH", "NEUTRAL", "NO_EDGE"}

REQUIRED_KEYS = {
    "direction",
    "bullish_probability",
    "bearish_probability",
    "confidence",
    "thesis",
    "evidence_ids",
    "counter_evidence_ids",
    "unknowns",
    "failure_conditions",
}

def _num(x: Any) -> float:
    if isinstance(x, bool):
        raise ValueError("boolean is not numeric")
    v = float(x)
    if v != v or v in (float("inf"), float("-inf")):
        raise ValueError("non-finite numeric")
    return v

def validate_analysis(obj: Any, valid_evidence_ids: Set[str]) -> Tuple[bool, List[str], Dict[str, Any]]:
    errors: List[str] = []
    if not isinstance(obj, dict):
        return False, ["output is not an object"], {}

    missing = REQUIRED_KEYS - set(obj)
    if missing:
        errors.append("missing keys: " + ", ".join(sorted(missing)))

    extra=set(obj)-REQUIRED_KEYS
    if extra: errors.append("unknown keys: "+", ".join(sorted(map(str,extra))))
    # Closed-world sanitization: rejected material is never preserved in the
    # returned cleaned object, even when a caller inspects validation errors.
    out = {k: obj[k] for k in obj if k in REQUIRED_KEYS}
    direction = str(out.get("direction", "")).upper().strip()
    if direction not in VALID_DIRECTIONS:
        errors.append(f"invalid direction: {direction!r}")
    out["direction"] = direction

    try:
        bp = _num(out.get("bullish_probability"))
        sp = _num(out.get("bearish_probability"))
        conf = _num(out.get("confidence"))
        if not 0 <= bp <= 100:
            errors.append("bullish_probability outside [0,100]")
        if not 0 <= sp <= 100:
            errors.append("bearish_probability outside [0,100]")
        total = bp + sp
        drift = abs(total - 100.0)
        # Local models can emit harmless rounding drift (e.g. 61 + 38 = 99).
        # Repair ONLY small drift while preserving the bullish/bearish ratio.
        # Material inconsistency still fails closed.
        if drift <= 2.0 and total > 0 and 0 <= bp <= 100 and 0 <= sp <= 100:
            if drift > 0.01:
                bp = (bp / total) * 100.0
                sp = 100.0 - bp
        else:
            errors.append("probabilities do not sum to 100")
        if not 0 <= conf <= 100:
            errors.append("confidence outside [0,100]")
        out["bullish_probability"] = round(bp, 2)
        out["bearish_probability"] = round(sp, 2)
        out["confidence"] = round(conf, 2)
    except Exception as e:
        errors.append(f"invalid numeric field: {e}")

    for k in ("evidence_ids", "counter_evidence_ids", "unknowns", "failure_conditions"):
        if not isinstance(out.get(k), list):
            errors.append(f"{k} must be a list")
            out[k] = []

    used = []
    for k in ("evidence_ids", "counter_evidence_ids"):
        for eid in out.get(k, []):
            eid = str(eid)
            used.append(eid)
            if eid not in valid_evidence_ids:
                errors.append(f"unknown evidence id: {eid}")

    # Directional forecasts must cite at least one valid prediction-time evidence item.
    if direction in {"BULLISH","BEARISH"}:
        refs=[str(e) for e in out.get("evidence_ids",[]) if str(e) in valid_evidence_ids]
        if not refs:
            errors.append("directional analysis requires at least one valid evidence_id")

    thesis = out.get("thesis")
    if not isinstance(thesis, str) or not thesis.strip():
        errors.append("thesis must be non-empty string")
    elif len(thesis) > 3000:
        errors.append("thesis too long")

    # This brain is not allowed to output execution instructions.
    forbidden = ("place order", "execute trade", "broker order", "guaranteed profit")
    t = str(thesis or "").lower()
    if any(x in t for x in forbidden):
        errors.append("execution/guarantee language forbidden")

    return not errors, errors, out
