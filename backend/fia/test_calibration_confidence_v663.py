"""Regression tests for the V6.6.3 calibration + confidence fixes.

Each test below locks a defect that was reproduced empirically before the fix.

  BUG-1  Calibration intercept could flip the published direction.
  BUG-2  A no-information raw 50.0 was rendered as a directional 52.7% / 57.2%.
  BUG-3  Pre-move applied a calibrator fitted on a DIFFERENT layer's raw scores.
  BUG-4  Stale evidence did not reduce confidence.
  BUG-5  Unknown observation age was treated as fresh.
  BUG-6  Correlated / common-source evidence RAISED confidence.
"""
from __future__ import annotations

import math
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from fia.cognitive.calibration import (  # noqa: E402
    apply_calibration, fit_slope_only, load_models, load_premove_models,
)
from fia.premove_watch import (  # noqa: E402
    DIVERSITY_REFERENCE, HARD_BAD_CONFIDENCE_CAP, STALE_CONFIDENCE_CAP,
    UNKNOWN_AGE_CONFIDENCE_CAP, build_watch,
)

FAILURES = []


def check(name, cond, detail=""):
    if cond:
        print("  PASS  %s" % name)
    else:
        print("  FAIL  %s %s" % (name, detail))
        FAILURES.append(name)


def signals(scores=None, freshness="live"):
    base = [("NQ structure", 0.20), ("SPX confirmation", 0.10), ("DXY", 0.08),
            ("US10Y", 0.07), ("Mega-cap leadership", 0.20), ("Semiconductors", 0.12),
            ("Breadth", 0.08), ("News", 0.07), ("Macro calendar", 0.04),
            ("Earnings/guidance", 0.04)]
    scores = scores or {}
    return [{"name": n, "score": scores.get(n, 0.4), "weight": w, "freshness": freshness}
            for n, w in base]


def watch(sig, ts=None, status="LIVE", ph="LIVE"):
    fc = {"status": status, "direction": "BULLISH", "signals": sig,
          "regime": "BALANCED", "invalidation": []}
    # Production snapshots always publish source_health; the V6.6.4 age gate
    # fails critical sources closed without it. Fresh ages here so this file keeps
    # testing calibration/confidence rather than the age gate.
    snap = {"status": status, "timestamp": ts if ts is not None else time.time(),
            "data": {"source_health": {"market_quotes":{"age_seconds":0.0},"candles":{"age_seconds":0.0},"dxy":{"age_seconds":0.0},"us10y":{"age_seconds":0.0},"volatility":{"age_seconds":0.0},"news":{"age_seconds":0.0},"macro":{"age_seconds":0.0},"earnings":{"age_seconds":0.0}}}}
    return build_watch(fc, snap, {"provider_health": {"overall": ph}}, persist=False)


# --------------------------------------------------------------------------- #
print("\n[BUG-1/2] calibration models are slope-only: no sign flip, no base-rate injection")
for loader, label in ((load_models, "cognitive"), (load_premove_models, "premove")):
    m = loader()
    check("%s model available" % label, m.get("available") is True)
    check("%s intercept pinned flag" % label, m.get("intercept_pinned_at_zero") is True)
    for h in ("4h", "8h"):
        hm = (m.get("horizons") or {}).get(h) or {}
        check("%s %s b == 0" % (label, h), float(hm.get("b", 1)) == 0.0, str(hm.get("b")))
        check("%s %s holdout not fitted" % (label, h),
              m.get("dataset_split", {}).get("holdout_used_for_fitting") is False)
        # a no-information 50.0 must stay 50.0
        out = apply_calibration(50.0, hm)
        check("%s %s calibrate(50.0) == 50.0" % (label, h), abs(out - 50.0) < 1e-6, str(out))
        # sign can never cross
        for raw in (25.0, 40.0, 49.0, 49.99, 50.01, 51.0, 60.0, 75.0):
            cal = apply_calibration(raw, hm)
            same = (raw > 50.0) == (cal > 50.0) if raw != 50.0 else True
            check("%s %s sign preserved at raw=%.2f" % (label, h, raw), same,
                  "raw=%.2f cal=%.3f" % (raw, cal))

