from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timezone
from typing import Any, Iterable, Optional


def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, float(value)))


def clamp_signal(value: float) -> float:
    return clamp(float(value), -1.0, 1.0)


def as_float(value: Any, default: Optional[float] = None) -> Optional[float]:
    try:
        if value is None or value == "":
            return default
        out = float(value)
        if math.isfinite(out):
            return out
    except Exception:
        pass
    return default


def truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "y", "on"}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_dt(value: Any) -> Optional[datetime]:
    if isinstance(value, datetime):
        dt = value
    else:
        text = str(value or "").strip()
        if not text:
            return None
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            dt = datetime.fromisoformat(text)
        except Exception:
            try:
                dt = datetime.fromtimestamp(float(text), tz=timezone.utc)
            except Exception:
                return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def stable_hash(payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def sigmoid(x: float) -> float:
    x = max(-35.0, min(35.0, float(x)))
    return 1.0 / (1.0 + math.exp(-x))


def logit(p: float) -> float:
    p = clamp(p, 1e-6, 1.0 - 1e-6)
    return math.log(p / (1.0 - p))


def score_to_probability(score: float, slope: float = 2.35) -> float:
    return 100.0 * sigmoid(slope * clamp_signal(score))


def direction_from_probability(probability: float) -> str:
    return "BULLISH" if float(probability) >= 50.0 else "BEARISH"


def mean(values: Iterable[float], default: float = 0.0) -> float:
    vals = [float(v) for v in values]
    return sum(vals) / len(vals) if vals else default
