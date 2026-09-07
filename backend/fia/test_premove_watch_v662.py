"""V6.6.2 regression suite for the PRE-MOVE WATCH layer.

Pins the behaviours the audit showed were absent or wrong before this release:
  * separate 4H and 8H distributions at prediction time
  * NO_EDGE on absent evidence (not a 50/50 directional call)
  * calibration may not decide direction
  * deterministic forecast identity from the evidence hash
  * gated probability-shift detection (magnitude, freshness, quality, hysteresis, dedup)
  * hash-chained, atomically written observation ledger
"""
import json
import os
import shutil
import sys
import tempfile
from datetime import datetime, timezone, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
BACKEND = HERE.parent
sys.path.insert(0, str(BACKEND))

_TMP = tempfile.mkdtemp(prefix="pmw_test_")
os.environ["FIA_PREMOVE_WATCH_DIR"] = _TMP

import importlib
from fia import premove_watch as W
importlib.reload(W)

CAL = {"horizons": {
    "4h": {"available": True, "a": 0.22732908, "b": 0.10794294, "n": 146},
    "8h": {"available": True, "a": 0.52734566, "b": 0.29091559, "n": 122},
}}


def sig(name, score, weight, freshness="live"):
    return {"name": name, "score": score, "weight": weight, "freshness": freshness,
            "detail": ""}


# Production snapshots ALWAYS publish source_health. The V6.6.4 age gate fails
# critical sources closed when their age cannot be established, so this fixture
# must supply it exactly as the provider layer does. All ages are fresh here;
# staleness is exercised deliberately in test_truth_fixes_v664.py.
_FRESH_SOURCE_HEALTH = {"market_quotes":{"age_seconds":0.0},"candles":{"age_seconds":0.0},"dxy":{"age_seconds":0.0},"us10y":{"age_seconds":0.0},"volatility":{"age_seconds":0.0},"news":{"age_seconds":0.0},"macro":{"age_seconds":0.0},"earnings":{"age_seconds":0.0}}


def snap(ts=None, status="LIVE"):
    return {"status": status, "provider": "Finnhub",
            "timestamp": (ts if ts is not None else datetime.now(timezone.utc).timestamp()),
            "data": {"macro_high_impact": False, "earnings_catalyst_risk": False,
                     "source_health": _FRESH_SOURCE_HEALTH}}


PH_OK = {"provider_health": {"overall": "LIVE", "score": 90.0},
         "source_health": _FRESH_SOURCE_HEALTH}


def fc(signals, status="LIVE", regime="BALANCED"):
    return {"symbol": "NQ", "status": status, "regime": regime, "signals": signals,
            "invalidation": [], "direction": "BULLISH", "bullish_probability": 50.0,
            "bearish_probability": 50.0, "confidence": 0.0}



BULL = [sig("NQ structure", 0.6, 0.20), sig("Semiconductors", 0.5, 0.12),
        sig("Mega-cap leadership", 0.4, 0.20), sig("SPX confirmation", 0.3, 0.10),
        sig("Breadth", 0.2, 0.08), sig("News", 0.1, 0.07),
        sig("DXY", 0.1, 0.08), sig("US10Y", 0.1, 0.07)]
BEAR = [sig(s["name"], -s["score"], s["weight"]) for s in BULL]
DEAD = [sig(s["name"], 0.0, s["weight"], "missing") for s in BULL]

# ---------------------------------------------------------------- 1. dual horizon
w = W.build_watch(fc(BULL), snap(), PH_OK, calibration_models=CAL, persist=False)
assert set(w["horizons"]) == {"4h", "8h"}, w["horizons"].keys()
h4, h8 = w["horizons"]["4h"], w["horizons"]["8h"]
assert h4["bullish_probability"] is not None and h8["bullish_probability"] is not None
# horizon weighting must actually differentiate the two views
assert h4["raw_probability"] != h8["raw_probability"], (h4["raw_probability"], h8["raw_probability"])
assert w["state"] == W.STATE_WATCH, w["state"]

