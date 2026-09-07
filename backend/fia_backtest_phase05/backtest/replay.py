"""Phase 2 — historical FIA replay.

This module deliberately does not fetch current provider data. It replays
historical, timestamped FIA input snapshots through the SAME forecast engine
used by the live application. This prevents a fake backtest where today's
data is substituted for historical data.
"""
from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional
from uuid import uuid4

from .quality import data_quality_score, provider_quality
from .schemas import PredictionRecord


def parse_timestamp(value: Any) -> datetime:
    if isinstance(value, datetime):
        dt = value
    else:
        text = str(value).strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def load_snapshots(path: str | Path) -> Iterable[Dict[str, Any]]:
    """Load historical snapshot records from JSONL or CSV."""
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix == ".jsonl":
        with path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    yield json.loads(line)
        return
    if suffix == ".csv":
        with path.open("r", encoding="utf-8", newline="") as fh:
            yield from csv.DictReader(fh)
        return
    raise ValueError("Historical snapshots must be .jsonl or .csv")


class HistoricalReplay:
    """Replay historical FIA snapshots without changing forecast logic."""

    def __init__(self, forecast_fn: Callable[[Dict[str, Any]], Dict[str, Any]]):
        if not callable(forecast_fn):
            raise TypeError("forecast_fn must be callable")
        self.forecast_fn = forecast_fn
        self.ready = True

    def _validate_observation(self, record: Dict[str, Any], asof: datetime) -> None:
        ts = record.get("timestamp")
        if ts is None:
            raise ValueError("Historical snapshot is missing timestamp")
        observed_at = parse_timestamp(ts)
        if observed_at > asof:
            raise ValueError("Look-ahead detected: snapshot timestamp is after as-of time")

        # Optional provenance guard. If a record carries a list of source
        # timestamps, none may be newer than the prediction timestamp.
        source_times = record.get("source_timestamps") or []
        for source_ts in source_times:
            if parse_timestamp(source_ts) > asof:
                raise ValueError("Look-ahead detected in source_timestamps")

    def replay_records(
        self,
        records: Iterable[Dict[str, Any]],
        run_id: str,
        instrument: str = "QQQ",
    ) -> List[PredictionRecord]:
        predictions: List[PredictionRecord] = []
        ordered = sorted(records, key=lambda r: parse_timestamp(r["timestamp"]))

        for record in ordered:
            asof = parse_timestamp(record["timestamp"])
            self._validate_observation(record, asof)

            # Accept either a raw FIA data dict or a {"data": {...}} envelope.
            data = record.get("data", record)
            forecast = self.forecast_fn(data)

            components = {
                key: data.get(key)
                for key in (
                    "nq_structure",
                    "liquidity_evidence_available",
                    "mega_cap",
                    "semis",
                    "breadth",
                    "macro",
                    "news",
                    "earnings",
                )
                if key in data
            }

            prediction = PredictionRecord(
                run_id=run_id,
                timestamp=asof.isoformat(),
                price=_safe_float(data.get("price")),
                bullish_probability=_extract_probability(forecast, "bullish"),
                bearish_probability=_extract_probability(forecast, "bearish"),
                fia_score=_extract_number(forecast, ("fia_score", "score")),
                components=components,
                regime=data.get("regime"),
                data_quality_score=data_quality_score(data),
                provider_status=provider_quality(data),
            )
            predictions.append(prediction)

        return predictions

    def replay_file(
        self,
        path: str | Path,
        run_id: Optional[str] = None,
        instrument: str = "QQQ",
    ) -> List[PredictionRecord]:
        run_id = run_id or f"replay_{uuid4().hex[:12]}"
        return self.replay_records(load_snapshots(path), run_id, instrument)


def _safe_float(value: Any) -> Optional[float]:
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None


def _extract_number(payload: Dict[str, Any], keys: tuple[str, ...]) -> Optional[float]:
    for key in keys:
        if key in payload:
            return _safe_float(payload[key])
    return None


def _extract_probability(payload: Dict[str, Any], side: str) -> Optional[float]:
    candidates = (
        f"{side}_probability",
        f"{side}_prob",
        side,
    )
    return _extract_number(payload, candidates)
