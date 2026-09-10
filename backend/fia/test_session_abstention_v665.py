"""Regression tests for the V6.6.5 zero-cost truth fixes.

  FIX-1/2  Session-aware freshness. US10Y/VIX were NOT broken feeds -- they are
           cash-session instruments, correctly frozen at Friday's close over a
           weekend. Wall-clock age alone misclassified that as STALE.
  FIX-3    The cognitive / Three-Brain path had NO age gate at all. A 54h VIX was
           feeding Volatility & Options AI at reliability 0.65.
  FIX-5    A legitimate NO_EDGE is now recorded as an immutable NON-DIRECTIONAL
           Forward-OOS observation, never as a directional call.
"""
from __future__ import annotations

import asyncio
import json
import shutil
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from fia.market_sessions import (  # noqa: E402
    SOURCE_VENUE, VENUE_CASH_INDEX, VENUE_FUTURES, market_open, session_state, summarize,
)
from fia.premove_watch import age_gate, build_watch  # noqa: E402

FAILURES = []


def check(name, cond, detail=""):
    if cond:
        print("  PASS  %s" % name)
    else:
        print("  FAIL  %s %s" % (name, detail))
        FAILURES.append(name)


# Fixed reference instants (never "now", so the test is deterministic).
SUNDAY_NIGHT = datetime(2026, 9, 7, 2, 30, tzinfo=timezone.utc)      # Sun 22:30 ET
WEDNESDAY_OPEN = datetime(2026, 9, 9, 18, 0, tzinfo=timezone.utc)    # Wed 14:00 ET
SATURDAY = datetime(2026, 9, 5, 18, 0, tzinfo=timezone.utc)          # Sat 14:00 ET

H = 3600.0

print("\n[FIX-1/2] venue awareness: a closed market is not a broken feed")
check("cash index closed on Sunday night", market_open(VENUE_CASH_INDEX, SUNDAY_NIGHT) is False)
check("futures OPEN on Sunday night (reopened 18:00 ET)",
      market_open(VENUE_FUTURES, SUNDAY_NIGHT) is True)
check("cash index open Wednesday 14:00 ET", market_open(VENUE_CASH_INDEX, WEDNESDAY_OPEN) is True)
check("futures closed Saturday", market_open(VENUE_FUTURES, SATURDAY) is False)
check("us10y mapped to a cash index venue", SOURCE_VENUE["us10y"] == VENUE_CASH_INDEX)
check("dxy mapped to a futures venue", SOURCE_VENUE["dxy"] == VENUE_FUTURES)

print("\n[FIX-1/2] the exact real-world case that produced the false diagnosis")
# Observed 2026-09-07T02:28Z: ^TNX 55.6h, ^VIX 54.3h, both weekend-frozen.
tnx = session_state("us10y", 55.6 * H, 6 * H, now=SUNDAY_NIGHT)
vix = session_state("volatility", 54.3 * H, 6 * H, now=SUNDAY_NIGHT)
check("55.6h US10Y over a weekend is CURRENT_FOR_SESSION",
      tnx["freshness"] == "CURRENT_FOR_SESSION", tnx["freshness"])
check("55.6h US10Y is USABLE (not discarded)", tnx["usable"] is True)
check("54.3h VIX over a weekend is CURRENT_FOR_SESSION",
      vix["freshness"] == "CURRENT_FOR_SESSION", vix["freshness"])
check("closure is recorded as the reason", "market closed" in tnx["reason"])

print("\n[FIX-1/2] the SAME age during an OPEN session is genuinely stale")
tnx_open = session_state("us10y", 55.6 * H, 6 * H, now=WEDNESDAY_OPEN)
check("55.6h US10Y mid-session is STALE", tnx_open["freshness"] == "STALE", tnx_open["freshness"])
check("55.6h US10Y mid-session is NOT usable", tnx_open["usable"] is False)

print("\n[FIX-1/2] closure never excuses genuinely missing data")
ancient = session_state("us10y", 10 * 24 * H, 6 * H, now=SUNDAY_NIGHT)
check("10-day-old value is STALE even on a weekend", ancient["freshness"] == "STALE",
      ancient["freshness"])
