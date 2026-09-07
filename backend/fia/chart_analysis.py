import base64
import json
import os
from typing import Any, Dict

import httpx


OPENAI_URL = "https://api.openai.com/v1/responses"
OPENAI_MODEL = os.getenv("OPENAI_VISION_MODEL", "gpt-5.6-luna")


VISION_INSTRUCTIONS = """
You are the Vision Chart Analyst inside CLEAR NASDAQ FIA.

Analyze the uploaded NASDAQ/NQ/NAS100 trading chart independently.

IMPORTANT:
- Do not blindly agree with the user's analysis.
- Do not invent prices or levels that cannot be read from the chart.
- Separate observations from inference.
- If the chart is unclear, say so.
- This is chart/technical analysis only. Do not pretend the image contains news,
  macro or fundamental information that is not visible.
- Produce structured JSON only.

Analyze:
1. instrument
2. timeframe visible on chart
3. directional bias: BULLISH, BEARISH, or NEUTRAL
4. bullish probability from 0 to 100
5. bearish probability from 0 to 100
6. confidence from 0 to 100
7. market structure
8. trend
9. momentum
10. support levels that are actually visible
11. resistance levels that are actually visible
12. liquidity / obvious highs and lows if visible
13. breakout or breakdown evidence
14. invalidation condition
15. key observations
16. concise thesis

Return exactly this JSON shape:

{
  "instrument": "...",
  "timeframe": "...",
  "direction": "BULLISH|BEARISH|NEUTRAL",
  "bullish_probability": 0,
  "bearish_probability": 0,
  "confidence": 0,
  "market_structure": "...",
  "trend": "...",
  "momentum": "...",
  "support_levels": [],
  "resistance_levels": [],
  "liquidity_levels": [],
  "breakout_breakdown": "...",
  "invalidation": "...",
  "key_observations": [],
  "thesis": "..."
}
"""



# PHASE25_CHART_CONFLUENCE_V1
PHASE25_CONFLUENCE_INSTRUCTIONS = """
PHASE 25 — CHART CONFLUENCE EXTRACTION

In addition to the existing chart-analysis fields, inspect ONLY what is visibly
supported and add these fields to the returned JSON. Use null or [] when a
feature cannot be confirmed; never invent it.

"htf_poi": null or {"type":"supply|demand|other","direction":"BULLISH|BEARISH","note":"..."},
"order_blocks": [],
"fair_value_gaps": [],
"liquidity_sweeps": [],
"smt": null or {"detected":true,"direction":"BULLISH|BEARISH","pair":"...","note":"..."},
"session_context": null or {"session":"ASIA|LONDON|NEW_YORK|OTHER","direction":"BULLISH|BEARISH","note":"..."},
"execution_confirmation": null or {"timeframe":"1m|5m|other","direction":"BULLISH|BEARISH","note":"..."}

For liquidity_sweeps, describe which side was swept and whether price visibly
reclaimed/rejected afterward. Do not label an Order Block, FVG, SMT, or sweep
unless the chart actually supports it.
"""

def _extract_output_text(payload: Dict[str, Any]) -> str:
    if payload.get("output_text"):
        return payload["output_text"]

    parts = []

    for item in payload.get("output", []):
        for content in item.get("content", []):
            if content.get("type") in ("output_text", "text"):
                text = content.get("text")
                if text:
                    parts.append(text)

    return "\n".join(parts).strip()


def _clean_json(text: str) -> Dict[str, Any]:
    text = text.strip()

    if text.startswith("```"):
        lines = text.splitlines()

        if lines and lines[0].startswith("```"):
            lines = lines[1:]

        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]

        text = "\n".join(lines).strip()

        if text.startswith("json"):
            text = text[4:].strip()

    return json.loads(text)


async def analyze_chart(
    image_bytes: bytes,
    filename: str,
    content_type: str,
    user_analysis: str = "",
    user_direction: str = "",
    timeframe: str = "",
) -> Dict[str, Any]:

    api_key = os.getenv("GEMINI_API_KEY")

    if not api_key:
        raise RuntimeError(
            "GEMINI_API_KEY is missing from backend/.env"
        )

    if not image_bytes:
        raise ValueError("Empty chart image.")

    if content_type not in ("image/png", "image/jpeg", "image/webp"):
        raise ValueError(
            "Unsupported chart format. Use PNG, JPEG or WEBP."
        )

    user_context = f"""
USER PROVIDED INFORMATION

User direction:
{user_direction or "Not provided"}

User timeframe:
{timeframe or "Not provided"}

User reasoning:
{user_analysis or "Not provided"}

The user's information is context only.

Independently inspect the chart and identify where the user's view
agrees or conflicts with what is visibly present.
"""

    from google import genai
    from google.genai import types

    client = genai.Client(api_key=api_key)

    prompt = f"""
{VISION_INSTRUCTIONS}

{PHASE25_CONFLUENCE_INSTRUCTIONS}

{user_context}

Return ONLY valid JSON.
"""

    response = await client.aio.models.generate_content(
        model=os.getenv("GEMINI_VISION_MODEL", "gemini-3.6-flash"),
        contents=[
            types.Part.from_bytes(
                data=image_bytes,
                mime_type=content_type,
            ),
            prompt,
        ],
    )

    text = response.text

    if not text:
        raise RuntimeError("Gemini Vision returned no text.")

    analysis = _clean_json(text)

    analysis["provider"] = "Gemini Vision"
    analysis["model"] = os.getenv(
        "GEMINI_VISION_MODEL",
        "gemini-3.6-flash",
    )
    analysis["filename"] = filename
    analysis["image_interpreted"] = True

    return analysis


