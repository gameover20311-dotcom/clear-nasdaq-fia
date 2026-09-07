"""Regression tests for fia.chart_analyst_report.

These lock the behaviours that keep the Chart Analyst honest:
  * chart-derived claims never appear inside the verified-backend block
  * missing / degraded / NO_EDGE never becomes agreement or neutral
  * 4H and 8H stay separate
  * setup quality is never a probability or win rate
  * FIA does not simply agree with the user
"""
from __future__ import annotations

import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from fia.chart_analyst_report import (  # noqa: E402
    BACKEND as ORIGIN_BACKEND,
    CHART as ORIGIN_CHART,
    DETECTED,
    NOT_CONFIRMED,
    build_chart_analyst_report,
    build_chart_only,
    build_user_comparison,
    build_verified_backend,
)

FAILURES = []


def check(name, condition, detail=""):
    if condition:
        print("  PASS  %s" % name)
    else:
        print("  FAIL  %s %s" % (name, detail))
        FAILURES.append(name)


# --------------------------------------------------------------------------- #
def vision_fixture(**over):
    base = {
        "instrument": "NQ",
        "timeframes_visible": ["15m", "1h"],
        "direction": "BULLISH",
        "bullish_probability": 62.0,
        "bearish_probability": 38.0,
        "confidence": 71.0,
        "htf_poi": {"detected": True, "type": "demand", "note": "visible demand zone"},
        "order_blocks": [{"note": "bullish OB"}],
        "fair_value_gaps": [],
        "session_liquidity": [],
        "liquidity_sweep": {"detected": True, "side": "sell-side", "note": "swept then reclaimed"},
        "smt": {"detected": False},
        "structure_shift": {"detected": True, "type": "CHoCH"},
        "displacement": {"detected": False},
        "execution_confirmation": {"detected": False},
        "invalidation": "Loss of the demand zone low",
        "supporting_observations": ["reclaim after sweep"],
        "conflicting_observations": [],
        "missing_evidence": ["no comparison instrument for SMT"],
        "thesis": "Sweep and reclaim into demand.",
        "provider": "Gemini Vision",
        "model": "gemini-3.6-flash",
    }
    base.update(over)
    return base


def premove_fixture(state="WATCH", h8_dir="BULLISH", h4_dir="BULLISH", degraded=False, **over):
    base = {
        "state": state,
        "regime": "BALANCED",
        "horizons": {
            "8h": {
                "state": state,
                "direction": h8_dir,
                "bullish_probability": 57.27,
                "bearish_probability": 42.73,
                "confidence": 0.34,
                "raw_probability": 50.09,
                "calibration": {"no_information_tilt_points": 7.22},
                "calibration_flips_direction": False,
                "direction_basis": "raw_evidence_score__calibration_may_not_decide_sign",
                "drivers": [
                    {"name": "Mega-cap leadership", "score": -0.315, "effective_weight": 0.22, "freshness": "live"},
                    {"name": "NQ structure", "score": 0.161, "effective_weight": 0.19, "freshness": "live"},
                    {"name": "Semiconductors", "score": 0.653, "effective_weight": 0.12, "freshness": "live"},
                ],
            },
            "4h": {
                "state": state,
                "direction": h4_dir,
                "bullish_probability": 52.95,
                "bearish_probability": 47.05,
                "confidence": 4.15,
                "raw_probability": 51.13,
                "calibration": {"no_information_tilt_points": 2.70},
            },
        },
        "evidence_quality": {
            "coverage": 0.92,
            "grade": "HIGH",
            "live_signal_count": 8,
            "total_signal_count": 10,
            "degraded": degraded,
            "stale": False,
            "not_live": False,
        },
        "catalyst_risk": {"level": "LOW", "known": True, "earnings_catalyst_risk": False, "macro_high_impact": None},
        "invalidation": ["NQ structure flips materially bearish"],
        "measured_performance_disclosure": {"status": "NO_DEMONSTRATED_EDGE"},
    }
    base.update(over)
    return base


SNAPSHOT = {
    "dxy_value": 99.157,
    "us10y_value": 4.784,
    "semis": 0.653,
    "breadth": -0.0098,
    "mega_cap": -0.315,
    "provider_health": {"missing_sources": ["macro", "earnings"], "stale_sources": []},
}