check("10-day-old value is not usable", ancient["usable"] is False)
unknown = session_state("candles", None, 5400.0, now=SUNDAY_NIGHT)
check("unknown age is never usable", unknown["usable"] is False)
check("unknown age is labelled", unknown["freshness"] == "UNKNOWN_AGE")

print("\n[FIX-1/2] futures are held to the live ceiling even at the weekend-open")
fut_ok = session_state("dxy", 0.2 * H, 6 * H, now=SUNDAY_NIGHT)
fut_bad = session_state("dxy", 20 * H, 6 * H, now=SUNDAY_NIGHT)
check("fresh futures value is LIVE", fut_ok["freshness"] == "LIVE", fut_ok["freshness"])
check("20h-old futures value while open is STALE", fut_bad["usable"] is False, str(fut_bad))

print("\n[FIX-1/2] the holiday calendar now exists and is declared")
summ = summarize(SUNDAY_NIGHT)
# V6.6.8: holidays ARE modelled now. The old assertion pinned the absence of the
# calendar, which is what allowed Labor Day 2026 to look like an open session.
check("holiday modelling honestly declared true", summ["holiday_calendar_modelled"] is True)
check("session phase is published", bool(summ.get("session_phase")), str(summ.get("session_phase")))
from fia.market_sessions import holiday_name as _hn
from datetime import date as _date
check("Labor Day 2026 is a known closure", _hn(_date(2026, 9, 7)) == "Labor Day")
check("a normal trading day is not a closure", _hn(_date(2026, 9, 8)) is None)

print("\n[FIX-1/2] premove age_gate consumes the session model")
g_weekend = age_gate({"name": "US10Y"}, {"us10y": 55.6 * H}, now=SUNDAY_NIGHT)
g_open = age_gate({"name": "US10Y"}, {"us10y": 55.6 * H}, now=WEDNESDAY_OPEN)
check("weekend: US10Y included", g_weekend["included"] is True, str(g_weekend))
check("weekend: reason names the closure",
      g_weekend["reason"] == "CURRENT_FOR_SESSION_MARKET_CLOSED", g_weekend["reason"])
check("open session: US10Y excluded", g_open["included"] is False, str(g_open))
check("critical source with unknown age still fails closed",
      age_gate({"name": "NQ structure"}, {}, now=SUNDAY_NIGHT)["included"] is False)

print("\n[FIX-3] the cognitive path now has an age gate at all")
from fia.cognitive.specialists import (  # noqa: E402
    SPECIALIST_AGE_CEILING, SPECIALIST_SOURCE, _freshness_gate,
)
check("specialists map to sources", SPECIALIST_SOURCE.get("Volatility & Options AI") == "volatility")
check("ceilings differ by source (not one threshold)",
      len(set(SPECIALIST_AGE_CEILING.values())) > 1)
gv = _freshness_gate("Volatility & Options AI", {"volatility": 54.3 * H})
check("gate returns a decision for a real specialist", "usable" in gv, str(gv))

print("\n[FIX-3] CORE PROOF: an expired signal cannot change cognitive reasoning")
import fia.cognitive.specialists as SP  # noqa: E402


class _FC:
    signals = []
    direction = "BULLISH"
    bullish_probability = 55.0


def _raw(vix_signal, vix_value, ages):
    return {"data": {"source_health": {k: {"age_seconds": v} for k, v in ages.items()},
                     "vix_signal": vix_signal, "vix_value": vix_value,
                     "us10y": 0.5, "dxy": 0.2, "mega_cap": -0.3, "semis": 0.6,
                     "breadth": -0.01, "nq_structure": 0.16, "spx_confirmation": -0.19,
                     "news": 0.5, "macro_status": "missing_event_calendar",
                     "earnings_status": "no_tracked_events",
                     "liquidity_evidence_available": True}}


STALE_AGES = {"market_quotes": 0.0, "candles": 0.0, "dxy": 700.0, "us10y": 0.0,
              "volatility": 54.3 * H, "news": 0.0, "macro": None,
              "earnings": None, "liquidity": 0.0}

