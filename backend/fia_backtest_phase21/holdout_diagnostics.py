import csv
import math
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

CSV_PATH = Path(
    "fia_backtest_phase20/results/phase20_full_backtest_1y.csv"
)

DEV_END = datetime(2026, 4, 30, 23, 59, 59, tzinfo=timezone.utc)

NEUTRAL_BANDS = [0.0, 2.5, 5.0, 7.5, 10.0, 12.5]
CONF_THRESHOLDS = [50, 55, 60, 65, 70, 75]


def parse_bool(value):
    if value is None:
        return None

    text = str(value).strip().lower()

    if text in ("true", "1", "yes"):
        return True

    if text in ("false", "0", "no"):
        return False

    return None


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


def load_rows():
    if not CSV_PATH.exists():
        raise FileNotFoundError(
            f"Missing Phase 20 CSV: {CSV_PATH}"
        )

    with CSV_PATH.open(
        newline="",
        encoding="utf-8",
    ) as handle:
        raw = list(csv.DictReader(handle))

    rows = []

    for row in raw:
        ts = parse_ts(row.get("timestamp"))
        bull = parse_float(
            row.get("bullish_probability")
        )
        conf = parse_float(row.get("confidence"))

        if ts is None or bull is None:
            continue

        item = dict(row)
        item["_ts"] = ts
        item["_bull"] = bull
        item["_conf"] = conf
        rows.append(item)

    return rows


def predict_from_band(bullish_probability, band):
    upper = 50.0 + band
    lower = 50.0 - band

    if bullish_probability >= upper:
        return "BULLISH"

    if bullish_probability <= lower:
        return "BEARISH"

    return "NEUTRAL"


def accuracy(rows, horizon, band=None, min_conf=None):
    actual_key = f"actual_{horizon}"

    resolved = []
    correct = 0

    prediction_counts = Counter()

    for row in rows:
        actual = str(row.get(actual_key) or "").strip().upper()

        if actual not in (
            "BULLISH",
            "BEARISH",
            "NEUTRAL",
        ):
            continue

        conf = row["_conf"]

        if min_conf is not None:
            if conf is None or conf < min_conf:
                continue

        if band is None:
            pred = str(
                row.get("predicted") or ""
            ).strip().upper()
        else:
            pred = predict_from_band(
                row["_bull"],
                band,
            )

        if pred not in (
            "BULLISH",
            "BEARISH",
            "NEUTRAL",
        ):
            continue

        resolved.append(row)
        prediction_counts[pred] += 1

        if pred == actual:
            correct += 1

    n = len(resolved)

    return {
        "n": n,
        "correct": correct,
        "accuracy": (
            100.0 * correct / n
            if n
            else None
        ),
        "predictions": dict(
            prediction_counts
        ),
    }


def directional_only(rows, horizon, band):
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

        pred = predict_from_band(
            row["_bull"],
            band,
        )

        if pred == "NEUTRAL":
            continue

        n += 1

        if pred == actual:
            correct += 1

    return (
        100.0 * correct / n
        if n
        else None,
        n,
    )


def neutral_precision(rows, horizon, band):
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

        pred = predict_from_band(
            row["_bull"],
            band,
        )

        if pred != "NEUTRAL":
            continue

        n += 1

        if actual == "NEUTRAL":
            correct += 1

    return (
        100.0 * correct / n
        if n
        else None,
        n,
    )


def combined_score(rows, band):
    a4 = accuracy(
        rows,
        "4h",
        band=band,
    )
    a8 = accuracy(
        rows,
        "8h",
        band=band,
    )

    values = [
        value
        for value in (
            a4["accuracy"],
            a8["accuracy"],
        )
        if value is not None
    ]

    return (
        sum(values) / len(values)
        if values
        else -1.0
    )


def brier(rows, horizon):
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

        p = row["_bull"] / 100.0
        y = 1.0 if actual == "BULLISH" else 0.0

        values.append(
            (p - y) ** 2
        )

    if not values:
        return None, 0

    return sum(values) / len(values), len(values)