# ---------------------------------------------------------------- 2. NO_EDGE on no evidence
w0 = W.build_watch(fc(DEAD), snap(), PH_OK, calibration_models=CAL, persist=False)
assert w0["state"] in (W.STATE_MISSING, W.STATE_NO_EDGE), w0["state"]
for h in ("4h", "8h"):
    x = w0["horizons"][h]
    assert x["direction"] == "NO_EDGE", x
    assert x["bullish_probability"] is None, x
    assert x["confidence"] == 0.0, x

# ---------------------------------------------------------------- 3. calibration may not decide direction
# Evidence mildly bearish; the 8h Platt intercept (+7.22 pts) would flip it bullish.
mild_bear = [sig("NQ structure", -0.05, 0.20), sig("Semiconductors", -0.03, 0.12),
             sig("Mega-cap leadership", -0.02, 0.20), sig("Breadth", -0.02, 0.08)]
wf = W.build_watch(fc(mild_bear), snap(), PH_OK, calibration_models=CAL, persist=False)
x8 = wf["horizons"]["8h"]
assert x8["raw_probability"] < 50.0, x8["raw_probability"]
assert x8["evidence_direction"] == "BEARISH", x8
# V6.6.4: this evidence is only mildly bearish, so the conviction gate now
# resolves the ACTIONABLE state to NO_EDGE. The property this test exists to
# protect is unchanged and still asserted above: the EVIDENCE direction must
# survive calibration. Direction is therefore either the evidence sign, or an
# explicit abstention -- but never the fitted base rate's BULLISH.
assert x8["direction"] in ("BEARISH", "NO_EDGE"), \
    "direction must follow evidence or abstain, never the fitted base rate"
assert x8["direction"] != "BULLISH", "the fitted base rate must not decide direction"
if x8["calibrated_direction"] == "BULLISH":
    assert x8["calibration_flips_direction"] is True, x8
    assert x8["confidence"] <= 20.0, "a sign conflict must reduce confidence, not raise it"
    # the published probability must AGREE with the evidence direction
    assert x8["bullish_probability"] < 50.0, \
        "published probability must not contradict the bearish evidence direction"
    assert x8["calibrated_bullish_probability"] > 50.0, x8
    assert x8["published_probability_basis"] == "raw_evidence__calibration_disagreed_on_sign", x8
# in the non-conflicting case the calibrated value is published
for hz in ("4h", "8h"):
    xx = w["horizons"][hz]
    if not xx["calibration_flips_direction"]:
        assert xx["published_probability_basis"] == "calibrated", xx
        if xx["direction"] == "BULLISH":
            assert xx["bullish_probability"] >= 50.0, xx
        elif xx["direction"] == "BEARISH":
            assert xx["bullish_probability"] <= 50.0, xx
# the no-information tilt must always be published
assert abs(x8["calibration"]["no_information_tilt_points"] - 7.222) < 0.01, x8["calibration"]
assert abs(wf["horizons"]["4h"]["calibration"]["no_information_tilt_points"] - 2.696) < 0.01

# ---------------------------------------------------------------- 4. deterministic identity
a = W.build_watch(fc(BULL), snap(ts=1788600000.0), PH_OK, calibration_models=CAL, persist=False)
b = W.build_watch(fc(BULL), snap(ts=1788600000.0), PH_OK, calibration_models=CAL, persist=False)
assert a["forecast_id"] == b["forecast_id"], "identical evidence must yield an identical id"
assert a["evidence_hash"] == b["evidence_hash"]
c = W.build_watch(fc(BEAR), snap(ts=1788600000.0), PH_OK, calibration_models=CAL, persist=False)
assert c["forecast_id"] != a["forecast_id"], "different evidence must yield a different id"

# ---------------------------------------------------------------- 5. staleness
old_ts = (datetime.now(timezone.utc) - timedelta(seconds=W.MAX_EVIDENCE_AGE_SECONDS + 600)).timestamp()
ws = W.build_watch(fc(BULL), snap(ts=old_ts), PH_OK, calibration_models=CAL, persist=False)
assert ws["state"] == W.STATE_STALE, ws["state"]

# ---------------------------------------------------------------- 6. degraded / not-live
wd = W.build_watch(fc(BULL, status="DEMO"), snap(status="FINNHUB_ERROR"), PH_OK,
                   calibration_models=CAL, persist=False)
assert wd["state"] in (W.STATE_DEGRADED, W.STATE_MISSING), wd["state"]