COGNITIVE = {
    "critic": {"severity": "LOW", "objections": ["Critical context is missing"], "hard_hold": False},
    "hypotheses": {
        "bullish_hypothesis": {"strength": 2.2366},
        "bearish_hypothesis": {"strength": 0.5695},
        "dominant_hypothesis": "BULLISH",
    },
}


# --------------------------------------------------------------------------- #
print("\n[1] chart-only block is tagged CHART and never asserts market truth")
chart = build_chart_only(vision_fixture())
check("origin is CHART", chart["origin"] == ORIGIN_CHART)
check("direction read", chart["direction"] == "BULLISH")
check("detected features found", "htf_poi" in chart["features_detected"])
check("undetected -> NOT_CONFIRMED", "smt" in chart["features_not_confirmed"])
smt = [f for f in chart["features"] if f["key"] == "smt"][0]
check("smt state NOT_CONFIRMED", smt["state"] == NOT_CONFIRMED)
poi = [f for f in chart["features"] if f["key"] == "htf_poi"][0]
check("poi state DETECTED", poi["state"] == DETECTED)
check("every feature tagged CHART", all(f["origin"] == ORIGIN_CHART for f in chart["features"]))

print("\n[2] unreadable chart is not forced into a direction")
unclear = build_chart_only(vision_fixture(direction="GARBAGE", confidence=None))
check("direction UNKNOWN", unclear["direction"] == "UNKNOWN")
check("readability UNCLEAR", unclear["readability"] == "UNCLEAR")

print("\n[3] verified-backend block keeps 4H and 8H separate")
backend = build_verified_backend(premove_fixture(), {}, SNAPSHOT, COGNITIVE)
check("origin BACKEND", backend["origin"] == ORIGIN_BACKEND)
check("8h present", backend["horizon_8h"]["bullish_probability"] == 57.27)
check("4h present", backend["horizon_4h"]["bullish_probability"] == 52.95)
check("horizons differ", backend["horizon_8h"]["confidence"] != backend["horizon_4h"]["confidence"])
check("tilt surfaced", backend["horizon_8h"]["no_information_tilt_points"] == 7.22)
check("missing sources visible", backend["missing_sources"] == ["macro", "earnings"])
check("drivers sorted by weight", backend["dominant_drivers"][0]["name"] == "Mega-cap leadership")
check(
    "same-model agreement not independent",
    backend["reasoning_layers"]["same_model_agreement_is_independent_evidence"] is False,
)

print("\n[4] missing horizon fails closed, never neutral")
empty = build_verified_backend({}, {}, {}, {})
check("8h unavailable", empty["horizon_8h"]["available"] is False)
check("state MISSING_DATA", empty["horizon_8h"]["state"] == "MISSING_DATA")
check("direction UNKNOWN not NEUTRAL", empty["horizon_8h"]["direction"] == "UNKNOWN")
check("probability None not 50", empty["horizon_8h"]["bullish_probability"] is None)

print("\n[5] agreement verdicts")
rpt = build_chart_analyst_report(vision_fixture(), {}, premove_fixture(), {}, SNAPSHOT, COGNITIVE)
check("CONFIRMS when both bullish", rpt["headline"]["agreement"]["verdict"] == "CONFIRMS")

conflict = build_chart_analyst_report(
    vision_fixture(direction="BEARISH", bullish_probability=30.0, bearish_probability=70.0),
    {}, premove_fixture(), {}, SNAPSHOT, COGNITIVE,
)
check("CONFLICTS when opposed", conflict["headline"]["agreement"]["verdict"] == "CONFLICTS")

no_edge = build_chart_analyst_report(
    vision_fixture(), {}, premove_fixture(state="NO_EDGE"), {}, SNAPSHOT, COGNITIVE,
)
check("NO_EDGE -> INSUFFICIENT_DATA", no_edge["headline"]["agreement"]["verdict"] == "INSUFFICIENT_DATA")
check("NO_EDGE not scored as agreement", no_edge["headline"]["agreement"]["verdict"] != "CONFIRMS")

split = build_chart_analyst_report(
    vision_fixture(), {}, premove_fixture(h4_dir="BEARISH"), {}, SNAPSHOT, COGNITIVE,
)
check("4H/8H split -> PARTIAL", split["headline"]["agreement"]["verdict"] == "PARTIAL")

degraded = build_chart_analyst_report(
    vision_fixture(), {}, premove_fixture(degraded=True), {}, SNAPSHOT, COGNITIVE,
)
check("degraded downgrades CONFIRMS", degraded["headline"]["agreement"]["verdict"] == "PARTIAL")

