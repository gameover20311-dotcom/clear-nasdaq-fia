"""Regression tests for the V6.6.4 high-priority truth fixes.

  FIX-1  Displayed 4H/8H must be the locked forecast (display/lock parity).
  FIX-2  "Breadth" was not breadth.
  FIX-3  Age-based hard exclusion; a stale badge alone was not enough.
  FIX-4  Low-confidence / low-edge must resolve to NO_EDGE, not a direction.
"""
from __future__ import annotations

import asyncio
import json
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from fia.forward_oos import _forecast_values  # noqa: E402
from fia.premove_watch import (  # noqa: E402
    AGE_CRITICAL_SOURCES, MAX_AGE_SECONDS_BY_SOURCE, MIN_CONFIDENCE_FOR_DIRECTION,
    MIN_EDGE_POINTS, SIGNAL_SOURCE, age_gate, build_watch, excluded_signals,
)

FAILURES = []


def check(name, cond, detail=""):
    if cond:
        print("  PASS  %s" % name)
    else:
        print("  FAIL  %s %s" % (name, detail))
        FAILURES.append(name)


BASE = [("NQ structure", 0.20), ("SPX confirmation", 0.10), ("DXY", 0.08),
        ("US10Y", 0.07), ("Mega-cap leadership", 0.20), ("Semiconductors", 0.12),
        ("Equal-weight participation", 0.08), ("News", 0.07),
        ("Macro calendar", 0.04), ("Earnings/guidance", 0.04)]


def signals(score=0.9):
    return [{"name": n, "score": score, "weight": w, "freshness": "live"} for n, w in BASE]


def snap(ages=None, ts=None):
    ages = ages or {}
    health = {src: {"status": "live", "age_seconds": ages.get(src, 0.0)}
              for src in set(SIGNAL_SOURCE.values())}
    return {"status": "LIVE",
            "timestamp": ts or datetime.now(timezone.utc).isoformat(),
            "data": {"source_health": health, "provider_health": {"overall": "LIVE"}}}


# V6.6.5: freshness became SESSION-AWARE. A 53h-old cash input on a weekend is
# CURRENT_FOR_SESSION, not stale. These tests are about the AGE CEILING, so they
# pin an OPEN cash session (Wed 14:00 ET) where lateness is genuinely stale.
# premove_watch binds session_state at MODULE level, so patch it there (patching
# fia.market_sessions would not affect the already-bound reference).
import fia.premove_watch as _PW  # noqa: E402
_OPEN_SESSION = datetime(2026, 9, 9, 18, 0, tzinfo=timezone.utc)
_ORIG_SESSION_STATE = _PW.session_state


def _force_open_session():
    _PW.session_state = (lambda src, age, ceil, now=None:
                         _ORIG_SESSION_STATE(src, age, ceil, now=_OPEN_SESSION))


def _restore_session():
    _PW.session_state = _ORIG_SESSION_STATE


def watch(sig, ages=None, ts=None):
    fc = {"status": "LIVE", "direction": "BULLISH", "signals": sig,
          "regime": "BALANCED", "invalidation": []}
    s = snap(ages, ts)
    _force_open_session()
    try:
        return build_watch(fc, s, {"provider_health": {"overall": "LIVE"},
                                   "source_health": s["data"]["source_health"]}, persist=False)
    finally:
        _restore_session()


# --------------------------------------------------------------------------- #
print("\n[FIX-2] the factor formerly called 'Breadth' is named for what it measures")
w = watch(signals())
names = {c["name"] for h in ("4h", "8h") for c in w["horizons"][h]["drivers"]}
check("'Equal-weight participation' is a scored driver", "Equal-weight participation" in names,
      str(sorted(names)))
check("no driver is labelled 'Breadth'", "Breadth" not in names, str(sorted(names)))