def calibration_bins(rows, horizon):
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
            max(low, 0),
            90,
        )
        high = low + 10

        key = f"{low}-{high}"

        bins[key]["n"] += 1
        bins[key]["sum_p"] += p

        if actual == "BULLISH":
            bins[key]["bulls"] += 1

    ordered = []

    for low in range(0, 100, 10):
        key = f"{low}-{low+10}"
        item = bins.get(key)

        if not item or not item["n"]:
            continue

        ordered.append(
            (
                key,
                item["n"],
                item["sum_p"]
                / item["n"],
                100.0
                * item["bulls"]
                / item["n"],
            )
        )

    return ordered


def regime_table(rows, horizon):
    stats = defaultdict(
        lambda: [0, 0]
    )

    for row in rows:
        actual = str(
            row.get(f"actual_{horizon}")
            or ""
        ).strip().upper()

        pred = str(
            row.get("predicted")
            or ""
        ).strip().upper()

        regime = str(
            row.get("regime")
            or "UNKNOWN"
        )

        if actual not in (
            "BULLISH",
            "BEARISH",
            "NEUTRAL",
        ):
            continue

        if pred not in (
            "BULLISH",
            "BEARISH",
            "NEUTRAL",
        ):
            continue

        stats[regime][0] += 1

        if pred == actual:
            stats[regime][1] += 1

    result = []

    for regime, (n, correct) in stats.items():
        result.append(
            (
                regime,
                n,
                100.0 * correct / n,
            )
        )

    result.sort(
        key=lambda x: (-x[1], x[0])
    )

    return result


def confidence_table(rows, horizon):
    output = []

    total_resolved = accuracy(
        rows,
        horizon,
    )["n"]

    for threshold in CONF_THRESHOLDS:
        result = accuracy(
            rows,
            horizon,
            min_conf=threshold,
        )

        coverage = (
            100.0
            * result["n"]
            / total_resolved
            if total_resolved
            else 0.0
        )

        output.append(
            (
                threshold,
                result["n"],
                result["accuracy"],
                coverage,
            )
        )

    return output


def print_period_header(name, rows):
    if not rows:
        print(name, "| rows = 0")
        return

    print(
        name,
        "| rows =",
        len(rows),
        "|",
        rows[0]["_ts"].date(),
        "->",
        rows[-1]["_ts"].date(),
    )


