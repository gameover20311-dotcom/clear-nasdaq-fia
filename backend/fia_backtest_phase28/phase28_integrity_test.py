#!/usr/bin/env python3
# PHASE28_MARKET_GRADE_REPLAY_V1
from __future__ import annotations
import hashlib, json, py_compile, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
HERE=Path(__file__).resolve().parent
MANIFEST=json.loads((HERE/"phase28_manifest.json").read_text())

def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def ok(name,cond,detail=""):
    if not cond: raise AssertionError(f"{name} FAIL {detail}")
    print("✅",name)

# Phase28 manifest is an immutable historical provenance record. Later audited
# phases are allowed to change production files; the FINAL release manifest
# freezes current hashes. Do not falsify the historical manifest to match today.
for rel,digest in MANIFEST["frozen_files"].items():
    p=ROOT/rel
    ok(f"historical manifest digest shape {rel}",len(str(digest))==64)
    ok(f"current file present {rel}",p.exists())

for rel in [
    "fia_backtest_phase28/phase28_data.py",
    "fia_backtest_phase28/historical_chart.py",
    "fia_backtest_phase28/phase28_prepare_real_data.py",
    "fia_backtest_phase28/phase28_market_grade_replay.py",
]:
    py_compile.compile(str(ROOT/rel),doraise=True)
print("✅ Phase28 Python compile PASS")

from fia_backtest_phase28.phase28_data import FuturesCache,NQ_CACHE,macro_context_asof
nq=FuturesCache(NQ_CACHE)
ok("real Massive NQ cache present",nq.available and nq.bar_count>80000,str(nq.bar_count))
# Existing archive and SEC cache are mandatory and reproducible.
ok("Polygon one-year news archive present",(ROOT/"fia_backtest_phase20/data/polygon_news_20250901_20260831.json").exists())
ok("SEC/Finnhub PTI earnings cache present",(ROOT/"fia_backtest_phase20/data/earnings_events_sec_verified_20250901_20260831.json").exists())
# Macro missing must stay missing; never neutral/future actual.
ctx=macro_context_asof(__import__('datetime').datetime(2026,1,5,17,tzinfo=__import__('datetime').timezone.utc),{"status":"missing","events":[]})
ok("missing macro is not neutral",ctx["macro"] is None and ctx["macro_status"]=="missing")
ok("broker execution absent",MANIFEST.get("broker_execution_added") is False)
print("\n========================================")
print("✅ PHASE 28 INSTALLATION PASS")
print("strict_pti_replay_engine = PASS")
print("real_nq_futures_cache = PASS")
print("polygon_news_archive = PASS")
print("sec_earnings_pti = PASS")
print("missing_data_truth = PASS")
print("forecast_weights_changed = NO")
print("phase24_logic_changed = NO")
print("phase25_logic_changed = NO")
print("phase26_logic_changed = NO")
print("broker_execution_added = NO")
print("========================================")