def compare_chart_with_fia(
    chart_analysis: Dict[str, Any],
    fia: Dict[str, Any],
) -> Dict[str, Any]:

    chart_direction = str(
        chart_analysis.get("direction", "NEUTRAL")
    ).upper()

    fia_direction = str(
        fia.get("direction", "NEUTRAL")
    ).upper()

    def _prob(value):
        try:
            if value is None or isinstance(value, bool) or (isinstance(value, str) and not value.strip()): return None
            x=float(value)
            return x if 0.0 <= x <= 100.0 else None
        except (TypeError, ValueError): return None

    chart_probability = _prob(chart_analysis.get("bullish_probability"))
    fia_probability = _prob(fia.get("bullish_probability"))

    direction_match = chart_direction == fia_direction
    probability_gap = (round(abs(chart_probability - fia_probability),2)
                       if chart_probability is not None and fia_probability is not None else None)

    if not direction_match:
        agreement = "CONFLICT"
    elif probability_gap is None:
        agreement = "DIRECTION_ONLY"
    elif probability_gap <= 10:
        agreement = "HIGH"
    elif probability_gap <= 20:
        agreement = "MODERATE"
    else:
        agreement = "LOW"

    return {
        "chart_direction": chart_direction,
        "fia_direction": fia_direction,
        "direction_match": direction_match,
        "chart_bullish_probability": chart_probability,
        "fia_bullish_probability": fia_probability,
        "probability_gap": probability_gap,
        "agreement": agreement,
        "note": (
            "This is a present-time comparison. "
            "It does not determine which forecast is correct. "
            "Final correctness must be measured against the actual "
            "market outcome after the forecast horizon."
        ),
    }

def compare_with_fia(fia: dict, user_analysis: dict) -> dict:
    """
    Compare the user's structured chart analysis with FIA's forecast.

    This is an alignment check only. It does not determine which
    forecast is actually correct until the forecast horizon completes.
    """

    fia_direction = str(fia.get("direction", "NEUTRAL")).upper()
    user_direction = str(
        user_analysis.get("direction", "NEUTRAL")
    ).upper()

    direction_alignment = (
        "AGREE"
        if fia_direction == user_direction
        else "DISAGREE"
    )

    # Probability comparison is allowed only when both sides explicitly supply
    # a valid probability. Confidence is not silently reinterpreted as probability.
    def explicit_bullish_probability(data: dict):
        try:
            v=data.get("bullish_probability")
            if v is None or isinstance(v,bool) or (isinstance(v,str) and not v.strip()): return None
            x=float(v)
            return round(x,2) if 0.0 <= x <= 100.0 else None
        except (TypeError,ValueError): return None

    fia_probability = explicit_bullish_probability(fia)
    user_probability = explicit_bullish_probability(user_analysis)
    probability_gap = (round(abs(fia_probability-user_probability),2)
                       if fia_probability is not None and user_probability is not None else None)

    if probability_gap is None:
        comparison_score = 100.0 if direction_alignment == "AGREE" else 0.0
        score_scope = "DIRECTION_ONLY_PROBABILITY_UNAVAILABLE"
    elif direction_alignment == "AGREE":
        comparison_score = round(max(0.0,100.0-probability_gap),2)
        score_scope = "DIRECTION_AND_EXPLICIT_PROBABILITY"
    else:
        comparison_score = round(max(0.0,50.0-probability_gap/2.0),2)
        score_scope = "DIRECTION_AND_EXPLICIT_PROBABILITY"

    return {
        "direction_alignment": direction_alignment,
        "fia_direction": fia_direction,
        "user_direction": user_direction,
        "fia_bullish_probability": fia_probability,
        "user_bullish_probability_estimate": user_probability,
        "probability_gap": probability_gap,
        "comparison_score": comparison_score,
        "comparison_score_scope": score_scope,
        "note": (
            "This is a present-time comparison. "
            "It does NOT determine which analysis is actually "
            "correct until the forecast horizon has completed "
            "and the market outcome is measured."
        ),
    }