print("\n[BUG-2] no-information evidence must not produce a directional headline")
w = watch(signals({n: 0.0 for n, _ in
                   [(s["name"], 0) for s in signals()]}))
h8 = w["horizons"]["8h"]
check("raw is 50.0 on zero evidence", abs(float(h8["raw_probability"]) - 50.0) < 1e-6,
      str(h8["raw_probability"]))
check("published is 50.0 on zero evidence", abs(float(h8["bullish_probability"]) - 50.0) < 0.01,
      str(h8["bullish_probability"]))
check("no base-rate tilt reported", abs(float(h8["calibration"].get("no_information_tilt_points", 1))) < 1e-6,
      str(h8["calibration"].get("no_information_tilt_points")))
check("confidence collapses to 0", float(h8["confidence"]) == 0.0, str(h8["confidence"]))

print("\n[BUG-1] no horizon may report a calibration-induced sign flip")
w = watch(signals({"NQ structure": -0.02, "SPX confirmation": -0.02, "DXY": -0.02,
                   "US10Y": -0.02, "Mega-cap leadership": -0.02, "Semiconductors": -0.02,
                   "Breadth": -0.02, "News": -0.02, "Macro calendar": -0.02,
                   "Earnings/guidance": -0.02}))
for h in ("4h", "8h"):
    x = w["horizons"][h]
    # The evidence is only slightly bearish, so as of V6.6.4 the conviction gate
    # correctly resolves the ACTIONABLE state to NO_EDGE. What this test locks is
    # the calibration property: the evidence sign must survive calibration and the
    # published probability must stay on the bearish side of 50.
    check("%s evidence direction stays BEARISH" % h,
          x["evidence_direction"] == "BEARISH", str(x.get("evidence_direction")))
    check("%s calibration_flips_direction is False" % h,
          x["calibration_flips_direction"] is False, str(x["calibration_flips_direction"]))
    check("%s published below 50" % h, float(x["bullish_probability"]) < 50.0,
          str(x["bullish_probability"]))
    check("%s low conviction -> NO_EDGE (V6.6.4 gate)" % h,
          x["direction"] == "NO_EDGE" and x["actionable"] is False,
          "%s / %s" % (x["direction"], x.get("actionable")))

print("\n[BUG-3] pre-move uses its OWN calibrator, not the cognitive one")
pm = load_premove_models(); cg = load_models()
check("premove model layer tag", pm.get("layer") == "PREMOVE", str(pm.get("layer")))
check("cognitive model layer tag", cg.get("layer") == "COGNITIVE", str(cg.get("layer")))
check("premove fitted on premove raw", "premove raw" in str(pm.get("fitted_on", "")).lower())
check("slopes are genuinely different",
      (pm.get("horizons", {}).get("8h", {}).get("a")
       != cg.get("horizons", {}).get("8h", {}).get("a")))

print("\n[BUG-4] stale evidence must reduce confidence")
fresh = watch(signals(), ts=datetime.now(timezone.utc).isoformat())
stale = watch(signals(), ts=(datetime.now(timezone.utc) - timedelta(seconds=4000)).isoformat())
cf = float(fresh["horizons"]["8h"]["confidence"]); cs = float(stale["horizons"]["8h"]["confidence"])
check("stale state detected", stale["state"] == "STALE", stale["state"])
check("stale confidence <= cap", cs <= STALE_CONFIDENCE_CAP, "%.2f > %.2f" % (cs, STALE_CONFIDENCE_CAP))
check("stale confidence < fresh confidence", cs < cf, "stale=%.2f fresh=%.2f" % (cs, cf))
check("stale cap flagged in basis", stale["horizons"]["8h"]["confidence_basis"]["stale_cap_applied"] is True)

print("\n[BUG-5] unknown observation age is not treated as fresh")
unknown = watch(signals(), ts=None if False else "")   # empty timestamp -> unparseable
q = unknown["evidence_quality"]
cu = float(unknown["horizons"]["8h"]["confidence"])
check("age_unknown detected", q["age_unknown"] is True, str(q["age_unknown"]))
check("unknown-age confidence <= cap", cu <= UNKNOWN_AGE_CONFIDENCE_CAP,
      "%.2f > %.2f" % (cu, UNKNOWN_AGE_CONFIDENCE_CAP))