# ---------------------------------------------------------------- 7. shift gating
shutil.rmtree(_TMP, ignore_errors=True)
os.makedirs(_TMP, exist_ok=True)
importlib.reload(W)

r1 = W.build_watch(fc(BULL), snap(), PH_OK, calibration_models=CAL, persist=True)
assert r1["probability_shift"]["detected"] is False
assert "no_prior_observation" in r1["probability_shift"]["reasons"]

# a tiny change must NOT alert
tiny = [sig(s["name"], s["score"] + 0.005, s["weight"]) for s in BULL]
r2 = W.build_watch(fc(tiny), snap(), PH_OK, calibration_models=CAL, persist=True)
assert r2["probability_shift"]["detected"] is False, r2["probability_shift"]
assert any("below_min_shift_points" in x for x in r2["probability_shift"]["reasons"]), r2["probability_shift"]

# HYSTERESIS: a single-observation reversal is large enough in magnitude but must
# NOT alert yet, because the new direction has not persisted. This is the anti-noise
# guarantee -- one flickering refresh may not raise an alert.
r3a = W.build_watch(fc(BEAR), snap(), PH_OK, calibration_models=CAL, persist=True)
ps = r3a["probability_shift"]
assert ps["eligible"] is True, ps
assert abs(ps["h8_delta_points"]) >= W.MIN_SHIFT_POINTS, ps
assert ps["detected"] is False, "a one-off flip must be suppressed by hysteresis"
assert "direction_not_persistent_across_hysteresis_window" in ps["reasons"], ps
assert r3a["state"] != W.STATE_SHIFT, r3a["state"]

# Once the new direction PERSISTS into a second observation, the shift is confirmed.
BEAR2 = [sig(s["name"], s["score"] - 0.12, s["weight"]) for s in BEAR]
r3 = W.build_watch(fc(BEAR2), snap(), PH_OK, calibration_models=CAL, persist=True)
ps = r3["probability_shift"]
assert ps["eligible"] is True, ps
assert ps["detected"] is True, ps
assert ps["magnitude_points"] >= W.MIN_SHIFT_POINTS, ps
assert r3["state"] == W.STATE_SHIFT, r3["state"]
assert ps["before_hash"] and ps["before_hash"] != r3["evidence_hash"], ps

# stale evidence must never raise an alert
r4 = W.build_watch(fc(BULL), snap(ts=old_ts), PH_OK, calibration_models=CAL, persist=True)
assert r4["probability_shift"]["detected"] is False, r4["probability_shift"]

# no-evidence must never raise an alert
r5 = W.build_watch(fc(DEAD), snap(), PH_OK, calibration_models=CAL, persist=True)
assert r5["probability_shift"]["detected"] is False, r5["probability_shift"]

# ---------------------------------------------------------------- 8. ledger chain
chain = W.verify_chain()
assert chain["ok"] is True, chain
assert chain["rows"] >= 4, chain
assert chain["tamper_evident"] is True

rows = [json.loads(l) for l in (Path(_TMP) / "premove_watch.jsonl").read_text().splitlines() if l.strip()]
assert [r["seq"] for r in rows] == list(range(1, len(rows) + 1))
head = json.loads((Path(_TMP) / "premove_watch.head.json").read_text())
assert head["head_hash"] == rows[-1]["row_hash"]

# tampering a middle row must be detected
rows[1]["h8_bullish"] = 99.9
(Path(_TMP) / "premove_watch.jsonl").write_text(
    "\n".join(json.dumps(r, ensure_ascii=False, sort_keys=True) for r in rows) + "\n")
bad = W.verify_chain()
assert bad["ok"] is False and bad["tamper_evident"] is False, bad
assert any("row_hash_mismatch" in i or "chain_break" in i for i in bad["issues"]), bad["issues"]

# ---------------------------------------------------------------- 9. research-only policy
assert r1["policy"]["broker_execution"] is False
assert r1["policy"]["auto_trading_signal"] is False
assert r1["policy"]["no_edge_is_a_valid_answer"] is True
assert r1["measured_performance_disclosure"]["status"] == "NO_DEMONSTRATED_EDGE"

shutil.rmtree(_TMP, ignore_errors=True)
print("PASS test_premove_watch_v662")