# specialists imports session_state inside the function, so patch the source module.
import fia.market_sessions as MS  # noqa: E402
_orig_ss = MS.session_state
MS.session_state = lambda src, age, ceil, now=None: _orig_ss(src, age, ceil, now=WEDNESDAY_OPEN)
try:
    a = SP.build_specialists(_raw(-0.45, 28.0, STALE_AGES), _FC(), {"records": []})
    b = SP.build_specialists(_raw(+0.25, 12.0, STALE_AGES), _FC(), {"records": []})
finally:
    MS.session_state = _orig_ss

va = [v for v in a if v.name == "Volatility & Options AI"][0]
vb = [v for v in b if v.name == "Volatility & Options AI"][0]
check("stale specialist fails closed to MISSING", va.direction == "MISSING", va.direction)
check("stale specialist reliability is 0.0", float(va.reliability) == 0.0)
check("stale specialist uncertainty is 1.0", float(va.uncertainty) == 1.0)
check("flipping an EXPIRED input cannot change direction", va.direction == vb.direction)
check("flipping an EXPIRED input cannot change score", float(va.score) == float(vb.score))
check("withheld value preserved for audit", "withheld_score" in (vb.missing_reason or ""),
      (vb.missing_reason or "")[:80])
check("stale is NOT substituted with a neutral vote",
      float(va.probability_bullish) == 50.0 and float(va.reliability) == 0.0,
      "MISSING carries reliability 0.0, so the 50.0 placeholder carries no weight")

print("\n[FIX-3] during a CLOSED session the same specialist is admissible")
MS.session_state = lambda src, age, ceil, now=None: _orig_ss(src, age, ceil, now=SUNDAY_NIGHT)
try:
    c = SP.build_specialists(_raw(-0.45, 28.0, STALE_AGES), _FC(), {"records": []})
finally:
    MS.session_state = _orig_ss
vc = [v for v in c if v.name == "Volatility & Options AI"][0]
check("weekend: specialist is not force-excluded", vc.direction != "MISSING", vc.direction)

print("\n[FIX-5] NO_EDGE is recorded as a NON-DIRECTIONAL observation")
import fia.forward_oos as F  # noqa: E402

PREMOVE = {
    "state": "WATCH", "forecast_id": "pmw-regressiontest000000000",
    "evidence_hash": "abc123def456abc123def456", "regime": "BALANCED",
    "market_observation_utc": "2026-09-08T17:00:00+00:00",
    "evidence_quality": {"coverage": 0.92, "grade": "HIGH", "live_signal_count": 8,
                         "total_signal_count": 10, "degraded": False, "stale": False,
                         "age_excluded_signals": [], "market_session": {}},
    "horizons": {
        "4h": {"state": "NO_EDGE", "direction": "NO_EDGE", "actionable": False,
               "raw_probability": 50.44, "bullish_probability": 50.02,
               "bearish_probability": 49.98, "calibrated_bullish_probability": 50.02,
               "confidence": 0.14, "edge_points": 0.02, "evidence_direction": "BULLISH",
               "conviction_gate": {"reasons": ["edge_below_min:0.02<2.00"],
                                   "min_edge_points": 2.0, "min_confidence": 5.0},
               "confidence_basis": {"coverage": 0.92}},
        "8h": {"state": "NO_EDGE", "direction": "NO_EDGE", "actionable": False,
               "raw_probability": 49.43, "bullish_probability": 49.15,
               "bearish_probability": 50.85, "calibrated_bullish_probability": 49.15,
               "confidence": 4.12, "edge_points": 0.85, "evidence_direction": "BEARISH",
               "conviction_gate": {"reasons": ["confidence_below_min:4.12<5.00"],
                                   "min_edge_points": 2.0, "min_confidence": 5.0},
               "confidence_basis": {"coverage": 0.92}}}}
SNAP = {"data": {"provider_health": {"overall": "LIVE"},
                 "source_health": {"us10y": {"age_seconds": 200000}}},
        "cognitive": {"critic": {"severity": "LOW", "objections": ["ctx missing"]},
                      "hypotheses": {"bullish_hypothesis": {"strength": 2.24},
                                     "bearish_hypothesis": {"strength": 0.57}}}}