def main():
    rows = load_rows()

    rows.sort(
        key=lambda row: row["_ts"]
    )

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
        "=== PHASE 21 HOLDOUT DIAGNOSTICS ==="
    )
    print_period_header(
        "DEVELOPMENT",
        dev,
    )
    print_period_header(
        "HOLDOUT",
        holdout,
    )
    print()

    print(
        "=== ORIGINAL MODEL ==="
    )

    for label, sample in (
        ("DEV", dev),
        ("HOLDOUT", holdout),
        ("FULL", rows),
    ):
        a4 = accuracy(
            sample,
            "4h",
        )
        a8 = accuracy(
            sample,
            "8h",
        )

        print(
            label,
            "| 4H =",
            (
                f"{a4['accuracy']:.2f}%"
                if a4["accuracy"]
                is not None
                else "NA"
            ),
            f"(n={a4['n']})",
            "| 8H =",
            (
                f"{a8['accuracy']:.2f}%"
                if a8["accuracy"]
                is not None
                else "NA"
            ),
            f"(n={a8['n']})",
        )

    print()
    print(
        "=== NEUTRAL BAND DEVELOPMENT TEST ==="
    )

    development_scores = []

    for band in NEUTRAL_BANDS:
        a4 = accuracy(
            dev,
            "4h",
            band=band,
        )
        a8 = accuracy(
            dev,
            "8h",
            band=band,
        )
        d4, d4n = directional_only(
            dev,
            "4h",
            band,
        )
        n4, n4n = neutral_precision(
            dev,
            "4h",
            band,
        )

        score = combined_score(
            dev,
            band,
        )

        development_scores.append(
            (score, band)
        )

        print(
            f"band = +/-{band:.1f}pp",
            "| 4H =",
            f"{a4['accuracy']:.2f}%",
            f"(N={a4['n']})",
            "| 8H =",
            f"{a8['accuracy']:.2f}%",
            f"(N={a8['n']})",
            "| directional 4H =",
            (
                f"{d4:.2f}%"
                if d4 is not None
                else "NA"
            ),
            f"(n={d4n})",
            "| neutral 4H precision =",
            (
                f"{n4:.2f}%"
                if n4 is not None
                else "NA"
            ),
            f"(n={n4n})",
        )

    development_scores.sort(
        reverse=True
    )

    candidate_band = (
        development_scores[0][1]
    )

    print()
    print(
        "development selected band =",
        f"+/-{candidate_band:.1f}pp",
    )
    print(
        "original band = +/-5.0pp"
    )

    print()
    print(
        "=== NEUTRAL BAND HOLDOUT VALIDATION ==="
    )

    for band in sorted(
        {
            5.0,
            candidate_band,
            0.0,
        }
    ):
        a4 = accuracy(
            holdout,
            "4h",
            band=band,
        )
        a8 = accuracy(
            holdout,
            "8h",
            band=band,
        )
        d4, d4n = directional_only(
            holdout,
            "4h",
            band,
        )
        d8, d8n = directional_only(
            holdout,
            "8h",
            band,
        )
        n4, n4n = neutral_precision(
            holdout,
            "4h",
            band,
        )
        n8, n8n = neutral_precision(
            holdout,
            "8h",
            band,
        )

        print(
            f"band = +/-{band:.1f}pp",
            "| 4H =",
            f"{a4['accuracy']:.2f}%",
            f"(n={a4['n']})",
            "| 8H =",
            f"{a8['accuracy']:.2f}%",
            f"(n={a8['n']})",
            "| directional 4H =",
            (
                f"{d4:.2f}%"
                if d4 is not None
                else "NA"
            ),
            f"(n={d4n})",
            "| directional 8H =",
            (
                f"{d8:.2f}%"
                if d8 is not None
                else "NA"
            ),
            f"(n={d8n})",
            "| neutral precision 4H =",
            (
                f"{n4:.2f}%"
                if n4 is not None
                else "NA"
            ),
            f"(n={n4n})",
            "| neutral precision 8H =",
            (
                f"{n8:.2f}%"
                if n8 is not None
                else "NA"
            ),
            f"(n={n8n})",
        )

    print()
    print(
        "=== CONFIDENCE HOLDOUT PERFORMANCE ==="
    )

    for horizon in (
        "4h",
        "8h",
    ):
        print(horizon.upper())

        for threshold, n, acc, coverage in confidence_table(
            holdout,
            horizon,
        ):
            print(
                f">={threshold}% confidence",
                "| n =",
                n,
                "| accuracy =",
                (
                    f"{acc:.2f}%"
                    if acc is not None
                    else "NA"
                ),
                "| resolved coverage =",
                f"{coverage:.2f}%",
            )

    print()
    print(
        "=== REGIME HOLDOUT PERFORMANCE ==="
    )

    for horizon in (
        "4h",
        "8h",
    ):
        print(horizon.upper())

        for regime, n, acc in regime_table(
            holdout,
            horizon,
        ):
            print(
                regime,
                "| n =",
                n,
                "| accuracy =",
                f"{acc:.2f}%",
            )

    print()
    print(
        "=== PROBABILITY CALIBRATION HOLDOUT ==="
    )

    for horizon in (
        "4h",
        "8h",
    ):
        score, n = brier(
            holdout,
            horizon,
        )

        print(
            horizon.upper(),
            "| Brier =",
            (
                f"{score:.4f}"
                if score is not None
                else "NA"
            ),
            "| n =",
            n,
            "| 0.5-probability baseline = 0.2500",
        )

        for (
            bucket,
            count,
            avg_pred,
            actual_bull,
        ) in calibration_bins(
            holdout,
            horizon,
        ):
            print(
                " ",
                bucket,
                "| n =",
                count,
                "| avg predicted bull =",
                f"{avg_pred:.1f}%",
                "| actual bullish =",
                f"{actual_bull:.1f}%",
            )

    print()
    print(
        "=== PHASE 21 DIAGNOSTIC VERDICT INPUTS ==="
    )
    print(
        "candidate_neutral_band_pp =",
        candidate_band,
    )
    print(
        "Do NOT change production settings solely from development performance."
    )
    print(
        "Only adopt a neutral-band or confidence rule if holdout also improves materially."
    )
    print(
        "=== PHASE 21 HOLDOUT DIAGNOSTICS COMPLETE ==="
    )


if __name__ == "__main__":
    main()
