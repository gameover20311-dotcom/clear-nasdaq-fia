# PHASE26_LEARNING_VALIDATION_V1
from __future__ import annotations

import asyncio
import csv
import inspect
import json
import math
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

DEFAULT_FORWARD_PATH = (
    Path(__file__).resolve().parents[1]
    / "fia_forward_learning"
    / "data"
    / "phase26_forward_records.csv"
)

FORWARD_FIELDS = [
    "prediction_id",
    "timestamp",
    "symbol",
    "direction",
    "bullish_probability",
    "bearish_probability",
    "confidence",
    "regime",
    "data_coverage",
    "intelligence_coverage",
    "phase24_grade",
    "phase24_eligible",
    "entry_nq",
    "aligned_signals",
    "opposed_signals",
    "missing_signals",
    "signal_combo",
    "phase25_grade",
    "phase25_eligible",
    "confluence_score",
    "confluence_alignment",
    "confluence_completeness",
    "confluence_features",
    "alert_level",
    "target_4h",
    "target_8h",
    "nq_4h",
    "nq_8h",
    "actual_4h",
    "actual_8h",
    "correct_4h",
    "correct_8h",
    "resolved_4h_at",
    "resolved_8h_at",
]


def _get(obj: Any, key: str, default=None):
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _as_float(value: Any, default: Optional[float] = None) -> Optional[float]:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except Exception:
        return default


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "y", "on"}


def _parse_dt(value: Any) -> datetime:
    if isinstance(value, datetime):
        dt = value
    else:
        text = str(value or "").strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


