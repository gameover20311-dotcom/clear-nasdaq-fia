from __future__ import annotations

ANALYSIS_SCHEMA = {
    "type": "object",
    "properties": {
        "direction": {"type": "string", "enum": ["BULLISH", "BEARISH", "NEUTRAL", "NO_EDGE"]},
        "bullish_probability": {"type": "number", "minimum": 0, "maximum": 100},
        "bearish_probability": {"type": "number", "minimum": 0, "maximum": 100},
        "confidence": {"type": "number", "minimum": 0, "maximum": 100},
        "thesis": {"type": "string"},
        "evidence_ids": {"type": "array", "items": {"type": "string"}},
        "counter_evidence_ids": {"type": "array", "items": {"type": "string"}},
        "unknowns": {"type": "array", "items": {"type": "string"}},
        "failure_conditions": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "direction", "bullish_probability", "bearish_probability", "confidence",
        "thesis", "evidence_ids", "counter_evidence_ids", "unknowns", "failure_conditions"
    ],
    "additionalProperties": False,
}

CAUSAL_SCHEMA = {
    "type": "object",
    "properties": {
        "chains": {
            "type": "array",
            "maxItems": 12,
            "items": {
                "type": "object",
                "properties": {
                    "driver": {"type": "string"},
                    "transmission": {"type": "string"},
                    "polarity": {"type": "string", "enum": ["BULLISH_NQ", "BEARISH_NQ", "MIXED", "UNKNOWN"]},
                    "strength": {"type": "number", "minimum": 0, "maximum": 100},
                    "evidence_ids": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["driver", "transmission", "polarity", "strength", "evidence_ids"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["chains"],
    "additionalProperties": False,
}

HYPOTHESIS_SCHEMA = {
    "type": "object",
    "properties": {
        "hypotheses": {
            "type": "array",
            "minItems": 2,
            "maxItems": 8,
            "items": {
                "type": "object",
                "properties": {
                    "hypothesis_id": {"type": "string"},
                    "claim": {"type": "string"},
                    "polarity": {"type": "string", "enum": ["BULLISH_NQ", "BEARISH_NQ", "MIXED", "UNKNOWN"]},
                    "confidence": {"type": "number", "minimum": 0, "maximum": 100},
                    "evidence_for": {"type": "array", "items": {"type": "string"}},
                    "evidence_against": {"type": "array", "items": {"type": "string"}},
                    "activation_conditions": {"type": "array", "items": {"type": "string"}},
                    "invalidation_conditions": {"type": "array", "items": {"type": "string"}},
                },
                "required": [
                    "hypothesis_id", "claim", "polarity", "confidence", "evidence_for",
                    "evidence_against", "activation_conditions", "invalidation_conditions"
                ],
                "additionalProperties": False,
            },
        }
    },
    "required": ["hypotheses"],
    "additionalProperties": False,
}

SCENARIO_SCHEMA = {
    "type": "object",
    "properties": {
        "worlds": {
            "type": "array",
            "minItems": 3,
            "maxItems": 3,
            "items": {
                "type": "object",
                "properties": {
                    "kind": {"type": "string", "enum": ["BULL", "BASE", "BEAR"]},
                    "probability": {"type": "number", "minimum": 0, "maximum": 100},
                    "narrative": {"type": "string"},
                    "activation_conditions": {"type": "array", "items": {"type": "string"}},
                    "break_conditions": {"type": "array", "items": {"type": "string"}},
                    "evidence_ids": {"type": "array", "items": {"type": "string"}},
                },
                "required": [
                    "kind", "probability", "narrative",
                    "activation_conditions", "break_conditions", "evidence_ids"
                ],
                "additionalProperties": False,
            },
        }
    },
    "required": ["worlds"],
    "additionalProperties": False,
}

JUDGE_SCHEMA = {
    "type": "object",
    "properties": {
        "grounding_score": {"type": "number", "minimum": 0, "maximum": 100},
        "causal_score": {"type": "number", "minimum": 0, "maximum": 100},
        "uncertainty_score": {"type": "number", "minimum": 0, "maximum": 100},
        "recommended_confidence_cap": {"type": "number", "minimum": 0, "maximum": 100},
        "fatal_flags": {"type": "array", "items": {"type": "string"}},
        "notes": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "grounding_score", "causal_score", "uncertainty_score",
        "recommended_confidence_cap", "fatal_flags", "notes"
    ],
    "additionalProperties": False,
}
