from __future__ import annotations

import json
import os
from typing import Any, Dict


ADVANCED_CHART_PROMPT = r"""
You are the INDEPENDENT CHART INTELLIGENCE specialist inside CLEAR NASDAQ — FIA.

NON-NEGOTIABLE INDEPENDENCE RULES
- You are NOT shown the FIA forecast direction, probability, confidence, thesis, or weights.
- You are NOT shown the user's directional opinion or reasoning.
- Judge only the pixels in the uploaded chart.
- Never infer news, macro, earnings, or fundamentals from a chart image.
- Never invent a price, timeframe, session, indicator, POI, OB, FVG, SMT, sweep, CHoCH/BOS, or displacement that is not visibly supportable.
- When evidence is ambiguous, mark it unconfirmed instead of forcing a label.
- This is research analysis only; never produce broker/order instructions.

TASK
Inspect NQ / NASDAQ chart structure as a professional execution analyst. Separate high-timeframe context from lower-timeframe execution evidence where visible. Specifically inspect:
1. Instrument and visible timeframe(s)
2. Directional chart bias: BULLISH / BEARISH / NEUTRAL
3. Bullish probability and bearish probability summing to 100
4. Confidence based only on chart clarity
5. Higher-timeframe POI / supply / demand zone
6. Order blocks
7. Fair value gaps / imbalances
8. Session liquidity: Asia / London / New York highs or lows when actually visible
9. Buy-side or sell-side liquidity sweep and whether price reclaimed/rejected
10. SMT divergence only when a comparison market is actually visible
11. Market-structure shift: CHoCH / MSS / BOS
12. Displacement / impulsive confirmation
13. Lower-timeframe execution confirmation
14. Visible invalidation condition
15. Evidence conflicts and missing chart evidence

Return ONLY valid JSON with this exact top-level shape:
{
  "instrument": "...",
  "timeframes_visible": [],
  "direction": "BULLISH|BEARISH|NEUTRAL",
  "bullish_probability": 50.0,
  "bearish_probability": 50.0,
  "confidence": 0.0,
  "htf_poi": {"detected": false, "type": null, "direction": null, "note": ""},
  "order_blocks": [],
  "fair_value_gaps": [],
  "session_liquidity": [],
  "liquidity_sweep": {"detected": false, "side": null, "direction": null, "reclaim_or_rejection": null, "note": ""},
  "smt": {"detected": false, "pair": null, "direction": null, "note": ""},
  "structure_shift": {"detected": false, "type": null, "direction": null, "note": ""},
  "displacement": {"detected": false, "direction": null, "note": ""},
  "execution_confirmation": {"detected": false, "timeframe": null, "direction": null, "note": ""},
  "invalidation": "",
  "supporting_observations": [],
  "conflicting_observations": [],
  "missing_evidence": [],
  "thesis": ""
}
"""

INDEPENDENCE_POLICY = {
    "fia_direction_visible": False,
    "fia_probability_visible": False,
    "user_direction_visible": False,
    "user_reasoning_visible": False,
    "chart_pixels_only": True,
    "broker_execution": False,
}


def _clean_json(text: str) -> Dict[str, Any]:
    value = (text or "").strip()
    if value.startswith("```"):
        lines = value.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        value = "\n".join(lines).strip()
        if value.lower().startswith("json"):
            value = value[4:].strip()
    parsed = json.loads(value)
    if not isinstance(parsed, dict):
        raise ValueError("Vision response must be a JSON object")
    return parsed


def _bounded(value: Any, default: float = 0.0) -> float:
    try:
        return max(0.0, min(100.0, float(value)))
    except Exception:
        return default


def _normalize_analysis(raw: Dict[str, Any]) -> Dict[str, Any]:
    result = dict(raw or {})
    direction = str(result.get("direction") or "").upper()
    if direction not in {"BULLISH", "BEARISH", "NEUTRAL"}:
        raise ValueError("Vision direction missing/invalid")
    def required_pct(key: str) -> float:
        value=result.get(key)
        if value is None or isinstance(value,bool) or (isinstance(value,str) and not value.strip()):
            raise ValueError(f"Vision {key} missing")
        try: x=float(value)
        except (TypeError,ValueError) as exc: raise ValueError(f"Vision {key} invalid") from exc
        if not 0.0 <= x <= 100.0: raise ValueError(f"Vision {key} outside [0,100]")
        return x
    bull=required_pct("bullish_probability"); bear=required_pct("bearish_probability"); confidence=required_pct("confidence")
    total=bull+bear
    if abs(total-100.0)>1.0:
        raise ValueError(f"Vision probabilities must sum to 100 (got {total:.3f})")
    if total<=0: raise ValueError("Vision probability total invalid")
    # Only repair <=1pp rounding drift; material contradictions fail closed.
    bull=bull/total*100.0; bear=100.0-bull
    result["direction"] = direction
    result["bullish_probability"] = round(bull, 1)
    result["bearish_probability"] = round(bear, 1)
    result["confidence"] = round(confidence, 1)
    for key in ("order_blocks", "fair_value_gaps", "session_liquidity", "supporting_observations", "conflicting_observations", "missing_evidence"):
        if not isinstance(result.get(key), list):
            result[key] = []
    for key in ("htf_poi", "liquidity_sweep", "smt", "structure_shift", "displacement", "execution_confirmation"):
        if not isinstance(result.get(key), dict):
            result[key] = {"detected": False}
        result[key].setdefault("detected", False)
    result["independence_policy"] = dict(INDEPENDENCE_POLICY)
    result["research_only"] = True
    result["broker_execution"] = False
    return result


async def analyze_advanced_chart_independent(
    image_bytes: bytes,
    filename: str,
    content_type: str,
) -> Dict[str, Any]:
    if not image_bytes:
        raise ValueError("Empty chart image")
    if content_type not in {"image/png", "image/jpeg", "image/webp"}:
        raise ValueError("Unsupported chart format. Use PNG, JPEG or WEBP")

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is missing from backend/.env")

    # Import lazily so normal FIA startup/tests do not require a network call.
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=api_key)
    response = await client.aio.models.generate_content(
        model=os.getenv("GEMINI_VISION_MODEL", "gemini-3.6-flash"),
        contents=[
            types.Part.from_bytes(data=image_bytes, mime_type=content_type),
            ADVANCED_CHART_PROMPT,
        ],
    )
    text = getattr(response, "text", None)
    if not text:
        raise RuntimeError("Vision provider returned no text")

    result = _normalize_analysis(_clean_json(text))
    result["provider"] = "Gemini Vision"
    result["model"] = os.getenv("GEMINI_VISION_MODEL", "gemini-3.6-flash")
    result["filename"] = filename
    result["image_interpreted"] = True
    result["module"] = "PHASE 31 — Independent A++ Chart Intelligence"
    return result
