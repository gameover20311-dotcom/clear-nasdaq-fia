from __future__ import annotations
import hashlib
import json
import math
from datetime import datetime, timezone
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _reject_nonfinite(obj: Any) -> None:
    if isinstance(obj, float) and not math.isfinite(obj):
        raise ValueError("non-finite float forbidden")
    if isinstance(obj, dict):
        for k, v in obj.items():
            _reject_nonfinite(k)
            _reject_nonfinite(v)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            _reject_nonfinite(v)


def canonical_json(obj: Any) -> str:
    _reject_nonfinite(obj)
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def sha256_obj(obj: Any) -> str:
    return hashlib.sha256(canonical_json(obj).encode("utf-8")).hexdigest()


def clamp(v: float, lo: float, hi: float) -> float:
    x=float(v)
    if not math.isfinite(x):
        raise ValueError("non-finite numeric")
    return max(lo, min(hi, x))