def _bucket_time(dt: datetime) -> datetime:
    minutes = max(15, int(os.getenv("PHASE26_RECORD_INTERVAL_MINUTES", "60") or "60"))
    dt = dt.astimezone(timezone.utc).replace(second=0, microsecond=0)
    total = dt.hour * 60 + dt.minute
    bucket = (total // minutes) * minutes
    hour = bucket // 60
    minute = bucket % 60
    day_start = dt.replace(hour=0, minute=0)
    return day_start + timedelta(hours=hour, minutes=minute)


def _prediction_id(dt: datetime) -> str:
    bucket = _bucket_time(dt)
    return "NQ-P26-" + bucket.strftime("%Y%m%dT%H%MZ")


def _json_list(value: Iterable[Any]) -> str:
    return json.dumps([str(x) for x in value if str(x or "").strip()], separators=(",", ":"))


def _load(path: Path) -> List[Dict[str, str]]:
    if not path.exists() or path.stat().st_size == 0:
        return []
    with path.open("r", newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _write(path: Path, rows: List[Dict[str, Any]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FORWARD_FIELDS, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            normalized = {k: row.get(k, "") for k in FORWARD_FIELDS}
            writer.writerow(normalized)
    tmp.replace(path)
    return path


def _append(path: Path, row: Dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    exists = path.exists() and path.stat().st_size > 0
    with path.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FORWARD_FIELDS, extrasaction="ignore")
        if not exists:
            writer.writeheader()
        writer.writerow({k: row.get(k, "") for k in FORWARD_FIELDS})
    return path


def _snapshot_data(snapshot: Dict[str, Any] | None) -> Dict[str, Any]:
    raw = snapshot or {}
    if isinstance(raw, dict) and isinstance(raw.get("data"), dict):
        return raw["data"]
    return raw if isinstance(raw, dict) else {}


def _outcome(entry: float, future: float) -> str:
    if future > entry:
        return "BULLISH"
    if future < entry:
        return "BEARISH"
    return "NEUTRAL"


def record_forward_forecast(
    forecast: Any,
    snapshot: Dict[str, Any] | None,
    accuracy_assessment: Dict[str, Any] | None = None,
    path: Path | str = DEFAULT_FORWARD_PATH,
) -> Dict[str, Any]:
    """Persist one forward-only research checkpoint per configured time bucket.

    The first forecast in a bucket is frozen. Later refreshes cannot rewrite it,
    which protects the forward record from lookahead/revision bias.
    """
    path = Path(path)
    raw = _snapshot_data(snapshot)
    entry = _as_float(raw.get("nq_futures_price"))
    if entry is None or entry <= 0:
        return {
            "ok": False,
            "created": False,
            "reason": "NQ futures entry price unavailable; no mixed-proxy record created.",
            "path": str(path),
        }

    ts_value = _get(forecast, "generated_at", None) or datetime.now(timezone.utc).isoformat()
    ts = _parse_dt(ts_value)
    pid = _prediction_id(ts)

    rows = _load(path)
    for existing in rows:
        if existing.get("prediction_id") == pid:
            return {
                "ok": True,
                "created": False,
                "prediction_id": pid,
                "reason": "Time-bucket checkpoint already frozen; existing forward record preserved.",
                "path": str(path),
            }

    acc = accuracy_assessment or {}
    evidence = acc.get("evidence") or {}
    aligned = list(evidence.get("aligned_signals") or [])
    opposed = list(evidence.get("opposed_signals") or [])
    missing = list(evidence.get("missing_signals") or [])
    combo = "+".join(sorted(aligned)) if aligned else "NONE"

    row = {
        "prediction_id": pid,
        "timestamp": _iso(ts),
        "symbol": str(_get(forecast, "symbol", "NQ") or "NQ"),
        "direction": str(_get(forecast, "direction", "") or "").upper(),
        "bullish_probability": _get(forecast, "bullish_probability", ""),
        "bearish_probability": _get(forecast, "bearish_probability", ""),
        "confidence": _get(forecast, "confidence", ""),
        "regime": str(_get(forecast, "regime", "") or "").upper(),
        "data_coverage": _get(forecast, "data_coverage", ""),
        "intelligence_coverage": _get(forecast, "intelligence_coverage", ""),
        "phase24_grade": str(acc.get("setup_grade") or ""),
        "phase24_eligible": bool(acc.get("research_eligible", False)),
        "entry_nq": round(entry, 6),
        "aligned_signals": _json_list(aligned),
        "opposed_signals": _json_list(opposed),
        "missing_signals": _json_list(missing),
        "signal_combo": combo,
        "phase25_grade": "",
        "phase25_eligible": "",
        "confluence_score": "",
        "confluence_alignment": "",
        "confluence_completeness": "",
        "confluence_features": "",
        "alert_level": "",
        "target_4h": _iso(ts + timedelta(hours=4)),
        "target_8h": _iso(ts + timedelta(hours=8)),
        "nq_4h": "",
        "nq_8h": "",
        "actual_4h": "",
        "actual_8h": "",
        "correct_4h": "",
        "correct_8h": "",
        "resolved_4h_at": "",
        "resolved_8h_at": "",
    }
    _append(path, row)
    return {"ok": True, "created": True, "prediction_id": pid, "path": str(path)}


def build_research_alert(
    accuracy_assessment: Dict[str, Any] | None,
    confluence_assessment: Dict[str, Any] | None,
) -> Dict[str, Any]:
    acc = accuracy_assessment or {}
    con = confluence_assessment or {}
    p24 = str(acc.get("setup_grade") or "").upper()
    p25 = str(con.get("setup_grade") or "").upper()
    eligible = bool(acc.get("research_eligible")) and bool(con.get("research_eligible"))

    if eligible and p25 == "A++" and p24 in {"A+", "A++"}:
        level = "HIGH_QUALITY"
        active = True
    elif eligible and p25 == "A+" and p24 in {"A+", "A++"}:
        level = "QUALIFIED"
        active = True
    else:
        level = "NONE"
        active = False

    return {
        "active": active,
        "level": level,
        "phase24_grade": p24 or "UNKNOWN",
        "phase25_grade": p25 or "UNKNOWN",
        "research_only": True,
        "broker_execution": False,
        "note": (
            "High-quality research confluence detected. This is not an order or broker instruction."
            if active
            else "No Phase26 high-quality research alert."
        ),
    }


def attach_confluence(
    prediction_id: str,
    confluence_assessment: Dict[str, Any],
    accuracy_assessment: Dict[str, Any] | None = None,
    path: Path | str = DEFAULT_FORWARD_PATH,
) -> Dict[str, Any]:
    path = Path(path)
    rows = _load(path)
    alert = build_research_alert(accuracy_assessment, confluence_assessment)
    changed = False

    for row in rows:
        if row.get("prediction_id") != prediction_id:
            continue
        row["phase25_grade"] = confluence_assessment.get("setup_grade", "")
        row["phase25_eligible"] = bool(confluence_assessment.get("research_eligible", False))
        row["confluence_score"] = confluence_assessment.get("confluence_score", "")
        row["confluence_alignment"] = confluence_assessment.get("confluence_alignment", "")
        row["confluence_completeness"] = confluence_assessment.get("confluence_completeness", "")
        features = confluence_assessment.get("features") or {}
        compact = {
            k: {
                "present": bool(v.get("present")),
                "aligned": bool(v.get("aligned")),
            }
            for k, v in features.items()
            if isinstance(v, dict) and ("present" in v or "aligned" in v)
        }
        row["confluence_features"] = json.dumps(compact, separators=(",", ":"))
        row["alert_level"] = alert["level"]
        changed = True
        break

    if changed:
        _write(path, rows)
    return {"ok": changed, "prediction_id": prediction_id, "alert": alert, "path": str(path)}


def _nearest_close(frame, target: datetime, max_distance_minutes: float = 30.0) -> Optional[float]:
    if frame is None or getattr(frame, "empty", True):
        return None
    try:
        index = frame.index
        if index.tz is None:
            index = index.tz_localize(timezone.utc)
        else:
            index = index.tz_convert(timezone.utc)
        best_i = None
        best_sec = None
        for i, stamp in enumerate(index):
            sec = abs((stamp.to_pydatetime() - target).total_seconds())
            if best_sec is None or sec < best_sec:
                best_i = i
                best_sec = sec
        if best_i is None or best_sec is None or best_sec > max_distance_minutes * 60:
            return None
        close = frame.iloc[best_i].get("Close")
        return float(close) if close is not None and not math.isnan(float(close)) else None
    except Exception:
        return None


async def _load_recent_nq_frame():
    import yfinance as yf

    def load():
        return yf.Ticker("NQ=F").history(period="7d", interval="5m", auto_adjust=False)

    try:
        return await asyncio.to_thread(load)
    except Exception as exc:
        print("Phase26 NQ=F resolver error:", repr(exc))
        return None


async def resolve_due_forward_records(
    path: Path | str = DEFAULT_FORWARD_PATH,
    now: Optional[datetime] = None,
    price_lookup=None,
) -> int:
    """Resolve only completed 4H/8H targets using target-time NQ prices.

    If an exact-enough target candle cannot be obtained, the row remains pending.
    This deliberately avoids substituting the current price or a different asset.
    """
    path = Path(path)
    rows = _load(path)
    if not rows:
        return 0

    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    due_targets: List[datetime] = []
    for row in rows:
        for h in (4, 8):
            if row.get(f"nq_{h}h"):
                continue
            target_text = row.get(f"target_{h}h")
            if not target_text:
                continue
            target = _parse_dt(target_text)
            if target <= now:
                due_targets.append(target)

    if not due_targets:
        return 0

    frame = None
    if price_lookup is None:
        frame = await _load_recent_nq_frame()

    async def lookup(target: datetime):
        if price_lookup is None:
            return _nearest_close(frame, target)
        result = price_lookup(target)
        if inspect.isawaitable(result):
            result = await result
        return result

    changed = 0
    resolved_at = _iso(now)
    for row in rows:
        entry = _as_float(row.get("entry_nq"))
        predicted = str(row.get("direction") or "").upper()
        if entry is None or entry <= 0 or predicted not in {"BULLISH", "BEARISH"}:
            continue

        for h in (4, 8):
            price_key = f"nq_{h}h"
            if row.get(price_key):
                continue
            target_text = row.get(f"target_{h}h")
            if not target_text:
                continue
            target = _parse_dt(target_text)
            if target > now:
                continue
            price = await lookup(target)
            price = _as_float(price)
            if price is None or price <= 0:
                continue
            actual = _outcome(entry, price)
            row[price_key] = round(price, 6)
            row[f"actual_{h}h"] = actual
            row[f"correct_{h}h"] = predicted == actual
            row[f"resolved_{h}h_at"] = resolved_at
            changed += 1

    if changed:
        _write(path, rows)
    return changed


def _bool_value(v: Any) -> Optional[bool]:
    if isinstance(v, bool):
        return v
    text = str(v or "").strip().lower()
    if text in {"true", "1", "yes"}:
        return True
    if text in {"false", "0", "no"}:
        return False
    return None


def _accuracy(rows: List[Dict[str, str]], h: int) -> Dict[str, Any]:
    vals = [_bool_value(r.get(f"correct_{h}h")) for r in rows]
    vals = [v for v in vals if v is not None]
    correct = sum(1 for v in vals if v)
    return {
        "resolved": len(vals),
        "correct": correct,
        "accuracy": round(correct / len(vals) * 100.0, 2) if vals else None,
    }


def _rolling(rows: List[Dict[str, str]], h: int, window: int) -> Dict[str, Any]:
    resolved = [r for r in rows if _bool_value(r.get(f"correct_{h}h")) is not None]
    resolved.sort(key=lambda r: r.get("timestamp", ""))
    subset = resolved[-window:]
    out = _accuracy(subset, h)
    out["window"] = window
    out["available"] = len(subset)
    return out


def calibration_report(rows: List[Dict[str, str]], h: int) -> Dict[str, Any]:
    obs = []
    for r in rows:
        actual = str(r.get(f"actual_{h}h") or "").upper()
        p = _as_float(r.get("bullish_probability"))
        if actual not in {"BULLISH", "BEARISH"} or p is None:
            continue
        p = max(0.0, min(1.0, p / 100.0))
        y = 1.0 if actual == "BULLISH" else 0.0
        obs.append((p, y))

    if not obs:
        return {"n": 0, "brier": None, "ece": None, "bins": [], "status": "INSUFFICIENT_SAMPLE"}

    brier = sum((p - y) ** 2 for p, y in obs) / len(obs)
    bins = []
    ece = 0.0
    edges = [(0.0, 0.2), (0.2, 0.4), (0.4, 0.6), (0.6, 0.8), (0.8, 1.000001)]
    for lo, hi in edges:
        vals = [(p, y) for p, y in obs if lo <= p < hi]
        if not vals:
            continue
        avg_p = sum(p for p, _ in vals) / len(vals)
        actual_rate = sum(y for _, y in vals) / len(vals)
        ece += (len(vals) / len(obs)) * abs(avg_p - actual_rate)
        bins.append({
            "band": f"{int(lo*100)}-{100 if hi > 1 else int(hi*100)}%",
            "n": len(vals),
            "avg_predicted_bullish": round(avg_p * 100, 2),
            "actual_bullish_rate": round(actual_rate * 100, 2),
        })

    status = "ACTIVE" if len(obs) >= 50 else "EARLY" if len(obs) >= 20 else "INSUFFICIENT_SAMPLE"
    return {
        "n": len(obs),
        "brier": round(brier, 4),
        "ece": round(ece, 4),
        "bins": bins,
        "status": status,
        "note": "Forward-only calibration; unresolved observations are excluded.",
    }


def signal_combination_attribution(
    rows: List[Dict[str, str]],
    min_n: int = 5,
) -> Dict[str, Any]:
    groups: Dict[str, List[Dict[str, str]]] = {}
    for r in rows:
        combo = str(r.get("signal_combo") or "NONE")
        groups.setdefault(combo, []).append(r)

    out = []
    for combo, grp in groups.items():
        a4 = _accuracy(grp, 4)
        a8 = _accuracy(grp, 8)
        n = max(a4["resolved"], a8["resolved"])
        if n < min_n:
            continue
        out.append({"combination": combo, "n": n, "4h": a4, "8h": a8})

    out.sort(
        key=lambda x: (
            (x["4h"]["accuracy"] if x["4h"]["accuracy"] is not None else -1),
            x["n"],
        ),
        reverse=True,
    )
    return {
        "minimum_sample": min_n,
        "groups": out,
        "note": "Descriptive forward attribution only; small groups are suppressed to reduce overfitting risk.",
    }


def _grade_breakdown(rows: List[Dict[str, str]], h: int) -> List[Dict[str, Any]]:
    grades: Dict[str, List[Dict[str, str]]] = {}
    for r in rows:
        grade = str(r.get("phase25_grade") or "UNLABELED").upper()
        grades.setdefault(grade, []).append(r)
    out = []
    for grade, grp in grades.items():
        a = _accuracy(grp, h)
        if a["resolved"]:
            out.append({"grade": grade, **a})
    return sorted(out, key=lambda x: x["grade"])


def forward_validation_report(
    path: Path | str = DEFAULT_FORWARD_PATH,
    rolling_windows: Iterable[int] = (20, 50),
) -> Dict[str, Any]:
    path = Path(path)
    rows = _load(path)
    a4 = _accuracy(rows, 4)
    a8 = _accuracy(rows, 8)
    max_resolved = max(a4["resolved"], a8["resolved"])
    status = "ACTIVE" if max_resolved >= 50 else "EARLY" if max_resolved >= 20 else "INSUFFICIENT_SAMPLE"

    return {
        "status": status,
        "records": len(rows),
        "4h": a4,
        "8h": a8,
        "rolling_4h": [_rolling(rows, 4, int(w)) for w in rolling_windows],
        "rolling_8h": [_rolling(rows, 8, int(w)) for w in rolling_windows],
        "phase25_grade_4h": _grade_breakdown(rows, 4),
        "phase25_grade_8h": _grade_breakdown(rows, 8),
        "warning": "Forward checkpoints can overlap in horizon; accuracy is descriptive and is not treated as independent-trial statistical proof.",
    }


def build_learning_status(path: Path | str = DEFAULT_FORWARD_PATH) -> Dict[str, Any]:
    path = Path(path)
    rows = _load(path)
    pending_4h = sum(1 for r in rows if not r.get("nq_4h"))
    pending_8h = sum(1 for r in rows if not r.get("nq_8h"))
    high_alerts = sum(1 for r in rows if r.get("alert_level") == "HIGH_QUALITY")
    qualified_alerts = sum(1 for r in rows if r.get("alert_level") == "QUALIFIED")
    last = rows[-1] if rows else None

    return {
        "ok": True,
        "phase": "PHASE 26",
        "module": "Learning & Forward Validation",
        "forward_file": str(path),
        "records": len(rows),
        "pending": {"4h": pending_4h, "8h": pending_8h},
        "alerts": {"high_quality": high_alerts, "qualified": qualified_alerts},
        "validation": forward_validation_report(path),
        "calibration": {
            "4h": calibration_report(rows, 4),
            "8h": calibration_report(rows, 8),
        },
        "signal_combinations": signal_combination_attribution(rows),
        "last_record": last,
        "protections": {
            "forward_only": True,
            "first_checkpoint_frozen": True,
            "target_time_resolution": True,
            "missing_target_price_stays_pending": True,
            "broker_execution": False,
        },
    }
