#!/usr/bin/env python3
# PHASE28_MARKET_GRADE_REPLAY_V1
from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Any, List

import httpx
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
OUT = Path(__file__).resolve().parent / "data"
OUT.mkdir(parents=True, exist_ok=True)
ES_PATH = OUT / "es_5m_multicontract_20250901_20260831.json"
MACRO_PATH = OUT / "finnhub_macro_calendar_20250901_20260831.json"
API_KEY = (os.getenv("POLYGON_API_KEY") or os.getenv("MASSIVE_API_KEY") or "").strip()
FINNHUB = (os.getenv("FINNHUB_API_KEY") or "").strip()
BASE = "https://api.massive.com"
UTC = timezone.utc

CONTRACT_WINDOWS = {
    "ESU5": ("2025-09-01", "2025-09-20"),
    "ESZ5": ("2025-09-01", "2025-12-20"),
    "ESH6": ("2025-12-01", "2026-03-21"),
    "ESM6": ("2026-03-01", "2026-06-20"),
    "ESU6": ("2026-06-01", "2026-09-01"),
}


def dt(s: str) -> datetime:
    return datetime.fromisoformat(s + "T00:00:00+00:00")


def bar_key(contract: str, row: Dict[str, Any]) -> str:
    return f"{contract}|{row.get('window_start')}"


def load_es():
    if not ES_PATH.exists():
        return {}, {}
    try:
        p = json.loads(ES_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}, {}
    bars = {bar_key(x.get("contract"), x): x for x in p.get("bars") or [] if x.get("contract") and x.get("window_start") is not None}
    return bars, p.get("progress") or {}


def save_es(bars, progress):
    ordered = sorted(bars.values(), key=lambda r: (int(r.get("window_start") or 0), str(r.get("contract") or "")))
    ES_PATH.write_text(json.dumps({
        "provider": "Massive Futures",
        "symbol": "ES",
        "resolution": "5min",
        "window_start": "2025-09-01",
        "window_end": "2026-08-31",
        "selection_rule": "Raw overlapping quarterly contracts. Point-in-time code selects dominant contract using only completed trailing 24h volume as-of each forecast timestamp.",
        "contract_windows": CONTRACT_WINDOWS,
        "progress": progress,
        "bars": ordered,
    }), encoding="utf-8")


async def prepare_es():
    if ES_PATH.exists():
        try:
            p = json.loads(ES_PATH.read_text())
            if len(p.get("bars") or []) > 50000:
                print("✅ ES 5m Massive cache already present | bars =", len(p.get("bars") or []))
                return True
        except Exception:
            pass
    if not API_KEY:
        print("⚠️ ES 5m cache unavailable: POLYGON_API_KEY/MASSIVE_API_KEY missing")
        return False
    bars, progress = load_es()
    async with httpx.AsyncClient(timeout=40) as client:
        for contract, (start_s, end_s) in CONTRACT_WINDOWS.items():
            start, end = dt(start_s), dt(end_s)
            cur = start
            if progress.get(contract):
                try:
                    cur = max(cur, datetime.fromisoformat(str(progress[contract]).replace("Z", "+00:00")))
                except Exception:
                    pass
            while cur < end:
                nxt = min(cur + timedelta(days=7), end)
                params = {
                    "resolution": "5min",
                    "window_start.gte": cur.isoformat(),
                    "window_start.lt": nxt.isoformat(),
                    "limit": 50000,
                    "apiKey": API_KEY,
                }
                rows = None
                for attempt in range(1, 8):
                    r = await client.get(f"{BASE}/futures/v1/aggs/{contract}", params=params)
                    if r.status_code == 200:
                        rows = r.json().get("results") or []
                        break
                    if r.status_code in {403,429,500,502,503,504}:
                        await asyncio.sleep(min(30, attempt*3)); continue
                    print(f"⚠️ ES {contract} HTTP {r.status_code}: {r.text[:180]}")
                    return False
                if rows is None:
                    print("⚠️ ES repeated provider failure", contract, cur.date(), nxt.date())
                    return False
                for raw in rows:
                    x = dict(raw); x["contract"] = contract
                    try:
                        x["timestamp"] = datetime.fromtimestamp(int(x["window_start"])/1_000_000_000, tz=UTC).isoformat()
                    except Exception:
                        pass
                    bars[bar_key(contract, x)] = x
                progress[contract] = nxt.isoformat()
                save_es(bars, progress)
                print("ES", contract, cur.date(), "->", nxt.date(), "bars =", len(rows), "total =", len(bars))
                cur = nxt
    print("✅ ES 5m Massive cache ready | bars =", len(bars))
    return len(bars) > 50000


async def prepare_macro():
    if MACRO_PATH.exists():
        try:
            p = json.loads(MACRO_PATH.read_text())
            if (p.get("events") or []) or p.get("status") == "unavailable_plan":
                print("ℹ️ Macro cache already inspected | status =", p.get("status"), "events =", len(p.get("events") or []))
                return p.get("status") == "available"
        except Exception:
            pass
    if not FINNHUB:
        MACRO_PATH.write_text(json.dumps({"source":"Finnhub Economic Calendar","status":"missing_key","events":[]}), encoding="utf-8")
        print("⚠️ Historical macro calendar missing: FINNHUB_API_KEY not configured")
        return False
    events: List[Dict[str, Any]] = []
    start = dt("2025-09-01")
    end = dt("2026-09-01")
    status = "available"
    async with httpx.AsyncClient(timeout=30) as client:
        cur = start
        while cur < end:
            nxt = min(cur + timedelta(days=28), end)
            r = await client.get("https://finnhub.io/api/v1/calendar/economic", params={
                "from": cur.date().isoformat(), "to": (nxt-timedelta(days=1)).date().isoformat(), "token": FINNHUB,
            })
            if r.status_code != 200:
                status = "unavailable_plan" if r.status_code in {401,403} else f"http_{r.status_code}"
                print("⚠️ Finnhub historical macro unavailable |", status)
                events = []
                break
            payload = r.json()
            batch = payload.get("economicCalendar") or []
            events.extend(x for x in batch if isinstance(x, dict))
            cur = nxt
    # dedupe deterministic
    seen=set(); dedup=[]
    for x in events:
        key=(str(x.get("time")),str(x.get("country")),str(x.get("event")))
        if key in seen: continue
        seen.add(key); dedup.append(x)
    MACRO_PATH.write_text(json.dumps({
        "source": "Finnhub Economic Calendar",
        "status": status if dedup else (status if status != "available" else "empty"),
        "window_start": "2025-09-01",
        "window_end": "2026-08-31",
        "point_in_time_rule": "Upcoming actual values are hidden until event timestamp. Calendar is used as catalyst timing only; no unvalidated directional macro score is injected.",
        "events": dedup,
    }), encoding="utf-8")
    if dedup:
        print("✅ Historical macro calendar cached | events =", len(dedup))
        return True
    print("⚠️ Historical macro calendar not available; Phase28 will mark macro missing, never neutral/fake")
    return False


async def main():
    print("=== PHASE 28 REAL DATA PREPARATION ===")
    es_ok = await prepare_es()
    macro_ok = await prepare_macro()
    print("ES_5M =", "READY" if es_ok else "MISSING")
    print("MACRO_CALENDAR =", "READY" if macro_ok else "MISSING_OR_PLAN_LIMIT")
    print("✅ Preparation complete — missing sources remain explicitly missing")

if __name__ == "__main__":
    asyncio.run(main())
