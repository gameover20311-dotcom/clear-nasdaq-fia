"""V6.6.9 frozen historical replay: determinism, fail-closed, leakage.

WHY THIS EXISTS
---------------
The 258-row replay sourced market evidence from yfinance with windows relative
to the RUN DATE (period="2y" / "60d"), so it was a current-data reconstruction,
not a frozen historical replay. Measured on row 1 (2025-09-01T17:00Z) with
identical code and identical frozen news/earnings/futures caches:

    score  -0.538 -> -0.527
    p_bull  26.1  ->  26.5
    conf    69.9  ->  69.2

Direction, coverage and regime matched, so nothing was broken -- Yahoo's
historical intraday values had simply drifted. A backtest whose inputs change
between runs cannot be certified however correct its cutoffs are.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import pandas as pd                                                  # noqa: E402

import fia_backtest_phase19.full_snapshot as fs                      # noqa: E402
from fia_backtest_phase20.earnings_pti import earnings_point_in_time  # noqa: E402
from fia_backtest_phase21.full_backtest import news_window_asof      # noqa: E402

FAILURES = []


def check(name, cond, detail=""):
    if cond:
        print("  PASS  %s" % name)
    else:
        print("  FAIL  %s   %s" % (name, detail))
        FAILURES.append(name)


ARCHIVE = BACKEND / "fia_backtest_frozen"
MANIFEST = ARCHIVE / "FROZEN_MARKET_MANIFEST.json"
T = datetime(2025, 9, 1, 17, 0, tzinfo=timezone.utc)

print("\n[A] THE FROZEN ARCHIVE EXISTS AND MATCHES ITS MANIFEST")
check("[A1] manifest present", MANIFEST.exists(), str(MANIFEST))
man = json.loads(MANIFEST.read_text()) if MANIFEST.exists() else {"tickers": {}}
check("[A2] every production ticker is frozen", len(man["tickers"]) >= 20,
      str(len(man["tickers"])))
bad = []
for tk, meta in man["tickers"].items():
    p = ARCHIVE / "data" / meta["file"]
    if not p.exists() or meta.get("sha256") is None:
        bad.append(tk + ":missing")
        continue
    if hashlib.sha256(p.read_bytes()).hexdigest() != meta["sha256"]:
        bad.append(tk + ":hash")
check("[A3] no file drifted from its recorded sha256", not bad, str(bad[:5]))
check("[A4] capture is raw, unadjusted (no split back-adjustment hindsight)",
      "auto_adjust=False" in str(man.get("adjustment", "")))
check("[A5] the archive records that gaps are NOT filled",
      "no gap filling" in str(man.get("note", "")).lower())

print("\n[B] REPLAY IS DETERMINISTIC ON THE FROZEN ARCHIVE")


def market_digest():
    fs.hist1h.cache_clear()
    rows = []
    cur = T
    end = datetime(2026, 8, 31, 17, 0, tzinfo=timezone.utc)
    while cur <= end:
        if cur.weekday() < 5:
            m = fs.market_asof(cur)
            rows.append({"t": cur.isoformat(),
                         **{k: m.get(k) for k in ("nq_structure", "spx_confirmation",
                                                  "mega_cap", "semis", "breadth",
                                                  "dxy", "us10y", "price")}})
        cur += timedelta(days=1)
    blob = json.dumps(rows, sort_keys=True, default=str)
    return hashlib.sha256(blob.encode()).hexdigest(), rows


d1, rows1 = market_digest()
d2, rows2 = market_digest()
check("[B1] two independent passes produce the same digest", d1 == d2, "%s vs %s" % (d1[:16], d2[:16]))
check("[B2] every row is identical field-for-field", rows1 == rows2)
check("[B3] the window is fully covered (no silently empty rows)",
      all(r["nq_structure"] is not None for r in rows1),
      "%d/%d usable" % (sum(1 for r in rows1 if r["nq_structure"] is not None), len(rows1)))
check("[B4] the expected checkpoint count is produced", len(rows1) == 261, str(len(rows1)))

print("\n[C] A MISSING ARCHIVE FAILS CLOSED, IT DOES NOT REFETCH")
orig = fs._FROZEN_DIR
fs._FROZEN_DIR = orig.parent / "__absent__"
fs.hist1h.cache_clear()
raised = None
try:
    fs.hist1h("QQQ")
except RuntimeError as exc:
    raised = str(exc)
check("[C1] a missing archive raises rather than refetching", raised is not None)
check("[C2] the error names the archive and the reproducibility risk",
      raised is not None and "FROZEN_HISTORICAL_ARCHIVE_MISSING" in raised
      and "reproducible" in raised.lower(), (raised or "")[:90])
os.environ["FIA_ALLOW_LIVE_HISTORICAL_REFETCH"] = "1"
check("[C3] the live escape hatch exists but must be set deliberately",
      fs._live_refetch_allowed() is True)
os.environ.pop("FIA_ALLOW_LIVE_HISTORICAL_REFETCH", None)
check("[C4] the escape hatch is OFF by default", fs._live_refetch_allowed() is False)
fs._FROZEN_DIR = orig
fs.hist1h.cache_clear()

print("\n[D] POINT-IN-TIME LEAKAGE ATTACKS")
idx = pd.to_datetime([T - timedelta(hours=2), T - timedelta(hours=1), T,
                      T + timedelta(hours=1)], utc=True)
adm = fs.asof(pd.DataFrame({"Close": [1, 2, 3, 4]}, index=idx), T, 60)
check("[D1] a future bar (T+1h) is rejected",
      not any(i > pd.Timestamp(T) for i in adm.index))
check("[D2] the FORMING bar (starts at T, ends T+1h) is rejected",
      not any(i == pd.Timestamp(T) for i in adm.index))
check("[D3] only completed bars survive: bar_start + interval <= T", len(adm) == 2, str(len(adm)))

ep = [(T - timedelta(hours=5)).timestamp(), (T - timedelta(hours=1)).timestamp(),
      (T + timedelta(hours=3)).timestamp()]
kept = news_window_asof(T, [(e, i, {"id": i}) for i, e in enumerate(ep)], ep)
check("[D4] an article published after T is rejected", all(k["id"] != 2 for k in kept),
      str([k["id"] for k in kept]))
check("[D5] articles published at/before T are kept", len(kept) == 2)

evp = BACKEND / "fia_backtest_phase20/data/earnings_events_sec_verified_20250901_20260831.json"
if evp.exists():
    ev = json.loads(evp.read_text())
    ev = ev if isinstance(ev, list) else ev.get("events", [])
    e0 = sorted(ev, key=lambda x: x["reveal_at"])[0]
    rt = datetime.fromisoformat(e0["reveal_at"].replace("Z", "+00:00"))
    check("[D6] earnings are INVISIBLE 5 min before reveal_at",
          earnings_point_in_time(rt - timedelta(minutes=5)).get("earnings") is None)
    check("[D7] earnings become visible 5 min after reveal_at",
          earnings_point_in_time(rt + timedelta(minutes=5)).get("earnings") is not None)
    check("[D8] reveal_at is a real SEC-derived timestamp, not a date",
          "T" in str(e0["reveal_at"]) and e0.get("sec_accession"), str(e0["reveal_at"]))

print("\n[E] NO SILENT SUBSTITUTION OF CURRENT DATA FOR HISTORY")
src = Path(fs.__file__).read_text()
# Inspect the FUNCTION BODY, not the module text: the rationale comment above
# also mentions period="2y" and would match first.
import inspect as _inspect                                           # noqa: E402
_h1 = _inspect.getsource(fs.hist1h.__wrapped__ if hasattr(fs.hist1h, "__wrapped__")
                         else fs.hist1h)
check("[E1] hist1h reads the archive before any network call",
      "_load_frozen(ticker" in _h1
      and _h1.index("_load_frozen(ticker") < _h1.index('period="2y"'),
      _h1[:80])
check("[E1b] the network call is unreachable unless the archive is absent",
      _h1.index("_live_refetch_allowed") < _h1.index("yf.Ticker"))
check("[E2] the live path announces that the run is not reproducible",
      "THIS RUN IS NOT" in src)
check("[E3] nq5m records its real coverage gap rather than hiding it",
      "NEVER covered" in src)

print("\n" + "=" * 66)
if FAILURES:
    print("FAILED %d check(s):" % len(FAILURES))
    for f in FAILURES:
        print("   -", f)
    sys.exit(1)
print("ALL V6.6.9 FROZEN-REPLAY CHECKS PASSED  (market digest %s)" % d1[:16])
