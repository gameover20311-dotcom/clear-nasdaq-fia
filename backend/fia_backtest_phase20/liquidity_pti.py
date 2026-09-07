import json
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path

import pandas as pd

CACHE_PATH = Path(
    "fia_backtest_phase20/data/nq_5m_multicontract_20250901_20260831.json"
)

CONTRACT_ORDER = {
    "NQU5": 1,
    "NQZ5": 2,
    "NQH6": 3,
    "NQM6": 4,
    "NQU6": 5,
}


def parse_ts(value):
    if isinstance(value, datetime):
        dt = value
    else:
        dt = datetime.fromisoformat(
            str(value).replace("Z", "+00:00")
        )

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)

    return dt.astimezone(timezone.utc)


@lru_cache(maxsize=1)
def load_contract_frames():
    if not CACHE_PATH.exists():
        raise FileNotFoundError(
            f"Missing NQ 5m cache: {CACHE_PATH}"
        )

    payload = json.loads(
        CACHE_PATH.read_text(encoding="utf-8")
    )

    by_contract = defaultdict(list)

    for row in payload.get("bars") or []:
        contract = str(row.get("contract") or "")
        ts = parse_ts(row.get("timestamp"))

        if not contract or ts is None:
            continue

        by_contract[contract].append(
            {
                "timestamp": ts,
                "Open": row.get("open"),
                "High": row.get("high"),
                "Low": row.get("low"),
                "Close": row.get("close"),
                "Volume": row.get("volume"),
            }
        )

    frames = {}

    for contract, rows in by_contract.items():
        df = pd.DataFrame(rows)

        if df.empty:
            continue

        df = df.set_index("timestamp").sort_index()

        for column in (
            "Open",
            "High",
            "Low",
            "Close",
            "Volume",
        ):
            df[column] = pd.to_numeric(
                df[column],
                errors="coerce",
            )

        frames[contract] = df

    return frames


def completed_asof(df, target):
    if df is None or df.empty:
        return df

    target = parse_ts(target)

    # 5m bars are stamped by bar start. At target 17:00,
    # the 16:55 bar is the latest fully known bar.
    cutoff = target - timedelta(minutes=5)

    return df[df.index <= cutoff]


def select_dominant_contract(
    target,
    volume_lookback_hours=24,
):
    """Choose the dominant NQ contract using only past volume.

    No post-target volume is used. During rollover overlaps,
    each contract is scored on the same trailing 24-hour window.
    """
    target = parse_ts(target)
    frames = load_contract_frames()

    cutoff = target - timedelta(minutes=5)
    lookback = cutoff - timedelta(
        hours=volume_lookback_hours
    )

    candidates = []

    for contract, df in frames.items():
        recent = df[
            (df.index >= lookback)
            & (df.index <= cutoff)
        ]

        if recent.empty:
            continue

        closes = recent["Close"].dropna()
        if closes.empty:
            continue

        volume = pd.to_numeric(
            recent["Volume"],
            errors="coerce",
        ).fillna(0.0)

        volume_sum = float(
            volume.clip(lower=0).sum()
        )

        completed_bars = int(
            recent["Close"].notna().sum()
        )

        last_bar = recent.index[-1]

        # Require enough recent evidence to avoid selecting a
        # contract with only a few stale bars.
        if completed_bars < 12:
            continue

        candidates.append(
            {
                "contract": contract,
                "volume_24h": volume_sum,
                "bars_24h": completed_bars,
                "last_bar": last_bar,
                "contract_order": CONTRACT_ORDER.get(
                    contract,
                    0,
                ),
            }
        )

    if not candidates:
        return None, []

    # Primary rule: highest volume known as-of target.
    # Tie-break: fresher bar, then later quarterly contract.
    candidates.sort(
        key=lambda row: (
            row["volume_24h"],
            row["last_bar"],
            row["contract_order"],
        ),
        reverse=True,
    )

    return candidates[0], candidates


