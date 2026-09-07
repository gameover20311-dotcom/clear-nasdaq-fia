import csv
from collections import Counter
from pathlib import Path

CSV_PATH = Path("fia_backtest_phase19/results/phase19_full_backtest.csv")


def pct(n, d):
    return None if not d else 100.0 * n / d


def fmt(v):
    return "N/A" if v is None else f"{v:.2f}%"


def direction(move, threshold):
    if move is None:
        return None
    if move > threshold:
        return "BULLISH"
    if move < -threshold:
        return "BEARISH"
    return "NEUTRAL"


def as_float(v):
    try:
        if v in ("", None, "None"):
            return None
        return float(v)
    except Exception:
        return None


def truthy(v):
    if v is None or v == "":
        return None
    return str(v).lower() == "true"


if not CSV_PATH.exists():
    raise SystemExit(f"Missing CSV: {CSV_PATH}")

with CSV_PATH.open(newline="", encoding="utf-8") as f:
    rows = list(csv.DictReader(f))

print("=== PHASE 19 DIAGNOSTICS ===")
print("rows =", len(rows))
print()

# 1) Missing news dates
missing_news = [r for r in rows if str(r.get("news_evidence", "")).lower() != "available"]
print("=== MISSING NEWS CHECKPOINTS ===")
print("count =", len(missing_news))
for r in missing_news:
    print(
        r["timestamp"][:10],
        "| news =", r.get("news"),
        "| polygon =", r.get("news_polygon_articles"),
        "| finnhub =", r.get("news_finnhub_articles"),
        "| pred =", r.get("predicted"),
    )
print()

# 2) Accuracy conditional on news availability
print("=== ACCURACY BY NEWS AVAILABILITY ===")
for label, subset in [
    ("NEWS AVAILABLE", [r for r in rows if str(r.get("news_evidence", "")).lower() == "available"]),
    ("NEWS MISSING", missing_news),
]:
    for h in ("4h", "8h"):
        resolved = [r for r in subset if truthy(r.get(f"correct_{h}")) is not None]
        correct = sum(truthy(r.get(f"correct_{h}")) is True for r in resolved)
        print(label, h.upper(), "| n =", len(resolved), "| accuracy =", fmt(pct(correct, len(resolved))))
print()

# 3) Liquidity usefulness
print("=== LIQUIDITY DIAGNOSTICS ===")
liq_counts = Counter(r.get("liquidity_direction") or "MISSING" for r in rows)
print("directions =", dict(liq_counts))
for direction_name in ("BULLISH", "BEARISH", "NEUTRAL"):
    subset = [r for r in rows if (r.get("liquidity_direction") or "") == direction_name]
    if not subset:
        continue
    for h in ("4h", "8h"):
        resolved = [r for r in subset if r.get(f"actual_{h}") not in ("", None)]
        if not resolved:
            continue
        aligned = sum(r.get(f"actual_{h}") == direction_name for r in resolved)
        print(
            direction_name,
            h.upper(),
            "| n =", len(resolved),
            "| liquidity aligned with actual =", fmt(pct(aligned, len(resolved))),
        )
print()

# 4) Neutral prediction failure analysis
print("=== NEUTRAL PREDICTION CASES ===")
neutral_rows = [r for r in rows if r.get("predicted") == "NEUTRAL"]
for r in neutral_rows:
    print(
        r["timestamp"][:10],
        "| score =", r.get("score"),
        "| conf =", r.get("confidence"),
        "| 4H =", r.get("actual_4h"),
        "| move4 =", r.get("move_4h_pct"),
        "| 8H =", r.get("actual_8h"),
        "| move8 =", r.get("move_8h_pct"),
        "| news =", r.get("news"),
        "| liq =", r.get("liquidity_direction"),
    )
print()

# 5) Confidence sanity
print("=== HIGH CONFIDENCE CHECK ===")
for cutoff in (60, 70):
    subset = [r for r in rows if (as_float(r.get("confidence")) or 0) >= cutoff]
    for h in ("4h", "8h"):
        resolved = [r for r in subset if truthy(r.get(f"correct_{h}")) is not None]
        correct = sum(truthy(r.get(f"correct_{h}")) is True for r in resolved)
        print(f">={cutoff}% confidence", h.upper(), "| n =", len(resolved), "| accuracy =", fmt(pct(correct, len(resolved))))
print()

# 6) Diagnostic-only neutral threshold sensitivity.
print("=== NEUTRAL THRESHOLD SENSITIVITY (DIAGNOSTIC ONLY) ===")
print("Do NOT optimize from this sample; this only shows whether neutral labeling is driving errors.")
for threshold in (0.02, 0.05, 0.10, 0.15):
    for h in ("4h", "8h"):
        move_key = f"move_{h}_pct"
        usable = []
        for r in rows:
            move = as_float(r.get(move_key))
            if move is None:
                continue
            actual = direction(move, threshold)
            usable.append((r.get("predicted"), actual))
        correct = sum(p == a for p, a in usable)
        dist = Counter(a for _, a in usable)
        print(
            f"threshold={threshold:.2f}% {h.upper()}",
            "| n =", len(usable),
            "| current-pred accuracy =", fmt(pct(correct, len(usable))),
            "| actual dist =", dict(dist),
        )
print()

# 7) Directional-only accuracy: ignores neutral predictions and neutral actual outcomes.
print("=== DIRECTIONAL-ONLY ACCURACY ===")
for h in ("4h", "8h"):
    subset = [
        r for r in rows
        if r.get("predicted") in ("BULLISH", "BEARISH")
        and r.get(f"actual_{h}") in ("BULLISH", "BEARISH")
    ]
    correct = sum(r.get("predicted") == r.get(f"actual_{h}") for r in subset)
    print(h.upper(), "| n =", len(subset), "| accuracy =", fmt(pct(correct, len(subset))))
print()

print("=== PHASE 19 DIAGNOSTICS COMPLETE ===")
