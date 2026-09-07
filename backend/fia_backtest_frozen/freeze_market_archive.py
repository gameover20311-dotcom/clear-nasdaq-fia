#!/usr/bin/env python3
"""Freeze every yfinance series the 258-row replay depends on.

WHY
---
The replay sourced its market evidence from
    yf.Ticker(t).history(period="2y", interval="1h")
    yf.Ticker("NQ=F").history(period="60d", interval="5m")
Both windows are RELATIVE TO THE RUN DATE, so the replay was a current-data
reconstruction rather than a frozen historical replay. Measured consequence on
row 1 (2025-09-01T17:00Z), same code, same frozen news/earnings/futures caches:

    score  -0.538 -> -0.527
    p_bull  26.1  ->  26.5
    conf    69.9  ->  69.2

Two further defects follow from the rolling window: the 2y lookback stops
reaching 2025-09-01 around late 2027, silently starving the earliest rows; and
the archive cannot be rebuilt identically once Yahoo revises a bar.

WHAT THIS WRITES
----------------
One CSV per ticker plus a manifest carrying a SHA256 over the exact bytes, so a
replay can assert it ran on the same inputs. Bars are stored verbatim as fetched
-- no adjustment, no gap filling, no interpolation. A missing bar stays missing.

This script REQUIRES the network and is run deliberately, not on import. The
replay itself must never call it.
"""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import yfinance as yf

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"
MANIFEST = HERE / "FROZEN_MARKET_MANIFEST.json"

SYMBOLS = ["NVDA", "MSFT", "AAPL", "AMZN", "META", "AVGO", "GOOGL", "GOOG", "TSLA",
           "NFLX", "AMD", "MU", "INTC", "QCOM", "SMCI"]
TICKERS = {"nq": "NQ=F", "qqq": "QQQ", "spy": "SPY", "dxy": "DX-Y.NYB",
           "us10y": "^TNX", **{s: s for s in SYMBOLS}}


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def freeze(period: str = "2y", interval: str = "1h") -> dict:
    DATA.mkdir(parents=True, exist_ok=True)
    entries = {}
    for key, ticker in sorted(TICKERS.items(), key=lambda kv: kv[1]):
        df = yf.Ticker(ticker).history(period=period, interval=interval,
                                       auto_adjust=False, prepost=False)
        safe = ticker.replace("=", "_").replace("^", "_").replace(".", "_")
        path = DATA / ("%s_%s.csv" % (safe, interval))
        if df is None or len(df) == 0:
            print("  %-10s EMPTY -- recorded as unavailable, NOT filled" % ticker)
            entries[ticker] = {"rows": 0, "file": path.name, "sha256": None,
                               "status": "UNAVAILABLE"}
            continue
        df.to_csv(path)
        entries[ticker] = {
            "rows": int(len(df)),
            "file": path.name,
            "sha256": _sha256(path),
            "first_bar": str(df.index[0]),
            "last_bar": str(df.index[-1]),
            "status": "FROZEN",
        }
        print("  %-10s %6d bars  %s .. %s" % (ticker, len(df), df.index[0], df.index[-1]))
    manifest = {
        "frozen_at_utc": datetime.now(timezone.utc).isoformat(),
        "interval": interval,
        "requested_period": period,
        "provider": "yfinance",
        "adjustment": "auto_adjust=False, prepost=False (raw prices, no split back-adjustment)",
        "note": ("Verbatim capture. No gap filling, no interpolation, no adjustment. "
                 "A missing bar stays missing so the replay fails closed rather than "
                 "inventing a price."),
        "tickers": entries,
    }
    blob = json.dumps(manifest, sort_keys=True, indent=1).encode()
    MANIFEST.write_bytes(blob)
    manifest["manifest_sha256"] = hashlib.sha256(blob).hexdigest()
    return manifest


if __name__ == "__main__":
    print("Freezing yfinance market archive (requires network)...")
    m = freeze()
    ok = sum(1 for v in m["tickers"].values() if v["status"] == "FROZEN")
    print("\nfrozen %d/%d tickers -> %s" % (ok, len(m["tickers"]), DATA))
    print("manifest: %s" % MANIFEST)
    sys.exit(0 if ok else 1)