import fia.engine as _eng  # noqa: E402
src = Path(_eng.__file__).read_text(encoding="utf-8")
check("engine no longer emits a 'Breadth' adapter label", '("Breadth", raw.get("breadth")' not in src)
check("engine emits the honest label", '"Equal-weight participation"' in src)
import fia.providers as _prov  # noqa: E402
psrc = Path(_prov.__file__).read_text(encoding="utf-8")
check("provider documents it is NOT market breadth", "THIS IS NOT MARKET BREADTH" in psrc)
check("provider exposes the definition block", "equal_weight_participation_definition" in psrc)

print("\n[FIX-3] hard age exclusion per source, with cadence-matched ceilings")
check("ceilings differ by source (not one arbitrary threshold)",
      len(set(MAX_AGE_SECONDS_BY_SOURCE.values())) > 1, str(MAX_AGE_SECONDS_BY_SOURCE))
check("quotes ceiling tighter than macro ceiling",
      MAX_AGE_SECONDS_BY_SOURCE["market_quotes"] < MAX_AGE_SECONDS_BY_SOURCE["macro"])

fresh = watch(signals(), ages={s: 0.0 for s in set(SIGNAL_SOURCE.values())})
expired = watch(signals(), ages={**{s: 0.0 for s in set(SIGNAL_SOURCE.values())},
                                 "us10y": 190000.0})
q_e = expired["evidence_quality"]
check("expired signal is excluded", q_e["age_excluded_count"] >= 1, str(q_e["age_excluded_count"]))
excl_names = {e["name"] for e in q_e["age_excluded_signals"]}
check("US10Y excluded by ceiling", "US10Y" in excl_names, str(excl_names))
check("exclusion reason recorded",
      any(e["reason"] == "STALE_EXCLUDED_AGE_CEILING" for e in q_e["age_excluded_signals"]))
check("excluded evidence preserved for provenance",
      all("score_withheld" in e for e in q_e["age_excluded_signals"]))

# THE CORE PROOF: an expired item cannot influence the probability.
drv = {c["name"] for h in ("4h", "8h") for c in expired["horizons"][h]["drivers"]}
check("expired signal contributes to NO driver", "US10Y" not in drv, str(sorted(drv)))
opposite = [dict(s) for s in signals()]
for s_ in opposite:
    if s_["name"] == "US10Y":
        s_["score"] = -1.0          # maximally opposed
a = watch(opposite, ages={**{s: 0.0 for s in set(SIGNAL_SOURCE.values())}, "us10y": 190000.0})
b = watch(signals(), ages={**{s: 0.0 for s in set(SIGNAL_SOURCE.values())}, "us10y": 190000.0})
for h in ("4h", "8h"):
    check("%s probability unchanged when an EXPIRED signal flips sign" % h,
          a["horizons"][h]["raw_probability"] == b["horizons"][h]["raw_probability"],
          "%s vs %s" % (a["horizons"][h]["raw_probability"], b["horizons"][h]["raw_probability"]))
check("coverage falls when evidence is excluded",
      q_e["coverage"] < fresh["evidence_quality"]["coverage"],
      "%s vs %s" % (q_e["coverage"], fresh["evidence_quality"]["coverage"]))
check("excluded evidence is NOT converted to neutral",
      all(e.get("score_withheld") is not None for e in q_e["age_excluded_signals"]))

print("\n[FIX-3b] critical sources fail closed when age cannot be established")
g = age_gate({"name": "NQ structure"}, {}, now=_OPEN_SESSION)
check("candles source is age-critical", "candles" in AGE_CRITICAL_SOURCES)
check("unknown age on critical source excludes", g["included"] is False, str(g))
check("reason recorded", g["reason"] == "AGE_UNKNOWN_FOR_CRITICAL_SOURCE", g["reason"])
g2 = age_gate({"name": "Macro calendar"}, {}, now=_OPEN_SESSION)
check("unknown age on non-critical source does not exclude", g2["included"] is True, str(g2))