unclear_rpt = build_chart_analyst_report(
    vision_fixture(direction="GARBAGE", confidence=None), {}, premove_fixture(), {}, SNAPSHOT, COGNITIVE,
)
check("unclear chart -> INSUFFICIENT_DATA", unclear_rpt["headline"]["agreement"]["verdict"] == "INSUFFICIENT_DATA")

print("\n[6] setup quality is descriptive, never a probability")
q = rpt["headline"]["setup_quality"]
check("is_probability false", q["is_probability"] is False)
check("is_win_rate false", q["is_win_rate"] is False)
check("gate requires OOS", q["validation_gate"] == "OOS_VALIDATION_REQUIRED")
check("conflict -> NO_SETUP", conflict["headline"]["setup_quality"]["grade"] == "NO_SETUP")
check("insufficient -> NOT_GRADED", no_edge["headline"]["setup_quality"]["grade"] == "NOT_GRADED")
check("no numeric grade leaked", not isinstance(q["grade"], (int, float)))

print("\n[7] key reasons are capped and origin-tagged")
reasons = rpt["headline"]["key_reasons"]
check("at most 3 reasons", len(reasons) <= 3)
check("all tagged", all(r.get("origin") in {ORIGIN_CHART, ORIGIN_BACKEND} for r in reasons))
check("conflicting top driver surfaced", any("argues against" in r["text"] for r in reasons))

print("\n[8] invalidation keeps both sides separate")
inv = rpt["headline"]["invalidation"]
check("chart side tagged CHART", inv["visible_in_chart"]["origin"] == ORIGIN_CHART)
check("backend side tagged BACKEND", inv["verified_from_backend"]["origin"] == ORIGIN_BACKEND)
check("backend conditions real", inv["verified_from_backend"]["conditions"] == ["NQ structure flips materially bearish"])

print("\n[9] user comparison — FIA does not simply agree")
agree = build_user_comparison({"direction": "BULLISH"}, chart, backend, {})
check("AGREES when all align", agree["verdict"] == "AGREES")
disagree = build_user_comparison({"direction": "BEARISH"}, chart, backend, {})
check("DISAGREES when opposed", disagree["verdict"] == "DISAGREES")
none_given = build_user_comparison({}, chart, backend, {})
check("no direction -> INSUFFICIENT_EVIDENCE", none_given["verdict"] == "INSUFFICIENT_EVIDENCE")
noedge_backend = build_verified_backend(premove_fixture(state="NO_EDGE"), {}, SNAPSHOT, COGNITIVE)
noedge_user = build_user_comparison({"direction": "BULLISH"}, chart, noedge_backend, {})
check("NO_EDGE -> INSUFFICIENT_EVIDENCE", noedge_user["verdict"] == "INSUFFICIENT_EVIDENCE")
partial = build_user_comparison(
    {"direction": "BULLISH"},
    build_chart_only(vision_fixture(direction="BEARISH", bullish_probability=30.0, bearish_probability=70.0)),
    backend, {},
)
check("user matches FIA only -> PARTIALLY_AGREES", partial["verdict"] == "PARTIALLY_AGREES")
unconfirmed = build_user_comparison(
    {"direction": "BULLISH"}, chart, backend,
    {"independent_feature_check": {"user_only_unconfirmed": ["smt"], "confirmed_by_both": ["htf_poi"]}},
)
check("unconfirmed user claims surfaced", unconfirmed["user_claims_not_confirmed"] == ["smt"])

print("\n[10] separation policy is explicit and no chart field leaks into backend block")
pol = rpt["separation_policy"]
check("chart claims not market facts", pol["chart_claims_are_market_facts"] is False)
check("vision may not state live data", pol["vision_may_state_live_market_data"] is False)
check("missing never neutral", pol["missing_evidence_converted_to_neutral"] is False)
check("horizons not blended", pol["horizons_blended"] is False)
vb = rpt["verified_backend"]
leaked = [k for k in ("thesis", "features", "readability", "chart_clarity_confidence") if k in vb]
check("no chart keys inside verified_backend", not leaked, str(leaked))
check("research only", rpt["research_only"] is True)
check("broker execution off", rpt["broker_execution"] is False)

print("\n" + "=" * 60)
if FAILURES:
    print("FAILED %d check(s): %s" % (len(FAILURES), ", ".join(FAILURES)))
    sys.exit(1)
print("ALL CHART ANALYST REPORT CHECKS PASSED")
