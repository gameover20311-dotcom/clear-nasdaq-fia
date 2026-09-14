"""Strict real-schema contract for SIMONS SHADOW LAB V2 hybrid.

This module adapts the strongest anti-leakage idea from the independent Cloud
build to the *actual* CLEAR NASDAQ Shadow-Lab row shape used by this repository.
It intentionally does not require synthetic/proposed fields such as neutral
probabilities. Prediction-time code receives a guarded mapping where any attempt
to read resolution/outcome data raises immediately, including via ``.get()``.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Dict, Iterator


class LeakageError(RuntimeError):
    pass


_FORBIDDEN_ROOT = {"outcomes", "resolution", "resolutions", "future", "future_price"}
_FORBIDDEN_TOKENS = ("outcome_", "resolved_", "resolution_", "future_")
_ALLOWED_ROOT = {
    "forecast_id", "lock_event_hash", "locked_at_utc", "checkpoint_date",
    "entry", "campaign", "eligibility", "base", "evidence",
}


def _forbidden_key(key: str) -> bool:
    k = str(key or "").strip().lower()
    return k in _FORBIDDEN_ROOT or any(k.startswith(token) for token in _FORBIDDEN_TOKENS)


class GuardedMapping(Mapping):
    """Read-only recursive mapping that refuses future/resolution fields."""

    __slots__ = ("_data", "_path")

    def __init__(self, data: Mapping[str, Any], path: str = "row") -> None:
        self._data = data
        self._path = path

    def __getitem__(self, key: str) -> Any:
        if _forbidden_key(key):
            raise LeakageError(f"post-outcome field blocked at {self._path}.{key}")
        value = self._data.get(key)
        if isinstance(value, Mapping):
            return GuardedMapping(value, f"{self._path}.{key}")
        if isinstance(value, list):
            return tuple(_guard_value(v, f"{self._path}.{key}[]") for v in value)
        return value

    def get(self, key: str, default: Any = None) -> Any:
        value = self[key]  # .get() deliberately does not soften the barrier
        return default if value is None else value

    def __iter__(self) -> Iterator[str]:
        return (k for k in self._data.keys() if not _forbidden_key(str(k)))

    def __len__(self) -> int:
        return sum(1 for k in self._data.keys() if not _forbidden_key(str(k)))


def _guard_value(value: Any, path: str) -> Any:
    if isinstance(value, Mapping):
        return GuardedMapping(value, path)
    if isinstance(value, list):
        return tuple(_guard_value(v, path + "[]") for v in value)
    return value


class LockTimeRowView(GuardedMapping):
    """Guard the actual Shadow-Lab row contract.

    Unknown root fields fail closed. Nested BASE_FIA fields remain open because
    production evidence evolves, but all resolution-like names are blocked
    recursively.
    """

    def __getitem__(self, key: str) -> Any:
        if key not in _ALLOWED_ROOT and key not in self._data:
            raise LeakageError(f"unknown root field blocked: {key}")
        if key not in _ALLOWED_ROOT:
            raise LeakageError(f"field outside lock-time contract blocked: {key}")
        return super().__getitem__(key)


def validate_horizon_distribution(base: Mapping[str, Any], hours: int, tolerance: float = 0.75) -> Dict[str, Any]:
    """Validate the *real* two-way published horizon distribution.

    CLEAR NASDAQ currently stores bullish/bearish probabilities for 4H and 8H.
    We therefore validate exactly those fields rather than importing the Cloud
    fixture's proposed neutral-probability schema.
    """
    if hours not in (4, 8):
        raise ValueError("hours must be 4 or 8")
    h = base.get(f"h{hours}") or {}
    bull = h.get("bullish_probability")
    bear = h.get("bearish_probability")
    if bull is None or bear is None:
        return {"ok": False, "reason": "missing_distribution", "hours": hours}
    try:
        bull_f, bear_f = float(bull), float(bear)
    except (TypeError, ValueError):
        return {"ok": False, "reason": "non_numeric_distribution", "hours": hours}
    if not (0.0 <= bull_f <= 100.0 and 0.0 <= bear_f <= 100.0):
        return {"ok": False, "reason": "probability_out_of_range", "hours": hours}
    total = bull_f + bear_f
    if abs(total - 100.0) > float(tolerance):
        return {"ok": False, "reason": "distribution_not_normalized", "hours": hours, "sum": total}
    return {"ok": True, "hours": hours, "bullish_probability": bull_f, "bearish_probability": bear_f, "sum": total}


def audit_lock_time_row(row: Mapping[str, Any]) -> Dict[str, Any]:
    view = LockTimeRowView(row)
    base = view.get("base") or {}
    required = {
        "forecast_id": view.get("forecast_id"),
        "locked_at_utc": view.get("locked_at_utc"),
        "base": base,
    }
    missing = [k for k, v in required.items() if v in (None, "", {})]
    d4 = validate_horizon_distribution(base, 4) if base else {"ok": False, "reason": "missing_base", "hours": 4}
    d8 = validate_horizon_distribution(base, 8) if base else {"ok": False, "reason": "missing_base", "hours": 8}
    return {
        "ok": not missing and d4.get("ok") and d8.get("ok"),
        "missing_required": missing,
        "h4": d4,
        "h8": d8,
        "outcome_access_forbidden": True,
        "schema": "CLEAR_NASDAQ_ACTUAL_SHADOW_ROW_V2",
    }
