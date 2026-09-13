import asyncio
import json
import os
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
from dotenv import load_dotenv
from fia.artifact_guard import guarded_output_path

load_dotenv()

API_KEY = (
    os.getenv("POLYGON_API_KEY")
    or os.getenv("MASSIVE_API_KEY")
    or ""
).strip()

BASE = "https://api.massive.com"

OUTDIR = Path("fia_backtest_phase20/data")
CACHE_PATH = OUTDIR / "nq_5m_multicontract_20250901_20260831.json"

# Keep overlapping contracts around rollover periods.
# We do NOT create an adjusted continuous price series here.
# At forecast time, the liquidity adapter will choose the dominant
# contract using only cumulative volume available up to that timestamp,
# then use recent bars from that SAME contract.
CONTRACT_WINDOWS = {
    "NQU5": ("2025-09-01", "2025-09-20"),
    "NQZ5": ("2025-09-01", "2025-12-20"),
    "NQH6": ("2025-12-01", "2026-03-21"),
    "NQM6": ("2026-03-01", "2026-06-20"),
    "NQU6": ("2026-06-01", "2026-09-01"),
}

WINDOW_DAYS = 7
LIMIT = 50000


def parse_ns(value):
    try:
        ns = int(value)
    except Exception:
        return None

    # Massive Futures window_start is nanoseconds since Unix epoch.
    seconds = ns / 1_000_000_000
    return datetime.fromtimestamp(
        seconds,
        tz=timezone.utc,
    )


def bar_key(contract, row):
    return f"{contract}|{row.get('window_start')}"


def load_existing():
    if not CACHE_PATH.exists():
        return {}, {}

    try:
        payload = json.loads(
            CACHE_PATH.read_text(encoding="utf-8")
        )
    except Exception:
        return {}, {}

    bars = {}
    for row in payload.get("bars") or []:
        contract = row.get("contract")
        if contract and row.get("window_start") is not None:
            bars[bar_key(contract, row)] = row

    progress = payload.get("progress") or {}
    return bars, progress


