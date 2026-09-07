from __future__ import annotations

from dataclasses import dataclass
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fia.advanced_chart_intelligence import INDEPENDENCE_POLICY
from fia.three_way_confluence import build_three_way_confluence


@dataclass
class Forecast:
    direction: str = "BULLISH"
    bullish_probability: float = 62.0
    bearish_probability: float = 38.0


def check(name, condition, detail=None):
    if not condition:
        raise AssertionError(f"{name} FAIL {detail or ''}")
    print("PASS", name)


def main():
    check("Vision cannot see FIA direction", INDEPENDENCE_POLICY["fia_direction_visible"] is False)
    check("Vision cannot see user direction", INDEPENDENCE_POLICY["user_direction_visible"] is False)
    check("Vision cannot see user reasoning", INDEPENDENCE_POLICY["user_reasoning_visible"] is False)
    check("Chart layer cannot execute broker orders", INDEPENDENCE_POLICY["broker_execution"] is False)

    user = {
        "direction": "BULLISH",
        "timeframe": "1M",
        "reasoning": "HTF demand POI, order block, FVG, sell-side liquidity sweep and CHoCH confirmation",
    }
    vision = {
        "direction": "BULLISH",
        "confidence": 82,
        "htf_poi": {"detected": True, "direction": "BULLISH"},
        "order_blocks": [{"direction": "BULLISH"}],
        "fair_value_gaps": [{"direction": "BULLISH"}],
        "liquidity_sweep": {"detected": True, "side": "SELL_SIDE", "direction": "BULLISH"},
        "smt": {"detected": False},
        "structure_shift": {"detected": True, "type": "CHOCH", "direction": "BULLISH"},
        "displacement": {"detected": True, "direction": "BULLISH"},
        "execution_confirmation": {"detected": True, "timeframe": "1m", "direction": "BULLISH"},
    }
    aligned = build_three_way_confluence(Forecast(), user, vision)
    check("FIA User Vision three-way alignment works", aligned["three_way_alignment"] == "ALIGNED", aligned)
    check("Independent user claims are verified against Vision", len(aligned["independent_feature_check"]["confirmed_by_both"]) >= 4, aligned)
    check("A++ remains OOS-gated", aligned["validation_gate"] == "OOS_VALIDATION_REQUIRED", aligned)
    check("Broker execution remains disabled", aligned["broker_execution"] is False, aligned)

    conflict = build_three_way_confluence(
        Forecast(),
        {"direction": "BEARISH", "reasoning": "bearish order block"},
        vision,
    )
    check("Directional conflict triggers research hold", conflict["research_hold"] is True, conflict)
    check("Directional conflict is explicit", conflict["three_way_alignment"] == "CONFLICT", conflict)

    print("PHASE 31 REMAINING TWO FEATURES TEST PASS")


if __name__ == "__main__":
    main()