def liquidity_asof_cached(target, hub):
    """Phase 20 point-in-time NQ 5m liquidity.

    1. Pick dominant quarterly NQ contract from trailing 24h
       volume available at the forecast timestamp.
    2. Use only fully completed 5-minute bars from that SAME
       contract.
    3. Apply the same session sweep/reclaim logic used in
       Phase 19/live FIA.
    """
    target = parse_ts(target)

    selected, candidates = select_dominant_contract(
        target
    )

    if selected is None:
        return {
            "nq_liquidity_evidence": "missing",
            "liquidity_signal": None,
            "liquidity_resolution": "missing",
            "liquidity_contract": None,
        }

    contract = selected["contract"]
    frames = load_contract_frames()
    df = completed_asof(
        frames.get(contract),
        target,
    )

    if df is None or df.empty:
        return {
            "nq_liquidity_evidence": "missing",
            "liquidity_signal": None,
            "liquidity_resolution": "missing",
            "liquidity_contract": contract,
        }

    now = target.astimezone(timezone.utc)
    levels = {}

    for back in range(8):
        day = now.date() - timedelta(
            days=back
        )

        for session in (
            "ASIA",
            "LONDON",
            "NEW_YORK",
        ):
            start, end = (
                hub.session_window_for_date(
                    session,
                    day,
                )
            )

            if start is None or end is None:
                continue

            rows = df[
                (df.index >= start)
                & (df.index < end)
            ]

            if rows.empty:
                continue

            high_key = (
                session.lower()
                + "_high"
            )
            low_key = (
                session.lower()
                + "_low"
            )

            if high_key not in levels:
                levels[high_key] = float(
                    rows["High"].max()
                )

            if low_key not in levels:
                levels[low_key] = float(
                    rows["Low"].min()
                )

        required = {
            "asia_high",
            "asia_low",
            "london_high",
            "london_low",
            "new_york_high",
            "new_york_low",
        }

        if required.issubset(levels):
            break

    closes = df["Close"].dropna()

    if closes.empty:
        return {
            "nq_liquidity_evidence": "missing",
            "liquidity_signal": None,
            "liquidity_resolution": "missing",
            "liquidity_contract": contract,
        }

    price = float(closes.iloc[-1])
    recent = df.tail(12)

    result = {
        "nq_liquidity_evidence": "available",
        "liquidity_resolution": "5m_massive_futures",
        "liquidity_contract": contract,
        "liquidity_contract_volume_24h": round(
            selected["volume_24h"],
            2,
        ),
        "liquidity_contract_candidates": [
            {
                "contract": row["contract"],
                "volume_24h": round(
                    row["volume_24h"],
                    2,
                ),
                "bars_24h": row[
                    "bars_24h"
                ],
            }
            for row in candidates
        ],
        "nq_price": price,
        **levels,
    }

    targets = []

    for name, level in levels.items():
        distance = float(level) - price
        distance_abs = abs(distance)

        result[
            f"{name}_distance"
        ] = distance

        result[
            f"{name}_distance_abs"
        ] = distance_abs

        targets.append(
            {
                "level": name,
                "price": float(level),
                "distance": distance,
                "distance_abs": distance_abs,
            }
        )

    targets.sort(
        key=lambda row: row[
            "distance_abs"
        ]
    )

    result["nearest_liquidity"] = (
        targets[0]["level"]
        if targets
        else None
    )

    result[
        "nearest_liquidity_distance"
    ] = (
        targets[0]["distance"]
        if targets
        else None
    )

    bull = False
    bear = False

    for session in (
        "asia",
        "london",
        "new_york",
    ):
        high = levels.get(
            f"{session}_high"
        )
        low = levels.get(
            f"{session}_low"
        )

        if high is None or low is None:
            continue

        swept_high = bool(
            (recent["High"] > high).any()
        )
        swept_low = bool(
            (recent["Low"] < low).any()
        )

        reclaimed_high = (
            swept_high
            and price < high
        )
        reclaimed_low = (
            swept_low
            and price > low
        )

        result[
            f"{session}_high_sweep"
        ] = swept_high
        result[
            f"{session}_low_sweep"
        ] = swept_low
        result[
            f"{session}_high_reclaim"
        ] = reclaimed_high
        result[
            f"{session}_low_reclaim"
        ] = reclaimed_low

        bear = bear or reclaimed_high
        bull = bull or reclaimed_low

    if bull and not bear:
        direction = "BULLISH"
        signal = 1.0
        conflict = "LOW"

    elif bear and not bull:
        direction = "BEARISH"
        signal = -1.0
        conflict = "LOW"

    elif bull and bear:
        direction = "NEUTRAL"
        signal = 0.0
        conflict = "HIGH"

    else:
        direction = "NEUTRAL"
        signal = 0.0
        conflict = "NONE"

    result.update(
        liquidity_direction=direction,
        liquidity_signal=signal,
        liquidity_conflict=conflict,
    )

    ranked = []

    for item in targets:
        ranked.append(
            {
                "level": item["level"],
                "price": item["price"],
                "direction": (
                    "UP"
                    if item[
                        "level"
                    ].endswith("_high")
                    else "DOWN"
                ),
                "distance": item[
                    "distance"
                ],
                "rank_score": round(
                    1.0
                    / (
                        1.0
                        + item[
                            "distance_abs"
                        ]
                    ),
                    6,
                ),
            }
        )

    result[
        "liquidity_targets"
    ] = ranked[:6]

    positive_volumes = [
        float(value)
        for value in recent[
            "Volume"
        ].dropna()
        if float(value) > 0
    ]

    if positive_volumes:
        average = (
            sum(positive_volumes)
            / len(positive_volumes)
        )

        current_volume = float(
            recent[
                "Volume"
            ].iloc[-1]
        )

        result[
            "nq_relative_volume"
        ] = (
            current_volume
            / average
            if average
            else None
        )

    else:
        result[
            "nq_relative_volume"
        ] = None

    return result