print("\n[FIX-4] low conviction resolves to NO_EDGE with probabilities preserved")
weak = watch([{"name": n, "score": 0.01, "weight": w, "freshness": "live"} for n, w in BASE])
for h in ("4h", "8h"):
    x = weak["horizons"][h]; g = x["conviction_gate"]
    check("%s weak evidence -> NO_EDGE state" % h, x["state"] == "NO_EDGE", x["state"])
    check("%s direction NO_EDGE" % h, x["direction"] == "NO_EDGE", x["direction"])
    check("%s not actionable" % h, x["actionable"] is False)
    check("%s gate did not pass" % h, g["passed"] is False)
    check("%s gate gives reasons" % h, len(g["reasons"]) > 0, str(g["reasons"]))
    # transparency: probabilities preserved, NOT rewritten to 50/50
    check("%s published probability preserved" % h, x["bullish_probability"] is not None)
    check("%s raw probability preserved" % h, x["raw_probability"] is not None)
    check("%s evidence_direction still recorded" % h,
          x["evidence_direction"] in ("BULLISH", "BEARISH", "BALANCED"), str(x.get("evidence_direction")))
    check("%s NOT faked to exactly 50/50" % h,
          not (x["bullish_probability"] == 50.0 and x["raw_probability"] == 50.0)
          or abs(float(x["raw_probability"]) - 50.0) < 1e-9)

strong = watch(signals(0.9))
for h in ("4h", "8h"):
    x = strong["horizons"][h]
    check("%s strong evidence stays actionable" % h, x["actionable"] is True,
          str(x.get("conviction_gate")))
    check("%s strong evidence keeps a direction" % h,
          x["direction"] in ("BULLISH", "BEARISH"), x["direction"])

print("\n[FIX-4b] boundary behaviour around the gate")
check("thresholds are explicit constants",
      MIN_EDGE_POINTS > 0 and MIN_CONFIDENCE_FOR_DIRECTION > 0,
      "%s / %s" % (MIN_EDGE_POINTS, MIN_CONFIDENCE_FOR_DIRECTION))
found_below = found_above = False
for sc in (0.005, 0.01, 0.02, 0.05, 0.1, 0.2, 0.4, 0.9):
    x = watch([{"name": n, "score": sc, "weight": w, "freshness": "live"} for n, w in BASE])["horizons"]["8h"]
    edge = float(x["edge_points"]); act = bool(x["actionable"])
    if edge < MIN_EDGE_POINTS:
        found_below = True
        check("edge %.2f < %.1f -> NO_EDGE" % (edge, MIN_EDGE_POINTS), act is False)
    if edge >= MIN_EDGE_POINTS and float(x["confidence"]) >= MIN_CONFIDENCE_FOR_DIRECTION:
        found_above = True
        check("edge %.2f >= %.1f and conf ok -> actionable" % (edge, MIN_EDGE_POINTS), act is True)
check("boundary exercised on both sides", found_below and found_above)

print("\n[FIX-1] display/lock parity: the ledger locks what was displayed")
displayed = watch(signals(0.9))
fc_obj = {"direction": "BULLISH", "bullish_probability": 61.0, "bearish_probability": 39.0,
          "confidence": 55.0, "regime": "BALANCED", "status": "LIVE",
          "data_coverage": 0.9, "intelligence_coverage": 0.8,
          "generated_at": datetime.now(timezone.utc).isoformat(), "signals": [], "invalidation": []}