def save_cache(bars, progress):
    ordered = sorted(
        bars.values(),
        key=lambda row: (
            int(row.get("window_start") or 0),
            str(row.get("contract") or ""),
        ),
    )

    # A6: sealed-artifact guard. This output is registered canonical
    # evidence, so a default run writes to a per-run directory instead.
    guarded_output_path(CACHE_PATH).write_text(
        json.dumps(
            {
                "provider": "Massive Futures",
                "symbol": "NQ",
                "resolution": "5min",
                "window_start": "2025-09-01",
                "window_end": "2026-08-31",
                "selection_rule": (
                    "Raw overlapping quarterly contracts are cached. "
                    "Point-in-time liquidity must choose one dominant "
                    "contract using cumulative volume available up to the "
                    "forecast timestamp, then use bars from that same contract."
                ),
                "contract_windows": CONTRACT_WINDOWS,
                "progress": progress,
                "bars": ordered,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


async def fetch_window(client, contract, start, end):
    params = {
        "resolution": "5min",
        "window_start.gte": start.isoformat(),
        "window_start.lt": end.isoformat(),
        "limit": LIMIT,
        "apiKey": API_KEY,
    }

    for attempt in range(1, 10):
        response = await client.get(
            f"{BASE}/futures/v1/aggs/{contract}",
            params=params,
        )

        if response.status_code == 200:
            payload = response.json()
            rows = payload.get("results") or []

            if len(rows) >= LIMIT:
                raise RuntimeError(
                    f"{contract} {start} -> {end} hit limit {LIMIT}; "
                    "reduce WINDOW_DAYS."
                )

            return rows

        if response.status_code in (403, 429, 500, 502, 503, 504):
            print(
                "RETRY",
                contract,
                start.date(),
                "->",
                end.date(),
                "| status =",
                response.status_code,
                "| attempt =",
                attempt,
            )
            await asyncio.sleep(min(60, attempt * 5))
            continue

        raise RuntimeError(
            f"{contract} HTTP {response.status_code}: "
            f"{response.text[:300]}"
        )

    raise RuntimeError(
        f"{contract} repeated failures for {start} -> {end}"
    )


def date_dt(value):
    return datetime.fromisoformat(
        value + "T00:00:00+00:00"
    )


async def main():
    if not API_KEY:
        raise SystemExit(
            "POLYGON_API_KEY / MASSIVE_API_KEY missing in .env"
        )

    OUTDIR.mkdir(parents=True, exist_ok=True)

    bars, progress = load_existing()

    print("=== PHASE 20 NQ 5M MULTI-CONTRACT CACHE ===")
    print("existing bars =", len(bars))
    print("cache =", CACHE_PATH)
    print()

    async with httpx.AsyncClient(timeout=30) as client:

        for contract, (start_s, end_s) in CONTRACT_WINDOWS.items():
            start = date_dt(start_s)
            end = date_dt(end_s)

            saved_until = progress.get(contract)

            if saved_until:
                try:
                    resume = datetime.fromisoformat(
                        str(saved_until).replace("Z", "+00:00")
                    )
                    if resume.tzinfo is None:
                        resume = resume.replace(tzinfo=timezone.utc)
                    current = max(start, resume.astimezone(timezone.utc))
                except Exception:
                    current = start
            else:
                current = start

            print(
                "CONTRACT",
                contract,
                "| requested =",
                start.date(),
                "->",
                end.date(),
                "| resume =",
                current.date(),
            )

            while current < end:
                window_end = min(
                    current + timedelta(days=WINDOW_DAYS),
                    end,
                )

                rows = await fetch_window(
                    client,
                    contract,
                    current,
                    window_end,
                )

                for raw in rows:
                    ts = parse_ns(raw.get("window_start"))
                    if ts is None:
                        continue

                    row = {
                        "contract": contract,
                        "window_start": int(raw.get("window_start")),
                        "timestamp": ts.isoformat(),
                        "open": raw.get("open"),
                        "high": raw.get("high"),
                        "low": raw.get("low"),
                        "close": raw.get("close"),
                        "volume": raw.get("volume"),
                    }

                    bars[bar_key(contract, row)] = row

                progress[contract] = window_end.isoformat()
                save_cache(bars, progress)

                print(
                    " ",
                    current.date(),
                    "->",
                    window_end.date(),
                    "| rows =",
                    len(rows),
                    "| total unique =",
                    len(bars),
                )

                current = window_end

                # Conservative pacing.
                await asyncio.sleep(0.20)

    # ----------------------------
    # Coverage / overlap audit
    # ----------------------------
    by_contract = defaultdict(list)

    for row in bars.values():
        by_contract[row["contract"]].append(row)

    print()
    print("=== CONTRACT COVERAGE ===")

    for contract in CONTRACT_WINDOWS:
        rows = sorted(
            by_contract.get(contract, []),
            key=lambda row: row["window_start"],
        )

        first = rows[0]["timestamp"] if rows else None
        last = rows[-1]["timestamp"] if rows else None

        print(
            contract,
            "| bars =",
            len(rows),
            "| first =",
            first,
            "| last =",
            last,
        )

    # Count timestamps where more than one quarterly contract exists.
    timestamp_contracts = defaultdict(set)

    for row in bars.values():
        timestamp_contracts[row["window_start"]].add(
            row["contract"]
        )

    overlap_timestamps = sum(
        len(contracts) > 1
        for contracts in timestamp_contracts.values()
    )

    # Weekday coverage: at least one NQ 5m bar on each weekday.
    days = defaultdict(int)

    for row in bars.values():
        day = row["timestamp"][:10]
        days[day] += 1

    start_day = datetime(2025, 9, 1).date()
    end_day = datetime(2026, 8, 31).date()

    zero_weekdays = []
    day = start_day

    while day <= end_day:
        if day.weekday() < 5 and days.get(day.isoformat(), 0) == 0:
            zero_weekdays.append(day.isoformat())
        day += timedelta(days=1)

    print()
    print("=== PHASE 20 NQ 5M CACHE SUMMARY ===")
    print("total_bars =", len(bars))
    print(
        "unique_timestamps =",
        len(timestamp_contracts),
    )
    print(
        "overlap_timestamps =",
        overlap_timestamps,
    )
    print(
        "weekday_zero_count =",
        len(zero_weekdays),
    )
    print(
        "weekday_zero_dates =",
        zero_weekdays,
    )
    print("cache =", CACHE_PATH)
    print(
        "=== PHASE 20 NQ 5M CACHE COMPLETE ==="
    )


if __name__ == "__main__":
    asyncio.run(main())
