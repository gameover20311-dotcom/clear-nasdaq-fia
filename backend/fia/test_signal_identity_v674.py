#!/usr/bin/env python3
"""V6.7.4 — CANONICAL SIGNAL IDENTITY REGRESSION SUITE

Guards the repair of a real, measured defect.

DEFECT
------
The equal-weighted participation signal was renamed from the misleading
"Breadth" to "Equal-weight participation". The rename reached fia/engine.py and
was aliased in fia/premove_watch.py, but four live consumers kept looking up the
legacy key, so on a FULLY HEALTHY snapshot (data_coverage == 1.0):

    premove _data_guard critical_missing == ['Breadth']   (permanently)
    usable leading weight                == 0.72          (intended 0.80)
    phase34 state['breadth']             == None          (permanently)
    phase33 live analog axis             == 0.0 while historical rows
                                            carried e.g. -0.5997

PROVENANCE
----------
ORIGIN_PRE_REPOSITORY / EXACT_DIVERGENCE_UNRECOVERABLE. The rename already
exists in the first repository commit (6b05d0b) and no commit, model-version
note or seal record documents it. This suite is part of the first fully
traceable repair of the inconsistency.

WHAT MUST NOT CHANGE
--------------------
The numeric weight vector, its 1.0 sum, and every forecast probability. Those
are asserted here against values captured from the UNPATCHED engine, so this
suite fails if the repair ever leaks into the science.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(BACKEND / "fia_backtest_phase22"))

from phase22_truth_consistency_test import base_data  # noqa: E402

from fia.engine import build_forecast  # noqa: E402
from fia import premove_engine as pe  # noqa: E402
from fia import phase33_analogs as pa  # noqa: E402
from fia.phase33_common import signal_map  # noqa: E402
from fia.models import Signal  # noqa: E402
from fia.signal_identity import (  # noqa: E402
    CANONICAL_EQUAL_WEIGHT_PARTICIPATION as CANON,
    alias_collisions,
    canonical_name_list,
    canonical_signal_name,
    canonicalize_signal_keys,
    is_equal_weight_participation,
)

CHECKS = []


def check(name, ok, detail=""):
    CHECKS.append((name, bool(ok), detail))
    print(("PASS  " if ok else "FAIL  ") + name + (("  -> " + str(detail)[:160]) if not ok else ""))


# Frozen behaviour captured from the UNPATCHED engine at commit ebaadf8.
FROZEN_SIGNALS = [
    ["DXY", 0.1, 0.08, "live"],
    ["Earnings/guidance", 0.0, 0.04, "live"],
    ["Equal-weight participation", -0.35, 0.08, "live"],
    ["Macro calendar", 0.0, 0.04, "live"],
    ["Mega-cap leadership", -0.45, 0.2, "live"],
    ["NQ structure", -0.55, 0.2, "live"],
    ["News", -0.2, 0.07, "live"],
    ["SPX confirmation", -0.4, 0.1, "live"],
    ["Semiconductors", -0.6, 0.12, "live"],
    ["US10Y", -0.3, 0.07, "live"],
]
FROZEN_PROBS = {"bullish": 30.6, "bearish": 69.4, "confidence": 72.1, "regime": "TREND"}

fc = build_forecast({"data": base_data()})
sigs = pe._signals_map(fc)
sm = signal_map(fc)

# ---------------------------------------------------------------- 1 + 10
# The numeric weight vector and every probability are unchanged by this repair.
actual_sig = sorted([s.name, round(float(s.score), 12), round(float(s.weight), 12), s.freshness]
                    for s in fc.signals)
check("1  numeric weight vector unchanged vs unpatched engine",
      actual_sig == sorted(FROZEN_SIGNALS), str(actual_sig))
check("10 no unrelated forecast/probability change",
      (fc.bullish_probability == FROZEN_PROBS["bullish"]
       and fc.bearish_probability == FROZEN_PROBS["bearish"]
       and getattr(fc, "confidence", None) == FROZEN_PROBS["confidence"]
       and str(getattr(fc, "regime", "")) == FROZEN_PROBS["regime"]),
      f"{fc.bullish_probability}/{fc.bearish_probability}/{getattr(fc,'confidence',None)}/{getattr(fc,'regime',None)}")

# ---------------------------------------------------------------- 2
check("2  total weights remain exactly 1.0",
      abs(sum(float(s.weight) for s in fc.signals) - 1.0) < 1e-9,
      str(sum(float(s.weight) for s in fc.signals)))

# ---------------------------------------------------------------- 3
guard = pe._data_guard(fc, sigs)
check("3  healthy input does not falsely report a missing critical signal",
      guard["critical_missing"] == [], str(guard["critical_missing"]))
check("3b legacy 'Breadth' never appears as a live signal key",
      "Breadth" not in sigs, sorted(sigs))

# ---------------------------------------------------------------- 4
usable = sum(sigs[n]["weight"] for n in pe.LEADING_SIGNAL_NAMES if n in sigs)
check("4  usable leading weight restored to 0.80 (was 0.72)",
      abs(usable - 0.80) < 1e-9, str(round(usable, 6)))

# ---------------------------------------------------------------- 5
check("5a participation signal emitted exactly once",
      sum(1 for s in fc.signals if is_equal_weight_participation(s.name)) == 1)
check("5b canonicalising both spellings yields ONE key",
      list(canonicalize_signal_keys({"Breadth": 0.4, CANON: 0.4}).keys()) == [CANON],
      str(canonicalize_signal_keys({"Breadth": 0.4, CANON: 0.4})))
check("5c double spelling is reported as a collision, never summed",
      alias_collisions({"Breadth": 0.4, CANON: 0.4}) == [CANON])
check("5d canonical axis list de-duplicates",
      canonical_name_list(["Breadth", CANON, "DXY"]) == [CANON, "DXY"],
      str(canonical_name_list(["Breadth", CANON, "DXY"])))
check("5e no alias collapses two distinct engine signals",
      len({canonical_signal_name(s.name) for s in fc.signals}) == len(fc.signals))
check("5f premove leading set holds participation exactly once",
      sum(1 for n in pe.LEADING_SIGNAL_NAMES if is_equal_weight_participation(n)) == 1)

# ---------------------------------------------------------------- 6
# Identical data, different spelling, must produce the identical analog vector.
payload = [{"name": "NQ structure", "score": -0.55}, {"name": "DXY", "score": 0.10}]
row_legacy = {"timestamp": "2026-01-01T00:00:00+00:00", "bullish_probability": 40,
              "confidence": 60, "score": -0.2, "regime": "TREND",
              "signals_json": json.dumps(payload + [{"name": "Breadth", "score": -0.5997}])}
row_canon = dict(row_legacy,
                 signals_json=json.dumps(payload + [{"name": CANON, "score": -0.5997}]))
check("6  historical 'Breadth' and live canonical give the SAME analog vector",
      pa._vec(row_legacy) == pa._vec(row_canon),
      f"{pa._vec(row_legacy)} vs {pa._vec(row_canon)}")

# ---------------------------------------------------------------- 7
check("7a CORE axes are canonical",
      CANON in pa.CORE and "Breadth" not in pa.CORE, str(pa.CORE))
axis = 3 + pa.CORE.index(CANON)
live_row = {"timestamp": "2026-06-01T17:00:00+00:00",
            "bullish_probability": fc.bullish_probability,
            "confidence": getattr(fc, "confidence", 50), "score": 0.0, "regime": "TREND",
            "signals_json": json.dumps([{"name": k, "score": v["score"]} for k, v in sm.items()])}
live_axis = pa._vec(live_row)[axis]
check("7b live analog axis is no longer forced to 0.0",
      abs(live_axis - (-0.35)) < 1e-9, str(live_axis))
check("7c identical spelling-variant rows are at distance 0",
      pa._vec(row_legacy) == pa._vec(row_canon))

# ---------------------------------------------------------------- 8
check("8  phase34 state vector receives the real participation score",
      sm.get(CANON, {}).get("score") == -0.35, str(sm.get(CANON)))

# ---------------------------------------------------------------- 9
# Abstention must change ONLY by no longer counting a present signal as absent.
# A genuinely absent critical signal must still be detected.
degraded = [s for s in fc.signals if not is_equal_weight_participation(s.name)]
degraded.append(Signal(name=CANON, score=0.0, weight=0.08,
                       detail="Awaiting provider data", freshness="missing"))


class _FC:
    signals = degraded
    data_coverage = fc.data_coverage
    intelligence_coverage = fc.intelligence_coverage


dg = pe._data_guard(_FC(), pe._signals_map(_FC()))
check("9a a genuinely missing participation signal is STILL flagged",
      dg["critical_missing"] == [CANON], str(dg["critical_missing"]))
check("9b guard still fails closed on 3+ genuinely missing critical signals",
      pe._data_guard(_FC(), {})["pass"] is False)

failed = [n for n, ok, _ in CHECKS if not ok]
print()
print("=" * 44)
if failed:
    print("V6.7.4 SIGNAL IDENTITY: FAIL")
    print("failed =", failed)
    raise SystemExit(1)
print(f"V6.7.4 SIGNAL IDENTITY: PASS  ({len(CHECKS)}/{len(CHECKS)})")
print("weight_vector_changed      = NO")
print("probability_math_changed   = NO")
print("abstention_identity_repaired = YES")
print("analog_coordinate_parity   = YES")
print("historical_files_rewritten = NO")
print("=" * 44)