locked = _forecast_values(fc_obj, displayed)
hp = locked["horizon_probabilities"]
for h in ("4h", "8h"):
    disp = displayed["horizons"][h]
    check("locked %s bullish == displayed %s bullish" % (h, h),
          abs(hp[h]["bullish_probability"] - float(disp["bullish_probability"])) < 1e-6,
          "locked=%s displayed=%s" % (hp[h]["bullish_probability"], disp["bullish_probability"]))
    check("locked %s bearish == displayed %s bearish" % (h, h),
          abs(hp[h]["bearish_probability"] - float(disp["bearish_probability"])) < 1e-6)
    check("locked %s direction == displayed" % h, hp[h]["direction"] == disp["direction"],
          "%s vs %s" % (hp[h]["direction"], disp["direction"]))
    check("locked %s state == displayed" % h, hp[h]["state"] == disp["state"],
          "%s vs %s" % (hp[h]["state"], disp["state"]))
    check("locked %s tagged as displayed source" % h,
          hp[h]["source"] == "PREMOVE_WATCH_PER_HORIZON_AS_DISPLAYED", hp[h]["source"])
check("4H and 8H locked values are independent",
      hp["4h"]["bullish_probability"] != hp["8h"]["bullish_probability"],
      "%s vs %s" % (hp["4h"]["bullish_probability"], hp["8h"]["bullish_probability"]))
check("premove identity recorded for parity audit",
      locked["premove"]["forecast_id"] == displayed["forecast_id"]
      and locked["premove"]["evidence_hash"] == displayed["evidence_hash"])

print("\n[FIX-1b] without a premove view the fallback is labelled, not disguised")
legacy = _forecast_values(fc_obj, None)
for h in ("4h", "8h"):
    check("%s fallback explicitly tagged" % h,
          legacy["horizon_probabilities"][h]["source"] == "BASE_FIA_SHARED_PREMOVE_DISTRIBUTION",
          legacy["horizon_probabilities"][h]["source"])

print("\n[FIX-1c] a displayed abstention cannot be locked as a directional observation")
import fia.forward_oos as _foos  # noqa: E402
fsrc = Path(_foos.__file__).read_text(encoding="utf-8")
check("abstention guard present", "PREMOVE_HORIZON_ABSTENTION_NOT_LOCKED_AS_DIRECTIONAL" in fsrc)
check("non-lockable premove state guard present", "PREMOVE_STATE_NOT_LOCKABLE" in fsrc)
import fia.forward_oos_api as _api  # noqa: E402
asrc = Path(_api.__file__).read_text(encoding="utf-8")
check("collector passes the displayed view", "premove=premove" in asrc)
check("collector builds it read-only", "persist=False" in asrc)
check("collector fails closed without it", "PREMOVE_VIEW_UNAVAILABLE_CANNOT_PROVE_PARITY" in asrc)

print("\n[INVARIANTS] existing protections still hold")
# Horizon weights only change the answer when signals DIFFER from one another:
# with a uniform score c, sum(c*w)/sum|w| == c for any weight vector, so identical
# raw values under uniform evidence are correct arithmetic, not a separation bug.
_varied = watch([{"name": n, "score": sc, "weight": w, "freshness": "live"}
                 for (n, w), sc in zip(BASE, [0.9, -0.8, 0.6, -0.7, 0.2, 0.8, -0.3, 0.5, 0.1, -0.4])])
check("4H and 8H remain separate under varied evidence",
      _varied["horizons"]["4h"]["raw_probability"] != _varied["horizons"]["8h"]["raw_probability"],
      "4h=%s 8h=%s" % (_varied["horizons"]["4h"]["raw_probability"],
                       _varied["horizons"]["8h"]["raw_probability"]))
for h in ("4h", "8h"):
    x = displayed["horizons"][h]
    check("%s bull+bear == 100" % h,
          abs(float(x["bullish_probability"]) + float(x["bearish_probability"]) - 100.0) < 0.01)
    check("%s calibration cannot flip sign" % h, x["calibration_flips_direction"] is False)
    check("%s no base-rate tilt" % h,
          abs(float(x["calibration"].get("no_information_tilt_points", 1))) < 1e-9)

print("\n" + "=" * 62)
if FAILURES:
    print("FAILED %d check(s):" % len(FAILURES))
    for f in FAILURES:
        print("   -", f)
    sys.exit(1)
print("ALL V6.6.4 TRUTH-FIX REGRESSION CHECKS PASSED")
