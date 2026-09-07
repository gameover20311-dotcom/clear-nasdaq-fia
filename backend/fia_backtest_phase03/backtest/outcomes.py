"""Phase 03 — Future Outcome Engine.

Joins timestamped FIA predictions to later OHLC candles and calculates
forward returns, direction, MFE and MAE without using future data in the
prediction itself.
"""
from __future__ import annotations

import csv
import json
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence
from uuid import uuid5, NAMESPACE_URL

from .replay import parse_timestamp
from .schemas import OutcomeRecord, PredictionRecord


HORIZON_HOURS = {"1h": 1, "4h": 4, "8h": 8}


def _float(value: Any) -> Optional[float]:
    try:
        return None if value is None or value == "" else float(value)
    except (TypeError, ValueError):
        return None


def load_candles(path: str | Path) -> List[Dict[str, Any]]:
    """Load timestamped OHLC candles from JSONL/CSV.

    Accepted names are timestamp/time/datetime and open/high/low/close.
    """
    path = Path(path)
    if path.suffix.lower() == ".jsonl":
        rows = []
        with path.open("r", encoding="utf-8") as fh:
            for line in fh:
                if line.strip():
                    rows.append(json.loads(line))
    elif path.suffix.lower() == ".csv":
        with path.open("r", encoding="utf-8", newline="") as fh:
            rows = list(csv.DictReader(fh))
    else:
        raise ValueError("Candles must be .jsonl or .csv")

    out = []
    for row in rows:
        ts = row.get("timestamp", row.get("time", row.get("datetime")))
        if ts is None:
            continue
        high = _float(row.get("high"))
        low = _float(row.get("low"))
        close = _float(row.get("close"))
        if high is None or low is None or close is None:
            continue
        out.append({
            "timestamp": parse_timestamp(ts),
            "open": _float(row.get("open")),
            "high": high,
            "low": low,
            "close": close,
        })
    return sorted(out, key=lambda x: x["timestamp"])


def prediction_id(prediction: PredictionRecord) -> str:
    """Stable ID so rerunning a backtest does not create arbitrary IDs."""
    raw = f"{prediction.run_id}|{prediction.timestamp}|{prediction.price}"
    return uuid5(NAMESPACE_URL, raw).hex


class FutureOutcomeEngine:
    """Calculate forward outcomes from already-available historical candles."""

    def __init__(self, candles: Sequence[Dict[str, Any]]):
        self.candles = sorted(candles, key=lambda x: parse_timestamp(x["timestamp"]))
        self._times = [parse_timestamp(c["timestamp"]) for c in self.candles]

    def _window(self, start: datetime, end: datetime) -> List[Dict[str, Any]]:
        return [c for c, ts in zip(self.candles, self._times) if start <= ts <= end]

    def outcome(self, prediction: PredictionRecord, horizon: str) -> OutcomeRecord:
        if horizon not in HORIZON_HOURS:
            raise ValueError(f"Unsupported horizon: {horizon}")
        start = parse_timestamp(prediction.timestamp)
        target = start + timedelta(hours=HORIZON_HOURS[horizon])
        entry = _float(prediction.price)
        if entry is None or entry <= 0:
            return OutcomeRecord(prediction_id=prediction_id(prediction), timestamp=prediction.timestamp,
                                 horizon=horizon, entry_price=entry, future_price=None,
                                 return_pct=None, direction=None)

        # First candle at/after the exact target is used for the target close.
        future = next((c for c, ts in zip(self.candles, self._times) if ts >= target), None)
        if future is None:
            return OutcomeRecord(prediction_id=prediction_id(prediction), timestamp=prediction.timestamp,
                                 horizon=horizon, entry_price=entry, future_price=None,
                                 return_pct=None, direction=None)

        future_price = _float(future.get("close"))
        if future_price is None:
            return OutcomeRecord(prediction_id=prediction_id(prediction), timestamp=prediction.timestamp,
                                 horizon=horizon, entry_price=entry, future_price=None,
                                 return_pct=None, direction=None)

        ret = (future_price / entry - 1.0) * 100.0
        direction = "bullish" if ret > 0 else "bearish" if ret < 0 else "flat"
        window = self._window(start, future["timestamp"])
        highs = [c["high"] for c in window if c.get("high") is not None]
        lows = [c["low"] for c in window if c.get("low") is not None]
        mfe = ((max(highs) / entry) - 1.0) * 100.0 if highs else None
        mae = ((min(lows) / entry) - 1.0) * 100.0 if lows else None

        return OutcomeRecord(prediction_id=prediction_id(prediction), timestamp=prediction.timestamp,
                             horizon=horizon, entry_price=entry, future_price=future_price,
                             return_pct=ret, direction=direction, mfe_pct=mfe, mae_pct=mae)

    def run(self, predictions: Iterable[PredictionRecord], horizons: Sequence[str] = ("4h", "8h")) -> List[OutcomeRecord]:
        results = []
        for pred in predictions:
            for horizon in horizons:
                results.append(self.outcome(pred, horizon))
        return results
