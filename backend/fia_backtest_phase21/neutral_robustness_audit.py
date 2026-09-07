import csv
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

CSV_PATH = Path(
    "fia_backtest_phase20/results/phase20_full_backtest_1y.csv"
)

BANDS = {
    "ORIGINAL_5PP": 5.0,
    "NO_NEUTRAL_0PP": 0.0,
}


def parse_float(value):
    try:
        if value is None or str(value).strip() == "":
            return None
        return float(value)
    except Exception:
        return None


def parse_ts(value):
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(
            str(value).replace("Z", "+00:00")
        )
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def predict(bullish_probability, band):
    if bullish_probability >= 50.0 + band:
        return "BULLISH"
    if bullish_probability <= 50.0 - band:
        return "BEARISH"
    return "NEUTRAL"


def load_rows():
    with CSV_PATH.open(
        newline="",
        encoding="utf-8",
    ) as handle:
        rows = []

        for row in csv.DictReader(handle):
            ts = parse_ts(row.get("timestamp"))
            bull = parse_float(
                row.get("bullish_probability")
            )
            conf = parse_float(
                row.get("confidence")
            )

            if ts is None or bull is None:
                continue

            item = dict(row)
            item["_ts"] = ts
            item["_bull"] = bull
            item["_conf"] = conf
            rows.append(item)

    rows.sort(key=lambda r: r["_ts"])
    return rows


def stats(rows, horizon, band):
    actual_key = f"actual_{horizon}"

    n = correct = 0
    pred_counts = defaultdict(int)

    for row in rows:
        actual = str(
            row.get(actual_key) or ""
        ).strip().upper()

        if actual not in (
            "BULLISH",
            "BEARISH",
            "NEUTRAL",
        ):
            continue

        pred = predict(
            row["_bull"],
            band,
        )

        n += 1
        pred_counts[pred] += 1

        if pred == actual:
            correct += 1

    return {
        "n": n,
        "correct": correct,
        "accuracy": (
            100.0 * correct / n
            if n
            else None
        ),
        "pred_counts": dict(pred_counts),
    }


def confidence_stats(
    rows,
    horizon,
    band,
    threshold,
):
    selected = [
        row
        for row in rows
        if (
            row["_conf"] is not None
            and row["_conf"] >= threshold
        )
    ]

    return stats(
        selected,
        horizon,
        band,
    )


def fmt(result):
    if result["accuracy"] is None:
        return "NA"
    return (
        f"{result['accuracy']:.2f}% "
        f"(n={result['n']}, "
        f"correct={result['correct']})"
    )


