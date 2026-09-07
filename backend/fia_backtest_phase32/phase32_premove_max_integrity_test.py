from __future__ import annotations

import tempfile
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fia.premove_max_engine import analyze_premove_max


class S:
    def __init__(self, n, s, w=.1, f="live"):
        self.name=n; self.score=s; self.weight=w; self.freshness=f


class F:
    direction="BULLISH"; bullish_probability=64.0; bearish_probability=36.0; confidence=72.0
    score=.3; regime="TRANSITION"; data_coverage=.92; intelligence_coverage=.82
    consistency={}
    signals=[]


def forecast(ts, p=64.0, lead=1.0):
    f=F(); f.generated_at=ts; f.bullish_probability=p
    f.signals=[
        S("NQ structure", .10*lead, .20), S("SPX confirmation", .32*lead, .10),
        S("DXY", .42*lead, .08), S("US10Y", .36*lead, .07),
        S("Mega-cap leadership", .55*lead, .20), S("Semiconductors", .60*lead, .12),
        S("Breadth", .48*lead, .08), S("News", .22*lead, .07),
        S("Macro calendar", .12*lead, .04), S("Earnings/guidance", .18*lead, .04),
    ]
    return f


def check(name, cond, detail=None):
    if not cond:
        raise AssertionError(f"{name} FAIL {detail}")
    print("PASS", name)


def main():
    with tempfile.TemporaryDirectory() as d:
        h=Path(d)/"history.jsonl"; mh=Path(d)/"max.jsonl"
        times=["2026-09-02T14:00:00+00:00","2026-09-02T14:15:00+00:00","2026-09-02T14:30:00+00:00","2026-09-02T14:45:00+00:00"]
        for i,ts in enumerate(times[:-1]):
            analyze_premove_max(forecast(ts,55+i*4), {"data":{"nq_futures_price":23000+i*5}}, h, mh, True)
        r=analyze_premove_max(forecast(times[-1],69), {"data":{"nq_futures_price":23020}}, h, mh, False)
        check("max module returns", r["module"]=="FIA PRE-MOVE MAX RIGOR", r.get("module"))
        check("core probability not overwritten", r["probability_policy"]["core_probability_untouched"] is True)
        check("decision strength separate from probability", r["probability_policy"]["status"]=="NOT_A_CALIBRATED_PROBABILITY")
        check("multi-window slopes present", "short" in r["multi_window_trajectory"]["leading_score_slopes_per_hour"])
        check("change-point detector present", "change_point" in r["multi_window_trajectory"])
        check("persistence present", r["persistence_hysteresis"]["persistence"]["sample"]>=1)
        check("ensemble present", r["ensemble"]["active_experts"]>=1)
        check("historical lead-lag present", isinstance(r["historical_lead_lag"], list))
        check("optional data missing is explicit", r["optional_institutional_inputs"]["VXN"]["status"]=="MISSING_NOT_FAKED")
        check("counterfactual present", len(r["counterfactual"])>=1)
        check("persistent alert gate present", "fire" in r["alert"] and "lead_time_status" in r["alert"])
        check("90 percent claim blocked", r["validation_gate"]["no_90_percent_claim_without_evidence"] is True)
        check("broker execution disabled", r["broker_execution"] is False)
    print("PHASE 32 PRE-MOVE MAX INTEGRITY TEST PASS")


if __name__ == "__main__":
    main()
