import csv
import math
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

CSV_PATH = Path(
    "fia_backtest_phase20/results/phase20_full_backtest_1y.csv"
)

DEV_END = datetime(
    2026, 4, 30, 23, 59, 59,
    tzinfo=timezone.utc,
)

CALIBRATION_SLOPES = [
    0.50, 0.60, 0.70, 0.80, 0.90,
    1.00, 1.10, 1.20, 1.30,
]


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
            dt = dt.replace(
                tzinfo=timezone.utc
            )
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def load_rows():
    rows = []

    with CSV_PATH.open(
        newline="",
        encoding="utf-8",
    ) as handle:
        for row in csv.DictReader(handle):
            ts = parse_ts(
                row.get("timestamp")
            )
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

    rows.sort(
        key=lambda row: row["_ts"]
    )

    return rows


def recalibrate_probability(pct, slope):
    """
    Shrink or expand probability around 50 without changing sign.
    slope < 1.0 = less extreme / more conservative.
    slope > 1.0 = more extreme.
    """
    calibrated = (
        50.0
        + slope * (float(pct) - 50.0)
    )

    return max(
        0.1,
        min(
            99.9,
            calibrated,
        ),
    )


def brier(rows, horizon, slope=1.0):
    actual_key = f"actual_{horizon}"

    values = []

    for row in rows:
        actual = str(
            row.get(actual_key) or ""
        ).strip().upper()

        if actual not in (
            "BULLISH",
            "BEARISH",
        ):
            continue

        p = (
            recalibrate_probability(
                row["_bull"],
                slope,
            )
            / 100.0
        )

        y = (
            1.0
            if actual == "BULLISH"
            else 0.0
        )

        values.append(
            (p - y) ** 2
        )

    if not values:
        return None, 0

    return (
        sum(values) / len(values),
        len(values),
    )


def directional_accuracy(
    rows,
    horizon,
):
    actual_key = f"actual_{horizon}"

    n = correct = 0

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

        pred = (
            "BULLISH"
            if round(
                row["_bull"],
                1,
            ) >= 50.0
            else "BEARISH"
        )

        n += 1

        if pred == actual:
            correct += 1

    return (
        100.0 * correct / n
        if n
        else None,
        n,
    )


def by_regime(rows, horizon):
    groups = defaultdict(list)

    for row in rows:
        groups[
            str(
                row.get("regime")
                or "UNKNOWN"
            )
        ].append(row)

    result = []

    for regime, sample in groups.items():
        acc, n = directional_accuracy(
            sample,
            horizon,
        )

        confs = [
            row["_conf"]
            for row in sample
            if row["_conf"] is not None
        ]

        bulls = [
            row["_bull"]
            for row in sample
        ]

        avg_conf = (
            sum(confs) / len(confs)
            if confs
            else None
        )

        avg_distance = (
            sum(
                abs(p - 50.0)
                for p in bulls
            )
            / len(bulls)
            if bulls
            else None
        )

        result.append(
            (
                regime,
                len(sample),
                acc,
                avg_conf,
                avg_distance,
            )
        )

    result.sort(
        key=lambda row: -row[1]
    )

    return result


def confidence_band_stats(rows, horizon):
    bands = [
        (0, 50),
        (50, 60),
        (60, 70),
        (70, 101),
    ]

    output = []

    for low, high in bands:
        selected = [
            row
            for row in rows
            if (
                row["_conf"] is not None
                and low
                <= row["_conf"]
                < high
            )
        ]

        acc, n = directional_accuracy(
            selected,
            horizon,
        )

        output.append(
            (
                f"{low}-{high}",
                n,
                acc,
            )
        )

    return output