def main():
    rows = load_rows()

    print(
        "=== PHASE 21 NEUTRAL ROBUSTNESS AUDIT ==="
    )
    print("rows =", len(rows))
    print()

    # --------------------------------------------------
    # FULL SAMPLE
    # --------------------------------------------------
    print("=== FULL SAMPLE ===")

    for horizon in ("4h", "8h"):
        print(horizon.upper())

        for name, band in BANDS.items():
            result = stats(
                rows,
                horizon,
                band,
            )

            print(
                name,
                "|",
                fmt(result),
                "| predictions =",
                result["pred_counts"],
            )

    # --------------------------------------------------
    # MONTH BY MONTH
    # --------------------------------------------------
    print()
    print("=== MONTH-BY-MONTH ROBUSTNESS ===")

    by_month = defaultdict(list)

    for row in rows:
        by_month[
            row["_ts"].strftime("%Y-%m")
        ].append(row)

    improved_4h = tied_4h = worse_4h = 0
    improved_8h = tied_8h = worse_8h = 0

    for month in sorted(by_month):
        sample = by_month[month]

        old4 = stats(
            sample,
            "4h",
            5.0,
        )
        new4 = stats(
            sample,
            "4h",
            0.0,
        )

        old8 = stats(
            sample,
            "8h",
            5.0,
        )
        new8 = stats(
            sample,
            "8h",
            0.0,
        )

        if (
            old4["accuracy"] is not None
            and new4["accuracy"] is not None
        ):
            if new4["accuracy"] > old4["accuracy"]:
                improved_4h += 1
            elif new4["accuracy"] == old4["accuracy"]:
                tied_4h += 1
            else:
                worse_4h += 1

        if (
            old8["accuracy"] is not None
            and new8["accuracy"] is not None
        ):
            if new8["accuracy"] > old8["accuracy"]:
                improved_8h += 1
            elif new8["accuracy"] == old8["accuracy"]:
                tied_8h += 1
            else:
                worse_8h += 1

        print(
            month,
            "| 4H",
            f"{old4['accuracy']:.2f}% -> {new4['accuracy']:.2f}%",
            f"(n={new4['n']})",
            "| 8H",
            (
                f"{old8['accuracy']:.2f}% -> "
                f"{new8['accuracy']:.2f}%"
                if (
                    old8["accuracy"] is not None
                    and new8["accuracy"] is not None
                )
                else "NA"
            ),
            f"(n={new8['n']})",
        )

    print()
    print("monthly_4H_improved =", improved_4h)
    print("monthly_4H_tied =", tied_4h)
    print("monthly_4H_worse =", worse_4h)

    print("monthly_8H_improved =", improved_8h)
    print("monthly_8H_tied =", tied_8h)
    print("monthly_8H_worse =", worse_8h)

    # --------------------------------------------------
    # REGIME ROBUSTNESS
    # --------------------------------------------------
    print()
    print("=== REGIME ROBUSTNESS ===")

    by_regime = defaultdict(list)

    for row in rows:
        by_regime[
            str(row.get("regime") or "UNKNOWN")
        ].append(row)

    for regime in sorted(
        by_regime,
        key=lambda key: -len(by_regime[key]),
    ):
        sample = by_regime[regime]

        old4 = stats(sample, "4h", 5.0)
        new4 = stats(sample, "4h", 0.0)
        old8 = stats(sample, "8h", 5.0)
        new8 = stats(sample, "8h", 0.0)

        print(
            regime,
            "| rows =",
            len(sample),
            "| 4H",
            (
                f"{old4['accuracy']:.2f}% -> "
                f"{new4['accuracy']:.2f}%"
            ),
            "| 8H",
            (
                f"{old8['accuracy']:.2f}% -> "
                f"{new8['accuracy']:.2f}%"
                if (
                    old8["accuracy"] is not None
                    and new8["accuracy"] is not None
                )
                else "NA"
            ),
        )

    # --------------------------------------------------
    # HIGH-CONFIDENCE ROBUSTNESS
    # --------------------------------------------------
    print()
    print("=== HIGH-CONFIDENCE ROBUSTNESS ===")

    for threshold in (
        60,
        65,
        70,
    ):
        old4 = confidence_stats(
            rows,
            "4h",
            5.0,
            threshold,
        )
        new4 = confidence_stats(
            rows,
            "4h",
            0.0,
            threshold,
        )

        old8 = confidence_stats(
            rows,
            "8h",
            5.0,
            threshold,
        )
        new8 = confidence_stats(
            rows,
            "8h",
            0.0,
            threshold,
        )

        print(
            f">={threshold}% confidence",
            "| 4H",
            (
                f"{old4['accuracy']:.2f}% -> "
                f"{new4['accuracy']:.2f}%"
            ),
            f"(n={new4['n']})",
            "| 8H",
            (
                f"{old8['accuracy']:.2f}% -> "
                f"{new8['accuracy']:.2f}%"
                if (
                    old8["accuracy"] is not None
                    and new8["accuracy"] is not None
                )
                else "NA"
            ),
            f"(n={new8['n']})",
        )

    print()
    print("=== ROBUSTNESS VERDICT INPUTS ===")
    print(
        "Adopt no-neutral only if improvement is broad "
        "across months/regimes and does not damage high-confidence performance."
    )
    print(
        "=== PHASE 21 NEUTRAL ROBUSTNESS AUDIT COMPLETE ==="
    )


if __name__ == "__main__":
    main()