tmp = Path(tempfile.mkdtemp(prefix="abst_reg_"))
try:
    (tmp / "events").mkdir(parents=True)
    (tmp / "evidence").mkdir()
    test_seal_path = tmp / "FORWARD_OOS_CAMPAIGN_SEAL.json"
    test_seal = F.write_campaign_seal(test_seal_path)
    check("isolated abstention test seal valid", test_seal.get("ok") is True)
    _seal = F.verify_campaign_seal
    F.verify_campaign_seal = lambda *a, **k: _seal(test_seal_path)
    _cp = F.checkpoint_state
    F.checkpoint_state = lambda now=None: {
        "eligible_now": True, "checkpoint_date_et": "2026-09-08",
        "scheduled_checkpoint_et": "2026-09-08T13:00:00-04:00"}
    try:
        r = asyncio.run(F.lock_abstention_observation(None, SNAP, PREMOVE, tmp))
        dup = asyncio.run(F.lock_abstention_observation(None, SNAP, PREMOVE, tmp))
    finally:
        F.checkpoint_state = _cp
        F.verify_campaign_seal = _seal

    check("abstention record created", r.get("created") is True, json.dumps(r)[:160])
    check("tagged as an ABSTENTION observation", r.get("observation_type") == "ABSTENTION")
    check("duplicate refused", dup.get("created") is False
          and dup.get("reason") == "CHECKPOINT_ABSTENTION_ALREADY_RECORDED")

    events = sorted((tmp / "events").glob("*.json"))
    payload = json.loads(events[0].read_text())["payload"]
    ev_type = json.loads(events[0].read_text()).get("event_type")
    check("distinct event type", ev_type == "ABSTENTION_OBSERVATION", str(ev_type))
    check("directional flag false", payload["directional"] is False)
    check("not scoreable as directional", payload["scoreable_as_directional"] is False)
    check("excluded from directional statistics",
          payload["excluded_from_directional_statistics"] is True)
    check("no historical backfill", payload["eligibility"]["historical_backfill"] is False)

    for h, raw_p, pub_p in (("4h", 50.44, 50.02), ("8h", 49.43, 49.15)):
        cell = payload["horizons"][h]
        check("%s raw probability preserved" % h, cell["raw_probability"] == raw_p)
        check("%s published probability preserved" % h,
              cell["published_bullish_probability"] == pub_p)
        check("%s NOT rewritten to 50/50" % h, cell["published_bullish_probability"] != 50.0
              or cell["raw_probability"] != 50.0)
        check("%s NO_EDGE reasons stored" % h, len(cell["no_edge_reasons"]) > 0)
        check("%s never labelled BULLISH/BEARISH" % h,
              cell["direction"] == "NO_EDGE", cell["direction"])
        check("%s evidence direction retained separately" % h,
              cell["evidence_direction"] in ("BULLISH", "BEARISH"))

    check("evidence hash stored", payload["evidence_hash"] == "abc123def456abc123def456")
    check("freshness state stored", "evidence_quality" in payload)
    check("data quality stored", "provider_health" in payload["data_quality"])
    tb = payload["three_brain_conflict"]
    check("three-brain conflict captured", tb["bull_strength"] == 2.24
          and tb["bear_strength"] == 0.57 and tb["critic_severity"] == "LOW")

    v = F.verify_ledger(tmp)
    check("ledger remains valid", v["ok"] is True and v["issues"] == [], json.dumps(v)[:120])
    check("DIRECTIONAL SAMPLE UNCONTAMINATED (forecast_locks == 0)",
          v.get("forecast_locks") == 0, str(v.get("forecast_locks")))
    check("abstention still counted as a ledger event", v["events"] == 1, str(v["events"]))
finally:
    shutil.rmtree(tmp, ignore_errors=True)

print("\n[INVARIANT] production Forward-OOS history untouched by this test")
prod = F.verify_ledger(F.DEFAULT_ROOT)
check("production ledger still valid", prod["ok"] is True)
check("production directional locks unchanged at 0", prod.get("forecast_locks") == 0)

print("\n" + "=" * 62)
if FAILURES:
    print("FAILED %d check(s):" % len(FAILURES))
    for f in FAILURES:
        print("   -", f)
    sys.exit(1)
print("ALL V6.6.5 SESSION + ABSTENTION REGRESSION CHECKS PASSED")