def probability_bins(rows, horizon):
    actual_key = f"actual_{horizon}"

    bins = defaultdict(
        lambda: {
            "n": 0,
            "sum_p": 0.0,
            "bulls": 0,
        }
    )

    for row in rows:
        actual = str(
            row.get(actual_key) or ""
        ).strip().upper()

        if actual not in (
            "BULLISH",
            "BEARISH",
        ):
            continue

        p = row["_bull"]

        low = int(p // 10) * 10
        low = min(
            90,
            max(
                0,
                low,
            ),
        )

        key = f"{low}-{low+10}"

        bins[key]["n"] += 1
        bins[key]["sum_p"] += p

        if actual == "BULLISH":
            bins[key]["bulls"] += 1

    result = []

    for low in range(
        0,
        100,
        10,
    ):
        key = f"{low}-{low+10}"

        item = bins.get(key)

        if not item:
            continue

        n = item["n"]

        result.append(
            (
                key,
                n,
                item["sum_p"] / n,
                100.0
                * item["bulls"]
                / n,
            )
        )

    return result


def select_slope(dev):
    scored = []

    for slope in CALIBRATION_SLOPES:
        b4, n4 = brier(
            dev,
            "4h",
            slope,
        )
        b8, n8 = brier(
            dev,
            "8h",
            slope,
        )

        values = [
            score
            for score in (
                b4,
                b8,
            )
            if score is not None
        ]

        avg = (
            sum(values) / len(values)
            if values
            else 999.0
        )

        scored.append(
            (
                avg,
                slope,
                b4,
                b8,
                n4,
                n8,
            )
        )

    scored.sort(
        key=lambda row: row[0]
    )

    return scored


def main():
    rows = load_rows()

    dev = [
        row
        for row in rows
        if row["_ts"] <= DEV_END
    ]

    holdout = [
        row
        for row in rows
        if row["_ts"] > DEV_END
    ]

    print(
        "=== PHASE 22 CALIBRATION + REGIME DIAGNOSTIC ==="
    )
    print(
        "development rows =",
        len(dev),
    )
    print(
        "holdout rows =",
        len(holdout),
    )
    print()

    # --------------------------------
    # Regime analysis
    # --------------------------------
    print(
        "=== REGIME DIAGNOSTIC FULL SAMPLE ==="
    )

    for horizon in (
        "4h",
        "8h",
    ):
        print(horizon.upper())

        for (
            regime,
            n,
            acc,
            avg_conf,
            avg_dist,
        ) in by_regime(
            rows,
            horizon,
        ):
            print(
                regime,
                "| rows =",
                n,
                "| accuracy =",
                (
                    f"{acc:.2f}%"
                    if acc is not None
                    else "NA"
                ),
                "| avg confidence =",
                (
                    f"{avg_conf:.2f}"
                    if avg_conf is not None
                    else "NA"
                ),
                "| avg |prob-50| =",
                (
                    f"{avg_dist:.2f}pp"
                    if avg_dist is not None
                    else "NA"
                ),
            )

    print()
    print(
        "=== CONFIDENCE BAND DIRECTIONAL ACCURACY ==="
    )

    for horizon in (
        "4h",
        "8h",
    ):
        print(horizon.upper())

        for band, n, acc in confidence_band_stats(
            rows,
            horizon,
        ):
            print(
                band,
                "| n =",
                n,
                "| accuracy =",
                (
                    f"{acc:.2f}%"
                    if acc is not None
                    else "NA"
                ),
            )

    # --------------------------------
    # Calibration dev selection
    # --------------------------------
    print()
    print(
        "=== CALIBRATION SLOPE DEVELOPMENT TEST ==="
    )

    scored = select_slope(dev)

    for (
        avg,
        slope,
        b4,
        b8,
        n4,
        n8,
    ) in scored:
        print(
            "slope =",
            slope,
            "| 4H Brier =",
            f"{b4:.4f}",
            f"(n={n4})",
            "| 8H Brier =",
            f"{b8:.4f}",
            f"(n={n8})",
            "| avg =",
            f"{avg:.4f}",
        )

    selected_slope = scored[0][1]

    print()
    print(
        "development selected slope =",
        selected_slope,
    )
    print(
        "original slope = 1.0"
    )

    # --------------------------------
    # Holdout validation
    # --------------------------------
    print()
    print(
        "=== CALIBRATION HOLDOUT VALIDATION ==="
    )

    for slope in sorted(
        {
            1.0,
            selected_slope,
        }
    ):
        b4, n4 = brier(
            holdout,
            "4h",
            slope,
        )
        b8, n8 = brier(
            holdout,
            "8h",
            slope,
        )

        print(
            "slope =",
            slope,
            "| 4H Brier =",
            f"{b4:.4f}",
            f"(n={n4})",
            "| 8H Brier =",
            f"{b8:.4f}",
            f"(n={n8})",
        )

    print()
    print(
        "=== HOLDOUT PROBABILITY BINS ==="
    )

    for horizon in (
        "4h",
        "8h",
    ):
        print(horizon.upper())

        for (
            bucket,
            n,
            avg_p,
            actual_bull,
        ) in probability_bins(
            holdout,
            horizon,
        ):
            print(
                bucket,
                "| n =",
                n,
                "| avg predicted bull =",
                f"{avg_p:.1f}%",
                "| actual bullish =",
                f"{actual_bull:.1f}%",
            )

    # --------------------------------
    # BALANCED-specific diagnostic
    # --------------------------------
    balanced = [
        row
        for row in rows
        if str(
            row.get("regime")
            or ""
        ) == "BALANCED"
    ]

    print()
    print(
        "=== BALANCED REGIME DETAIL ==="
    )
    print(
        "balanced rows =",
        len(balanced),
    )

    for horizon in (
        "4h",
        "8h",
    ):
        acc, n = directional_accuracy(
            balanced,
            horizon,
        )

        print(
            horizon.upper(),
            "| directional accuracy =",
            (
                f"{acc:.2f}%"
                if acc is not None
                else "NA"
            ),
            f"(n={n})",
        )

        for threshold in (
            50,
            55,
            60,
            65,
            70,
        ):
            selected = [
                row
                for row in balanced
                if (
                    row["_conf"] is not None
                    and row["_conf"] >= threshold
                )
            ]

            t_acc, t_n = directional_accuracy(
                selected,
                horizon,
            )

            print(
                f"  >= {threshold}% confidence",
                "| n =",
                t_n,
                "| accuracy =",
                (
                    f"{t_acc:.2f}%"
                    if t_acc is not None
                    else "NA"
                ),
            )

    print()
    print(
        "=== PHASE 22 VERDICT INPUTS ==="
    )
    print(
        "selected_calibration_slope =",
        selected_slope,
    )
    print(
        "Only adopt calibration if holdout Brier improves."
    )
    print(
        "Do not change BALANCED regime logic until its failure mode is isolated."
    )
    print(
        "=== PHASE 22 DIAGNOSTIC COMPLETE ==="
    )


if __name__ == "__main__":
    main()
