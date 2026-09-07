import csv
import json
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

EARNINGS_PATH = Path(
    "fia_backtest_phase19/data/earnings_events_sec_verified.json"
)
BACKTEST_PATH = Path(
    "fia_backtest_phase19/results/phase19_full_backtest.csv"
)

CHECKPOINT_HOUR_UTC = 17

MEGA_CAP_WEIGHTS = {
    "NVDA": 0.14,
    "MSFT": 0.10,
    "AAPL": 0.09,
    "AMZN": 0.08,
    "META": 0.07,
    "AVGO": 0.06,
    "GOOGL": 0.06,
    "GOOG": 0.04,
    "ALPHABET": 0.10,  # GOOGL + GOOG combined live-project weight
    "TSLA": 0.04,
    "NFLX": 0.03,
}

SEMI_SYMBOLS = {
    "NVDA", "AVGO", "AMD", "MU", "INTC", "QCOM", "SMCI"
}


def parse_dt(value):
    if not value:
        return None
    raw = str(value).replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(raw)
    except Exception:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def yesno(value):
    if value in ("", None):
        return "NA"
    return "YES" if str(value).lower() == "true" else "NO"


if not EARNINGS_PATH.exists():
    raise SystemExit(f"Missing: {EARNINGS_PATH}")

if not BACKTEST_PATH.exists():
    raise SystemExit(f"Missing: {BACKTEST_PATH}")

earnings_payload = json.loads(
    EARNINGS_PATH.read_text(encoding="utf-8")
)
events = earnings_payload.get("events") or []

with BACKTEST_PATH.open(
    newline="",
    encoding="utf-8",
) as handle:
    rows = list(csv.DictReader(handle))

rows_by_date = {
    row["timestamp"][:10]: row
    for row in rows
}

print("=== PHASE 19 EARNINGS HORIZON AUDIT ===")
print("verified earnings events =", len(events))
print("checkpoint =", f"{CHECKPOINT_HOUR_UTC:02d}:00 UTC")
print()

within4 = []
within8 = []
after8 = []
before_checkpoint = []

for event in events:
    reveal = parse_dt(event.get("reveal_at"))
    if reveal is None:
        continue

    checkpoint = reveal.replace(
        hour=CHECKPOINT_HOUR_UTC,
        minute=0,
        second=0,
        microsecond=0,
    )

    delta_hours = (
        reveal - checkpoint
    ).total_seconds() / 3600.0

    item = {
        **event,
        "_reveal": reveal,
        "_checkpoint": checkpoint,
        "_delta_hours": delta_hours,
    }

    if 0 <= delta_hours <= 4:
        within4.append(item)
        within8.append(item)
    elif 4 < delta_hours <= 8:
        within8.append(item)
    elif delta_hours > 8:
        after8.append(item)
    else:
        before_checkpoint.append(item)

print("=== HORIZON COUNTS ===")
print("within next 4H =", len(within4))
print("within next 8H =", len(within8))
print("after 8H =", len(after8))
print("already public before checkpoint =", len(before_checkpoint))
print()

print("=== VERIFIED EVENTS INSIDE NEXT 4H ===")

for event in sorted(
    within4,
    key=lambda e: e["_reveal"],
):
    symbol = event.get("symbol")
    day = event["_checkpoint"].date().isoformat()
    row = rows_by_date.get(day, {})

    mega_weight = MEGA_CAP_WEIGHTS.get(symbol, 0.0)
    is_semi = (
        symbol in SEMI_SYMBOLS
        or symbol == "ALPHABET" and False
    )

    print(
        day,
        "|", symbol,
        "| reveal =", event["_reveal"].isoformat(),
        "| in =", round(event["_delta_hours"], 2), "h",
        "| mega_weight =", mega_weight,
        "| semi =", "YES" if is_semi else "NO",
        "| EPS =", event.get("surprise_direction"),
        "| FIA =", row.get("predicted", "NO_ROW"),
        "| conf =", row.get("confidence", ""),
        "| actual4 =", row.get("actual_4h", ""),
        "| correct4 =", yesno(row.get("correct_4h")),
        "| actual8 =", row.get("actual_8h", ""),
        "| correct8 =", yesno(row.get("correct_8h")),
    )

print()

print("=== EVENT-DAY PERFORMANCE ===")

event_dates = sorted({
    event["_checkpoint"].date().isoformat()
    for event in within8
})

event_rows = [
    rows_by_date[day]
    for day in event_dates
    if day in rows_by_date
]

non_event_rows = [
    row
    for row in rows
    if row["timestamp"][:10] not in set(event_dates)
]


def accuracy(subset, horizon):
    key = f"correct_{horizon}"
    vals = []
    for row in subset:
        value = row.get(key)
        if value in ("", None):
            continue
        vals.append(
            str(value).lower() == "true"
        )
    if not vals:
        return None, 0
    return 100.0 * sum(vals) / len(vals), len(vals)


for label, subset in [
    ("EARNINGS-IN-HORIZON DAYS", event_rows),
    ("OTHER DAYS", non_event_rows),
]:
    a4, n4 = accuracy(subset, "4h")
    a8, n8 = accuracy(subset, "8h")

    print(
        label,
        "| 4H n =", n4,
        "| 4H accuracy =",
        "N/A" if a4 is None else f"{a4:.2f}%",
        "| 8H n =", n8,
        "| 8H accuracy =",
        "N/A" if a8 is None else f"{a8:.2f}%",
    )

print()

print("=== IMPACT SUMMARY ===")

mega_events = [
    e for e in within8
    if e.get("symbol") in MEGA_CAP_WEIGHTS
]

semi_events = [
    e for e in within8
    if e.get("symbol") in SEMI_SYMBOLS
]

print(
    "mega-cap earnings inside 8H =",
    len(mega_events),
)
print(
    "semiconductor earnings inside 8H =",
    len(semi_events),
)

by_date_weight = defaultdict(float)
by_date_symbols = defaultdict(list)

for event in within8:
    day = event["_checkpoint"].date().isoformat()
    symbol = event.get("symbol")
    by_date_weight[day] += MEGA_CAP_WEIGHTS.get(
        symbol,
        0.0,
    )
    by_date_symbols[day].append(symbol)

for day in sorted(by_date_symbols):
    print(
        day,
        "| symbols =",
        ",".join(by_date_symbols[day]),
        "| combined live mega-cap weight =",
        round(by_date_weight[day], 3),
    )

print()
print("=== AUDIT CONCLUSION INPUTS ===")
print(
    "If most SEC-verified releases sit inside +4H/+8H, "
    "they should be treated as upcoming catalyst risk, "
    "not as a directional EPS-surprise signal before reveal."
)
print(
    "Future actual/estimate remains unavailable until reveal_at."
)
print("=== EARNINGS HORIZON AUDIT COMPLETE ===")