check("unknown-age cap flagged", unknown["horizons"]["8h"]["confidence_basis"]["unknown_age_cap_applied"] is True)

print("\n[BUG-6] correlated / common-source evidence must not raise confidence")
diverse = watch(signals())
narrow_sig = [s for s in signals()
              if s["name"] in ("Semiconductors", "Mega-cap leadership", "NQ structure")]
narrow = watch(narrow_sig)
cd = float(diverse["horizons"]["8h"]["confidence"])
cn = float(narrow["horizons"]["8h"]["confidence"])
ed = diverse["horizons"]["8h"]["confidence_basis"]["effective_contributors"]
en = narrow["horizons"]["8h"]["confidence_basis"]["effective_contributors"]
check("diverse has more effective contributors", ed > en, "diverse=%.2f narrow=%.2f" % (ed, en))
check("narrow evidence does NOT exceed diverse confidence", cn <= cd,
      "narrow=%.2f diverse=%.2f" % (cn, cd))
check("diversity factor < 1 when concentrated",
      float(narrow["horizons"]["8h"]["confidence_basis"]["diversity_factor"]) < 1.0,
      str(narrow["horizons"]["8h"]["confidence_basis"]["diversity_factor"]))

print("\n[BUG-7] a hard-bad status must not support a mid-confidence directional call")
good = watch(signals(), ph="LIVE")
bad = watch(signals(), ph="ERROR")
cg_ = float(good["horizons"]["8h"]["confidence"]); cb_ = float(bad["horizons"]["8h"]["confidence"])
check("hard_bad detected", bad["evidence_quality"]["hard_bad"] is True)
check("hard-bad confidence <= cap", cb_ <= HARD_BAD_CONFIDENCE_CAP,
      "%.2f > %.2f" % (cb_, HARD_BAD_CONFIDENCE_CAP))
check("hard-bad confidence < healthy confidence", cb_ < cg_, "bad=%.2f good=%.2f" % (cb_, cg_))
check("hard-bad cap flagged", bad["horizons"]["8h"]["confidence_basis"]["hard_bad_cap_applied"] is True)

print("\n[INVARIANTS] confidence is not probability; horizons stay separate")
w = watch(signals())
for h in ("4h", "8h"):
    x = w["horizons"][h]
    check("%s confidence != bullish_probability" % h,
          float(x["confidence"]) != float(x["bullish_probability"]))
    check("%s bull+bear == 100" % h,
          abs(float(x["bullish_probability"]) + float(x["bearish_probability"]) - 100.0) < 0.01)
    check("%s confidence_basis published" % h, isinstance(x.get("confidence_basis"), dict))
# Horizon weights only change the answer when the SIGNALS DIFFER from each other.
# With a uniform score c, sum(c*w)/sum|w| == c for any weight vector, so identical
# 4H/8H raw is the mathematically correct result there -- not a separation bug.
varied = watch(signals({"NQ structure": 0.9, "US10Y": -0.8, "DXY": -0.6,
                        "Mega-cap leadership": 0.1, "Semiconductors": 0.7,
                        "Breadth": -0.2, "News": 0.3, "SPX confirmation": -0.4}))
r4 = float(varied["horizons"]["4h"]["raw_probability"])
r8 = float(varied["horizons"]["8h"]["raw_probability"])
check("4H and 8H raw differ under varied evidence (separate weights)", r4 != r8,
      "4h=%.4f 8h=%.4f" % (r4, r8))
uniform4 = float(w["horizons"]["4h"]["raw_probability"])
uniform8 = float(w["horizons"]["8h"]["raw_probability"])
check("uniform evidence yields identical raw by construction", uniform4 == uniform8,
      "4h=%.4f 8h=%.4f" % (uniform4, uniform8))

print("\n" + "=" * 62)
if FAILURES:
    print("FAILED %d check(s):" % len(FAILURES))
    for f in FAILURES:
        print("   -", f)
    sys.exit(1)
print("ALL CALIBRATION + CONFIDENCE REGRESSION CHECKS PASSED")
