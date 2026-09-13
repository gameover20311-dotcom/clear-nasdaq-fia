"""CLEAR NASDAQ — PRE-MOVE WATCH (V6.6.2)

The product question this layer answers:

    "Given ONLY information available before the outcome, what does the current
     evidence imply about the next 4H and 8H NQ distribution?"

Design commitments (each one exists because an audit found the opposite behaviour):

1. SEPARATE 4H AND 8H. Before this module the live system produced a single 8H
   number while the dashboard still reported accuracy_4h / brier_4h, and
   /api/cognitive/forecast?horizon=4h merely re-squashed the 8H probability through
   a different Platt model. Here each horizon is built from its own evidence
   weighting, and each carries its own state.

2. NO_EDGE IS A FIRST-CLASS OUTCOME. Absent evidence produces an abstention, never
   a directional call. A probability near 50 is NOT an abstention; absent evidence is.

3. CALIBRATION NEVER MANUFACTURES DIRECTION. The fitted Platt models carry non-zero
   intercepts (8h b=0.29091559 => +7.22 pts at the no-information point; 4h
   b=0.10794294 => +2.70 pts). That tilt is measured and published on every payload
   as calibration_no_information_tilt_points so it can never hide again.

4. STABLE FORECAST IDENTITY. forecast_id is derived deterministically from the
   evidence hash. Identical evidence yields an identical id, so a refresh cannot
   mint a new forecast and probability-shift detection has a real prior to diff
   against.

5. SHIFT ALERTS ARE GATED, NOT CHATTY. A shift must clear a minimum magnitude, be
   built on fresh evidence of sufficient quality, persist across consecutive
   observations (hysteresis), and not duplicate an alert already raised.

6. RESEARCH INTELLIGENCE, NOT A TRADING SIGNAL. Nothing here sizes, routes or
   places an order, and no state is named BUY or SELL.

IMPORTANT HONESTY NOTE carried in every payload: as of this release neither horizon
has demonstrated a measurable predictive edge. Retrospective performance over 258
forecasts was 4H 45.38% (113/249) and 8H 46.08% (94/204), both statistically
indistinguishable from chance, with Brier scores worse than an always-50% baseline.
This layer is built to report evidence honestly, not to imply skill that the
measurements do not support.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import math
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .market_sessions import session_state, summarize as session_summary

ROOT = Path(__file__).resolve().parents[1]
STORE = Path(os.getenv("FIA_PREMOVE_WATCH_DIR", str(ROOT / "fia_premove_watch")))
LEDGER = STORE / "premove_watch.jsonl"
HEAD = STORE / "premove_watch.head.json"
LOCKF = STORE / ".premove_watch.lock"

SCHEMA_VERSION = "premove-watch-1"

# ---------------------------------------------------------------- states
STATE_WATCH = "WATCH"
STATE_SHIFT = "SHIFT_DETECTED"
STATE_NO_EDGE = "NO_EDGE"
STATE_DEGRADED = "DEGRADED"
STATE_STALE = "STALE"
STATE_MISSING = "MISSING_DATA"

# ---------------------------------------------------------------- thresholds
MIN_SHIFT_POINTS = float(os.getenv("FIA_WATCH_MIN_SHIFT_POINTS", "8.0"))
HYSTERESIS_OBSERVATIONS = int(os.getenv("FIA_WATCH_HYSTERESIS", "2"))
MAX_EVIDENCE_AGE_SECONDS = float(os.getenv("FIA_WATCH_MAX_EVIDENCE_AGE", "900"))
MIN_EVIDENCE_QUALITY = float(os.getenv("FIA_WATCH_MIN_EVIDENCE_QUALITY", "0.35"))

# ---------------------------------------------------------------- NO_EDGE gate
# A direction is only published when the evidence separates the two outcomes by
# more than the measured noise floor.
#
# WHY THESE NUMBERS ARE DEFENSIBLE, NOT COSMETIC:
#   * The mapping is p = 50 + 25*normalized, so 1 published point == 0.04 of
#     normalized evidence score. MIN_EDGE_POINTS = 2.0 therefore demands that the
#     weighted evidence score reach |0.08| before any direction is claimed.
#   * Measured performance over 258 historical forecasts is Brier 0.2662 (4H) /
#     0.2676 (8H) against a 0.25 always-50 baseline -- i.e. WORSE than
#     uninformative. A separation smaller than the noise floor cannot be
#     presented as a directional research call.
#   * MIN_CONFIDENCE = 5.0 is the same bar expressed on the confidence scale:
#     coverage 1.0 x diversity 1.0 x (2.0/25) = 8.0, so 5.0 still admits a
#     genuine 2-point edge that is carrying some coverage or diversity penalty,
#     while rejecting the sub-2% confidence calls the system was publishing.
# Both conditions must hold. Failing either yields NO_EDGE with the raw and
# calibrated probabilities PRESERVED for transparency -- never rewritten to 50/50.
MIN_EDGE_POINTS = float(os.getenv("FIA_WATCH_MIN_EDGE_POINTS", "2.0"))
MIN_CONFIDENCE_FOR_DIRECTION = float(os.getenv("FIA_WATCH_MIN_CONFIDENCE", "5.0"))
# Effective independent contributors required before confidence gets full credit.
DIVERSITY_REFERENCE = float(os.getenv("FIA_WATCH_DIVERSITY_REFERENCE", "5.0"))
# Stale or unknown-age evidence cannot support high confidence.
STALE_CONFIDENCE_CAP = float(os.getenv("FIA_WATCH_STALE_CONF_CAP", "25.0"))
UNKNOWN_AGE_CONFIDENCE_CAP = float(os.getenv("FIA_WATCH_UNKNOWN_AGE_CONF_CAP", "25.0"))
# A hard-bad status token (ERROR/FAILED/DOWN/DEAD) is stronger than a soft degrade
# and must not support a mid-confidence directional call.
HARD_BAD_CONFIDENCE_CAP = float(os.getenv("FIA_WATCH_HARD_BAD_CONF_CAP", "15.0"))

# Horizon-specific evidence weighting. A 4H view leans on structure and immediate
# momentum; an 8H view gives macro, rates and catalysts more room to express.
# These are declared research priors, not fitted parameters — they were not tuned
# against the outcome column, and the ablation report states the measured effect.
HORIZON_WEIGHTS: Dict[str, Dict[str, float]] = {
    "4h": {
        "NQ structure": 1.35, "SPX confirmation": 1.15, "Semiconductors": 1.10,
        "Mega-cap leadership": 1.05, "Equal-weight participation": 1.00, "News": 0.85,
        "DXY": 0.70, "US10Y": 0.70, "Macro calendar": 0.55, "Earnings/guidance": 0.60,
    },
    "8h": {
        "NQ structure": 0.95, "SPX confirmation": 1.00, "Semiconductors": 1.00,
        "Mega-cap leadership": 1.10, "Equal-weight participation": 1.05, "News": 1.05,
        "DXY": 1.25, "US10Y": 1.25, "Macro calendar": 1.30, "Earnings/guidance": 1.25,
    },
}

DEAD_FRESHNESS = {"missing", "unavailable", "error", "unknown", ""}

# ---------------------------------------------------------------- truth labels
# The internal signal NAME is a stable lookup key used by weights, calibration,
# analogy and research modules; renaming it would silently change weight lookups
# in ten modules. What the trader sees must nonetheless be TRUE, so the display
# label and an explicit proxy flag are published alongside every driver.
#
# Two names were provably misleading:
#   "NQ structure"     -> computed from QQQ 60m Polygon bars, not NQ futures
#   "SPX confirmation" -> SPY normalised percent change, not an SPX divergence stat
SIGNAL_DISPLAY: Dict[str, Dict[str, Any]] = {
    "NQ structure": {
        "display_name": "QQQ Structure Proxy",
        "is_proxy": True,
        "measures": "QQQ 60m completed-bar range position and momentum",
        "not": "NQ futures structure",
    },
    "SPX confirmation": {
        "display_name": "SPY Confirmation Proxy",
        "is_proxy": True,
        "measures": "SPY normalised percent change",
        "not": "an SPX divergence statistic",
    },
    "Equal-weight participation": {
        "display_name": "Equal-Weight Participation",
        "is_proxy": True,
        "measures": "equal-weighted mean change of the 15 tracked large caps",
        "not": "market breadth or an advance/decline line",
    },
    "Breadth": {   # legacy key, same underlying data
        "display_name": "Equal-Weight Participation",
        "is_proxy": True,
        "measures": "equal-weighted mean change of the 15 tracked large caps",
        "not": "market breadth or an advance/decline line",
    },
}


def display_label(name: str) -> Dict[str, Any]:
    """Truthful presentation metadata for one signal. Never affects scoring."""
    meta = SIGNAL_DISPLAY.get(str(name))
    if not meta:
        return {"display_name": str(name), "is_proxy": False}
    return dict(meta)


# ---------------------------------------------------------------- freshness
# Which provider source backs each signal (mirrors engine.build_forecast).
SIGNAL_SOURCE: Dict[str, str] = {
    "NQ structure": "candles",
    "SPX confirmation": "market_quotes",
    "DXY": "dxy",
    "US10Y": "us10y",
    "Mega-cap leadership": "market_quotes",
    "Semiconductors": "market_quotes",
    "Equal-weight participation": "market_quotes",
    "Breadth": "market_quotes",          # legacy label, same source
    "News": "news",
    "Macro calendar": "macro",
    "Earnings/guidance": "earnings",
}

# HARD AGE CEILINGS, matched to each source's natural update cadence. Past the
# ceiling the evidence is EXCLUDED from directional scoring entirely -- a badge
# is not enough, because a 0.70 "delayed" weight still lets two-day-old rates
# move a 4-8H forecast. Excluded evidence is preserved for provenance and is
# never silently converted to a neutral vote.
MAX_AGE_SECONDS_BY_SOURCE: Dict[str, float] = {
    "market_quotes": 1800.0,    # 30 min  - quotes tick continuously
    "candles": 5400.0,          # 90 min  - one 60m bar plus margin
    "dxy": 21600.0,             # 6 h     - FX carries for hours, not days
    "us10y": 21600.0,           # 6 h     - same for rates
    "volatility": 21600.0,      # 6 h
    "news": 43200.0,            # 12 h    - slower decay than price
    "macro": 86400.0,           # 24 h    - scheduled, daily cadence
    "earnings": 86400.0,        # 24 h    - scheduled, daily cadence
}
DEFAULT_MAX_AGE_SECONDS = float(os.getenv("FIA_WATCH_DEFAULT_MAX_AGE", "21600"))

# Sources whose age MUST be establishable. If we cannot date them, they are
# excluded rather than trusted -- critical evidence fails closed.
AGE_CRITICAL_SOURCES = {"market_quotes", "candles"}


def _source_ages(snapshot: Optional[Dict[str, Any]]) -> Dict[str, Optional[float]]:
    """age_seconds per provider source, from the snapshot's source_health block."""
    snap = snapshot or {}
    data = snap.get("data") if isinstance(snap.get("data"), dict) else snap
    health = (data or {}).get("source_health")
    out: Dict[str, Optional[float]] = {}
    if isinstance(health, dict):
        for key, val in health.items():
            if isinstance(val, dict):
                out[str(key)] = _f(val.get("age_seconds"))
    return out


def age_gate(signal: Dict[str, Any], ages: Dict[str, Optional[float]],
             now=None) -> Dict[str, Any]:
    """Decide whether one signal is fresh enough to affect the probability.

    SESSION-AWARE (V6.6.5). Wall-clock age alone is the wrong test for a
    cash-session instrument. Verified 2026-09-07T02:28Z: ^TNX and ^VIX were 55h
    old purely because the cash market had been shut since Friday, while NQ=F and
    DX-Y.NYB were 0.2h old because futures reopened Sunday 18:00 ET. Excluding the
    former as "stale" would discard every cash input for ~62 hours a week and
    would misdescribe a correct last print as degraded data.

    A source is therefore judged against its OWN venue:
      market open   -> late past the live ceiling is STALE and excluded
      market closed -> an observation at/after the venue's last close is
                       CURRENT_FOR_SESSION and admissible, explicitly labelled
      either way    -> an observation older than the last close by more than the
                       grace is genuinely STALE and still excluded
    Unknown age on a critical source still fails closed.
    """
    name = str(signal.get("name") or "")
    source = SIGNAL_SOURCE.get(name)
    ceiling = MAX_AGE_SECONDS_BY_SOURCE.get(source or "", DEFAULT_MAX_AGE_SECONDS)
    age = ages.get(source) if source else None

    if age is None:
        if source in AGE_CRITICAL_SOURCES:
            return {"included": False, "reason": "AGE_UNKNOWN_FOR_CRITICAL_SOURCE",
                    "source": source, "age_seconds": None, "max_age_seconds": ceiling,
                    "freshness_state": "UNKNOWN_AGE", "market_open": None}
        return {"included": True, "reason": "AGE_UNKNOWN_NON_CRITICAL",
                "source": source, "age_seconds": None, "max_age_seconds": ceiling,
                "freshness_state": "UNKNOWN_AGE", "market_open": None}

    state = session_state(source or "", age, ceiling, now=now)
    included = bool(state.get("usable"))
    if included and state["freshness"] == "CURRENT_FOR_SESSION":
        reason = "CURRENT_FOR_SESSION_MARKET_CLOSED"
    elif included:
        reason = "WITHIN_AGE_CEILING"
    elif state["freshness"] == "STALE" and not state.get("market_open"):
        reason = "STALE_EXCLUDED_EVEN_ALLOWING_FOR_MARKET_CLOSURE"
    else:
        reason = "STALE_EXCLUDED_AGE_CEILING"
    return {"included": included, "reason": reason,
            "source": source, "age_seconds": round(age, 1), "max_age_seconds": ceiling,
            "freshness_state": state["freshness"], "venue": state.get("venue"),
            "market_open": state.get("market_open"),
            "seconds_since_venue_close": state.get("seconds_since_venue_close"),
            "session_reason": state.get("reason")}


# ---------------------------------------------------------------- helpers
def _utc() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: Optional[datetime] = None) -> str:
    return (dt or _utc()).isoformat()


def _canonical(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def sha256_obj(obj: Any) -> str:
    return hashlib.sha256(_canonical(obj)).hexdigest()


def _f(x: Any) -> Optional[float]:
    try:
        v = float(x)
        return v if math.isfinite(v) else None
    except (TypeError, ValueError):
        return None


def _parse_dt(x: Any) -> Optional[datetime]:
    if isinstance(x, (int, float)):
        try:
            return datetime.fromtimestamp(float(x), timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
    if not isinstance(x, str) or not x.strip():
        return None
    s = x.strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        d = datetime.fromisoformat(s)
        return d.replace(tzinfo=timezone.utc) if d.tzinfo is None else d.astimezone(timezone.utc)
    except ValueError:
        return None


def _status_tokens(v: Any) -> set:
    return {t for t in re.split(r"[^A-Z0-9]+", str(v or "").upper()) if t}


BAD_TOKENS = {"ERROR", "FAIL", "FAILED", "DOWN", "DEAD", "MISSING", "UNAVAILABLE"}
NOT_LIVE_TOKENS = {"DEMO", "SIMULATED", "SAMPLE", "PLACEHOLDER", "MOCK", "SYNTHETIC"}
DEGRADED_TOKENS = {"DEGRADED", "PARTIAL", "STALE"}


# ---------------------------------------------------------------- evidence view
def _signals(forecast: Dict[str, Any]) -> List[Dict[str, Any]]:
    out = []
    for s in (forecast.get("signals") or []):
        if isinstance(s, dict):
            out.append(s)
        elif hasattr(s, "model_dump"):
            out.append(s.model_dump())
        elif hasattr(s, "dict"):
            out.append(s.dict())
    return out


def _live_signals(signals: List[Dict[str, Any]],
                  ages: Optional[Dict[str, Optional[float]]] = None) -> List[Dict[str, Any]]:
    """Signals eligible to move the probability.

    A signal must have a usable score, a non-dead freshness label AND be inside
    the hard age ceiling for its source. Age-excluded signals are dropped from
    scoring here; the exclusion record is produced separately by
    `excluded_signals` so it stays visible rather than silently vanishing.
    """
    ages = ages or {}
    live = []
    for s in signals:
        fr = str(s.get("freshness") or "").lower()
        sc = _f(s.get("score"))
        if fr in DEAD_FRESHNESS or sc is None:
            continue
        if not age_gate(s, ages)["included"]:
            continue
        live.append(s)
    return live


def excluded_signals(signals: List[Dict[str, Any]],
                     ages: Optional[Dict[str, Optional[float]]] = None) -> List[Dict[str, Any]]:
    """Signals dropped by the age ceiling, kept for provenance and audit."""
    ages = ages or {}
    out = []
    for s in signals:
        fr = str(s.get("freshness") or "").lower()
        if fr in DEAD_FRESHNESS or _f(s.get("score")) is None:
            continue
        gate = age_gate(s, ages)
        if not gate["included"]:
            out.append({"name": s.get("name"), "freshness": s.get("freshness"),
                        "score_withheld": _f(s.get("score")), **gate})
    return out


def _horizon_probability(signals: List[Dict[str, Any]], horizon: str) -> Tuple[Optional[float], Dict[str, Any]]:
    """Evidence-weighted directional score -> raw probability for one horizon.

    Returns (None, meta) when no live signal supports the horizon, which the caller
    turns into NO_EDGE rather than a 50/50 forecast.
    """
    weights = HORIZON_WEIGHTS.get(horizon, {})
    num = 0.0
    den = 0.0
    contributions = []
    for s in signals:
        name = str(s.get("name") or "")
        score = _f(s.get("score"))
        base_w = _f(s.get("weight")) or 0.0
        if score is None or base_w <= 0:
            continue
        hw = weights.get(name, 1.0)
        w = base_w * hw
        num += score * w
        den += abs(w)
        contributions.append({
            "name": name, "score": round(score, 6),
            "base_weight": round(base_w, 4), "horizon_multiplier": hw,
            "effective_weight": round(w, 6),
            "freshness": s.get("freshness"),
        })
    if den <= 0 or not contributions:
        return None, {"contributions": [], "weighted_score": None,
                      "reason": "no live weighted signal for horizon"}
    normalized = max(-1.0, min(1.0, num / den))
    # Deliberately conservative mapping: a fully saturated one-sided evidence set
    # reaches 75/25, not 99/1. The measured Brier scores do not justify sharper claims.
    raw = 50.0 + normalized * 25.0
    contributions.sort(key=lambda c: -abs(c["effective_weight"] * c["score"]))
    return raw, {"contributions": contributions,
                 "weighted_score": round(normalized, 6),
                 "mapping": "p = 50 + 25 * clamp(sum(score*w)/sum(|w|), -1, 1)"}


def _calibrate(raw: float, horizon: str, models: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Apply the fitted Platt model and PUBLISH its no-information tilt."""
    m = ((models or {}).get("horizons") or {}).get(horizon) or {}
    if not m.get("available"):
        return {"calibrated": round(raw, 3), "applied": False,
                "no_information_tilt_points": 0.0,
                "reason": "no fitted calibration for horizon"}
    a = float(m.get("a", 1.0))
    b = float(m.get("b", 0.0))

    def sig(z: float) -> float:
        return 1.0 / (1.0 + math.exp(-z))

    def logit(p: float) -> float:
        p = min(max(p, 0.01), 0.99)
        return math.log(p / (1.0 - p))

    cal = 100.0 * sig(a * logit(raw / 100.0) + b)
    tilt = 100.0 * sig(b) - 50.0          # what the model does to a pure 50.0
    return {"calibrated": round(cal, 3), "applied": True, "a": a, "b": b,
            "n": m.get("n"), "method": m.get("method"),
            "no_information_tilt_points": round(tilt, 3),
            "tilt_note": ("the fitted intercept alone moves a no-information 50.0 by "
                          "%+.2f points; this is an unconditional base rate, not evidence"
                          % tilt)}


# ---------------------------------------------------------------- evidence quality
def evidence_quality(forecast: Dict[str, Any], snapshot: Dict[str, Any],
                     provider_health: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    signals = _signals(forecast)
    ages = _source_ages(snapshot)
    live = _live_signals(signals, ages)
    age_excluded = excluded_signals(signals, ages)
    total_w = sum((_f(s.get("weight")) or 0.0) for s in signals) or 1.0
    live_w = sum((_f(s.get("weight")) or 0.0) for s in live)
    coverage = max(0.0, min(1.0, live_w / total_w))

    snap_status = (snapshot or {}).get("status")
    fc_status = forecast.get("status")
    ph = (provider_health or {}).get("provider_health") if isinstance(provider_health, dict) else None
    ph = ph if isinstance(ph, dict) else {}
    ph_overall = ph.get("overall")

    tokens = _status_tokens(snap_status) | _status_tokens(fc_status) | _status_tokens(ph_overall)
    hard_bad = bool(tokens & BAD_TOKENS)
    not_live = bool(tokens & NOT_LIVE_TOKENS)
    degraded = bool(tokens & DEGRADED_TOKENS)

    # Freshest underlying market observation we can actually point at.
    obs = _parse_dt((snapshot or {}).get("timestamp"))
    age = (_utc() - obs).total_seconds() if obs else None

    grade = "HIGH" if coverage >= .70 else "MEDIUM" if coverage >= .45 else "LOW" if coverage >= .20 else "NONE"
    return {
        "coverage": round(coverage, 4),
        "grade": grade,
        "live_signal_count": len(live),
        "total_signal_count": len(signals),
        "snapshot_status": snap_status,
        "forecast_status": fc_status,
        "provider_health_overall": ph_overall,
        "provider_health_known": bool(ph),
        "hard_bad": hard_bad,
        "not_live": not_live,
        "degraded": degraded,
        "market_observation_utc": _iso(obs) if obs else None,
        "market_observation_age_seconds": round(age, 1) if age is not None else None,
        "stale": bool(age is not None and age > MAX_EVIDENCE_AGE_SECONDS),
        "age_unknown": obs is None,
        # Evidence dropped by a per-source hard age ceiling. Visible, never silent,
        # and never converted into a neutral vote.
        "age_excluded_signals": age_excluded,
        "age_excluded_count": len(age_excluded),
        # Session context: whether the venues were even open. Without this a
        # weekend reads as a data outage.
        "market_session": session_summary(),
    }


# ---------------------------------------------------------------- ledger
def _ensure_store() -> None:
    STORE.mkdir(parents=True, exist_ok=True)


def _read_rows() -> List[Dict[str, Any]]:
    if not LEDGER.exists():
        return []
    rows = []
    for line in LEDGER.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            # A truncated tail is a corruption signal, not something to skip silently.
            rows.append({"__corrupt__": True, "raw": line[:200]})
    return rows


def previous_observation() -> Optional[Dict[str, Any]]:
    for row in reversed(_read_rows()):
        if not row.get("__corrupt__"):
            return row
    return None


def verify_chain() -> Dict[str, Any]:
    rows = _read_rows()
    issues: List[str] = []
    prev = ""
    for i, r in enumerate(rows, 1):
        if r.get("__corrupt__"):
            issues.append("corrupt_row:%d" % i)
            continue
        if r.get("prev_hash", "") != prev:
            issues.append("chain_break:%d" % i)
        body = {k: v for k, v in r.items() if k != "row_hash"}
        if r.get("row_hash") != sha256_obj(body):
            issues.append("row_hash_mismatch:%d" % i)
        prev = r.get("row_hash", "")
    if rows and HEAD.exists():
        try:
            head = json.loads(HEAD.read_text(encoding="utf-8"))
            if head.get("rows") != len([r for r in rows if not r.get("__corrupt__")]):
                issues.append("head_row_count")
            if head.get("head_hash") != prev:
                issues.append("head_hash")
        except (json.JSONDecodeError, OSError) as exc:
            issues.append("unreadable_head:%s" % exc)
    elif rows and not HEAD.exists():
        issues.append("missing_head_anchor")
    return {"ok": not issues, "rows": len(rows), "head_hash": prev,
            "issues": issues, "tamper_evident": not issues}


def _append(row: Dict[str, Any]) -> Dict[str, Any]:
    """Append one observation under an exclusive lock, atomically."""
    _ensure_store()
    with LOCKF.open("a+", encoding="utf-8") as lh:
        fcntl.flock(lh.fileno(), fcntl.LOCK_EX)
        try:
            rows = [r for r in _read_rows() if not r.get("__corrupt__")]
            prev = rows[-1]["row_hash"] if rows else ""
            body = dict(row)
            body["seq"] = len(rows) + 1
            body["prev_hash"] = prev
            body["row_hash"] = sha256_obj(body)
            with LEDGER.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(body, ensure_ascii=False, sort_keys=True) + "\n")
                fh.flush()
                os.fsync(fh.fileno())
            head = {"schema_version": SCHEMA_VERSION, "rows": body["seq"],
                    "head_hash": body["row_hash"], "updated_at_utc": _iso()}
            fd, tmp = tempfile.mkstemp(dir=str(STORE), suffix=".tmp")
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(head, fh, indent=2)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp, HEAD)          # atomic head swap
            return body
        finally:
            fcntl.flock(lh.fileno(), fcntl.LOCK_UN)


# ---------------------------------------------------------------- main entry
def build_watch(forecast: Any, snapshot: Optional[Dict[str, Any]] = None,
                provider_health: Optional[Dict[str, Any]] = None,
                calibration_models: Optional[Dict[str, Any]] = None,
                persist: bool = False) -> Dict[str, Any]:
    """Build the PRE-MOVE WATCH view for both horizons from prediction-time evidence."""
    if hasattr(forecast, "model_dump"):
        fc = forecast.model_dump()
    elif hasattr(forecast, "dict"):
        fc = forecast.dict()
    elif isinstance(forecast, dict):
        fc = dict(forecast)
    else:
        fc = dict(getattr(forecast, "__dict__", {}) or {})

    snapshot = snapshot or {}
    signals = _signals(fc)
    _ages = _source_ages(snapshot)
    live = _live_signals(signals, _ages)
    quality = evidence_quality(fc, snapshot, provider_health)

    # Evidence hash covers ONLY prediction-time inputs. It must be reproducible.
    evidence_view = sorted(
        [{"name": s.get("name"), "score": _f(s.get("score")),
          "weight": _f(s.get("weight")), "freshness": s.get("freshness")} for s in signals],
        key=lambda x: str(x["name"]))
    evidence_hash = sha256_obj({
        "signals": evidence_view,
        "market_observation_utc": quality["market_observation_utc"],
        "snapshot_status": quality["snapshot_status"],
    })
    # Deterministic identity: identical evidence => identical forecast_id.
    forecast_id = "pmw-" + evidence_hash[:24]

    if calibration_models is None:
        try:
            # PRE-MOVE uses its OWN slope-only calibration, fitted on pre-move raw
            # scores. The cognitive model was fitted on a different quantity and,
            # measured on the untouched holdout, its intercept made Brier worse on
            # both horizons while being able to flip the published direction.
            from .cognitive.calibration import load_premove_models
            calibration_models = load_premove_models()
        except Exception:
            calibration_models = None

    horizons: Dict[str, Any] = {}
    for h in ("4h", "8h"):
        raw, meta = _horizon_probability(live, h)
        if raw is None:
            horizons[h] = {
                "state": STATE_NO_EDGE, "direction": "NO_EDGE",
                "bullish_probability": None, "bearish_probability": None,
                "confidence": 0.0, "raw_probability": None,
                "calibration": {"applied": False, "reason": "no evidence to calibrate"},
                "drivers": [], "conflicts": [],
                "reason": meta.get("reason", "no live evidence for this horizon"),
            }
            continue
        cal = _calibrate(raw, h, calibration_models)
        p = float(cal["calibrated"]) if cal.get("applied") else float(raw)

        # DIRECTION FOLLOWS THE EVIDENCE, NOT THE FITTED BASE RATE.
        # The 8h Platt intercept alone is worth +7.22 points, which is enough to turn a
        # slightly bearish evidence score (e.g. raw 49.28) into a 56.85% BULLISH call.
        # Calibration may sharpen or soften a probability; it must never decide the sign.
        # We therefore take direction from the raw evidence score and publish the
        # disagreement explicitly whenever calibration would have flipped it.
        raw_dir = "BULLISH" if raw > 50.0 else ("BEARISH" if raw < 50.0 else "BALANCED")
        cal_dir = "BULLISH" if p > 50.0 else ("BEARISH" if p < 50.0 else "BALANCED")
        flipped = bool(cal.get("applied")) and raw_dir != cal_dir and "BALANCED" not in (raw_dir, cal_dir)

        contribs = meta["contributions"]
        bull = [c for c in contribs if (c["score"] or 0) > 0]
        bear = [c for c in contribs if (c["score"] or 0) < 0]

        # EVIDENCE DIVERSITY. Confidence must not rise simply because a few
        # heavily-correlated signals all point the same way. The effective number
        # of independent contributors is the inverse Herfindahl of the effective
        # weights; full credit requires DIVERSITY_REFERENCE of them.
        _w = [abs(c["effective_weight"]) for c in contribs if c["effective_weight"]]
        _sw = sum(_w)
        _sw2 = sum(x * x for x in _w)
        effective_contributors = ((_sw * _sw) / _sw2) if _sw2 > 0 else 0.0
        diversity_factor = min(1.0, effective_contributors / DIVERSITY_REFERENCE) if DIVERSITY_REFERENCE > 0 else 1.0

        # Confidence is bounded by evidence coverage, evidence strength and
        # evidence diversity. It is NOT the probability.
        conf = max(0.0, min(100.0, 100.0 * quality["coverage"]
                            * min(1.0, abs(raw - 50.0) / 25.0)
                            * diversity_factor))
        if quality["degraded"] or quality["not_live"]:
            conf = min(conf, 45.0)
        # Stale evidence cannot support high confidence, and an observation whose
        # age we cannot establish is NOT treated as fresh -- unknown is not neutral.
        if quality.get("stale"):
            conf = min(conf, STALE_CONFIDENCE_CAP)
        if quality.get("age_unknown"):
            conf = min(conf, UNKNOWN_AGE_CONFIDENCE_CAP)
        # A hard-bad provider/forecast status is a fail-closed condition. The soft
        # 45-point degrade cap never binds in practice because ordinary confidence
        # is already below it, so a genuine ERROR was still publishing a mid-
        # confidence directional call.
        if quality.get("hard_bad"):
            conf = min(conf, HARD_BAD_CONFIDENCE_CAP)
        if flipped:
            # Evidence and fitted base rate disagree about the sign. That is a genuine
            # conflict, and confidence must fall, not rise.
            conf = min(conf, 20.0)
        # The PUBLISHED probability must agree with the published direction. When the
        # fitted base rate would flip the sign, we publish the EVIDENCE probability and
        # expose the calibrated value separately, rather than printing "BEARISH 52.69%
        # bullish", which is a self-contradicting headline.
        published = round(raw, 2) if flipped else round(p, 2)
        horizons[h] = {
            "state": STATE_WATCH,
            "direction": raw_dir,
            "bullish_probability": published,
            "bearish_probability": round(100.0 - published, 2),
            "calibrated_bullish_probability": round(p, 2),
            "published_probability_basis": ("raw_evidence__calibration_disagreed_on_sign"
                                            if flipped else "calibrated"),
            "evidence_direction": raw_dir,
            "calibrated_direction": cal_dir,
            "calibration_flips_direction": flipped,
            "direction_basis": "raw_evidence_score__calibration_may_not_decide_sign",
            "confidence": round(conf, 2),
            "confidence_basis": {
                "coverage": quality["coverage"],
                "evidence_strength": round(min(1.0, abs(raw - 50.0) / 25.0), 6),
                "effective_contributors": round(effective_contributors, 3),
                "diversity_factor": round(diversity_factor, 6),
                "degraded_cap_applied": bool(quality["degraded"] or quality["not_live"]),
                "stale_cap_applied": bool(quality.get("stale")),
                "unknown_age_cap_applied": bool(quality.get("age_unknown")),
                "hard_bad_cap_applied": bool(quality.get("hard_bad")),
                "flip_cap_applied": bool(flipped),
                "definition": ("coverage x evidence_strength x diversity, then capped. "
                               "This is evidence quality, NOT probability and NOT win rate."),
            },
            "raw_probability": round(raw, 3),
            "calibration": cal,
            "weighted_score": meta["weighted_score"],
            "mapping": meta["mapping"],
            "drivers": [{"name": c["name"], "score": c["score"],
                         "effective_weight": c["effective_weight"],
                         "freshness": c["freshness"],
                         **display_label(c["name"])} for c in contribs[:5]],
            "conflicts": [{"name": c["name"], "score": c["score"]}
                          for c in (bear if len(bull) >= len(bear) else bull)[:4]],
            "supporting_signal_count": len(contribs),
        }

        # ---------------- NO_EDGE / INSUFFICIENT CONVICTION GATE -------------
        # A slightly-directional probability carrying almost no conviction is not
        # a research call. Both the evidence separation and the confidence must
        # clear the bar. Raw and calibrated probabilities are PRESERVED so the
        # estimate stays fully transparent; only the actionable state changes.
        _edge_points = abs(published - 50.0)
        _gate_reasons = []
        if _edge_points < MIN_EDGE_POINTS:
            _gate_reasons.append("edge_below_min:%.2f<%.2f" % (_edge_points, MIN_EDGE_POINTS))
        if conf < MIN_CONFIDENCE_FOR_DIRECTION:
            _gate_reasons.append("confidence_below_min:%.2f<%.2f"
                                 % (conf, MIN_CONFIDENCE_FOR_DIRECTION))
        horizons[h]["edge_points"] = round(_edge_points, 3)
        horizons[h]["conviction_gate"] = {
            "min_edge_points": MIN_EDGE_POINTS,
            "min_confidence": MIN_CONFIDENCE_FOR_DIRECTION,
            "edge_points": round(_edge_points, 3),
            "confidence": round(conf, 2),
            "passed": not _gate_reasons,
            "reasons": _gate_reasons,
            "rule": ("direction is published only when |published-50| >= min_edge_points "
                     "AND confidence >= min_confidence"),
        }
        if _gate_reasons:
            # Actionable state becomes NO_EDGE. The probabilities remain visible
            # and are NOT rewritten to 50/50.
            horizons[h]["state"] = STATE_NO_EDGE
            horizons[h]["direction"] = "NO_EDGE"
            horizons[h]["evidence_direction"] = raw_dir
            horizons[h]["actionable"] = False
            horizons[h]["no_edge_reason"] = "INSUFFICIENT_CONVICTION"
        else:
            horizons[h]["actionable"] = True

    # ---- overall state machine ----
    if quality["hard_bad"] or quality["live_signal_count"] == 0:
        state = STATE_MISSING if quality["live_signal_count"] == 0 else STATE_DEGRADED
    elif quality["stale"]:
        state = STATE_STALE
    elif quality["not_live"] or quality["degraded"]:
        state = STATE_DEGRADED
    elif quality["coverage"] < MIN_EVIDENCE_QUALITY:
        state = STATE_NO_EDGE
    else:
        state = STATE_WATCH

    if state in (STATE_MISSING, STATE_NO_EDGE):
        for h in horizons:
            horizons[h]["state"] = state
            horizons[h]["direction"] = "NO_EDGE"
            horizons[h]["bullish_probability"] = None
            horizons[h]["bearish_probability"] = None
            horizons[h]["confidence"] = 0.0

    # ---- probability shift vs the previous persisted observation ----
    prev = previous_observation()
    shift = _shift(prev, horizons, quality, state)
    if shift["state_change"] == STATE_SHIFT and state == STATE_WATCH:
        state = STATE_SHIFT

    catalyst = _catalyst_risk(fc, snapshot)

    out = {
        "schema_version": SCHEMA_VERSION,
        "system": "CLEAR NASDAQ — PRE-MOVE WATCH",
        "state": state,
        "forecast_id": forecast_id,
        "evidence_hash": evidence_hash,
        "forecast_timestamp_utc": _iso(),
        "market_observation_utc": quality["market_observation_utc"],
        "evidence_quality": quality,
        "horizons": horizons,
        "regime": fc.get("regime"),
        "catalyst_risk": catalyst,
        "invalidation": fc.get("invalidation") or [],
        "probability_shift": shift,
        "thresholds": {
            "min_shift_points": MIN_SHIFT_POINTS,
            "hysteresis_observations": HYSTERESIS_OBSERVATIONS,
            "max_evidence_age_seconds": MAX_EVIDENCE_AGE_SECONDS,
            "min_evidence_quality": MIN_EVIDENCE_QUALITY,
        },
        "policy": {
            "research_only": True,
            "auto_trading_signal": False,
            "broker_execution": False,
            "unknown_is_not_neutral": True,
            "no_edge_is_a_valid_answer": True,
            "calibration_may_not_manufacture_direction": True,
        },
        "measured_performance_disclosure": {
            "status": "NO_DEMONSTRATED_EDGE",
            "historical_4h_accuracy_pct": 45.38,
            "historical_4h_denominator": "113/249 resolved",
            "historical_8h_accuracy_pct": 46.08,
            "historical_8h_denominator": "94/204 resolved",
            "brier_4h": 0.2662,
            "brier_8h": 0.2676,
            "always_50_percent_baseline_brier": 0.25,
            "note": ("Both horizons are statistically indistinguishable from chance and "
                     "Brier is worse than an uninformative baseline. Treat every "
                     "probability here as a description of current evidence, not as "
                     "demonstrated forecasting skill."),
        },
    }

    if persist and state not in (STATE_MISSING,):
        try:
            row = _append({
                "schema_version": SCHEMA_VERSION,
                "observed_at_utc": out["forecast_timestamp_utc"],
                "forecast_id": forecast_id,
                "evidence_hash": evidence_hash,
                "state": state,
                "evidence_coverage": quality["coverage"],
                "evidence_grade": quality["grade"],
                "market_observation_utc": quality["market_observation_utc"],
                "h4_bullish": horizons["4h"].get("bullish_probability"),
                "h8_bullish": horizons["8h"].get("bullish_probability"),
                "h4_direction": horizons["4h"].get("direction"),
                "h8_direction": horizons["8h"].get("direction"),
                # Baseline carries forward until a shift is CONFIRMED, at which point
                # the confirmed state becomes the new baseline.
                "baseline_h4_bullish": (horizons["4h"].get("bullish_probability")
                                        if shift.get("detected") or prev is None
                                        else shift.get("baseline_h4_bullish")),
                "baseline_h8_bullish": (horizons["8h"].get("bullish_probability")
                                        if shift.get("detected") or prev is None
                                        else shift.get("baseline_h8_bullish")),
                "baseline_forecast_id": (forecast_id if shift.get("detected") or prev is None
                                         else shift.get("baseline_forecast_id")),
                "shift": shift,
            })
            out["ledger"] = {"seq": row["seq"], "row_hash": row["row_hash"],
                             "prev_hash": row["prev_hash"]}
        except Exception as exc:
            out["ledger"] = {"error": "%s: %s" % (type(exc).__name__, exc)}

    return out


def _shift(prev: Optional[Dict[str, Any]], horizons: Dict[str, Any],
           quality: Dict[str, Any], state: str) -> Dict[str, Any]:
    """Material-change detection with magnitude, freshness, quality, hysteresis and dedup."""
    base = {
        "state_change": None, "detected": False, "eligible": False,
        "h4_delta_points": None, "h8_delta_points": None,
        "previous_forecast_id": (prev or {}).get("forecast_id"),
        "previous_observed_at_utc": (prev or {}).get("observed_at_utc"),
        "before_hash": (prev or {}).get("evidence_hash"),
        "after_hash": None, "reasons": [], "pending_confirmation": False,
    }
    if prev is None:
        base["reasons"].append("no_prior_observation")
        return base
    if state in (STATE_MISSING, STATE_NO_EDGE, STATE_STALE):
        base["reasons"].append("state_not_eligible_for_shift:" + state)
        return base
    if quality["coverage"] < MIN_EVIDENCE_QUALITY:
        base["reasons"].append("evidence_quality_below_threshold")
        return base
    if quality["stale"] or quality["age_unknown"]:
        base["reasons"].append("evidence_not_fresh_enough")
        return base

    # Magnitude is measured against the BASELINE -- the state at the last confirmed
    # shift (or the first observation) -- not against the immediately preceding tick.
    # Measuring against the previous tick makes a confirmed alert unreachable: the
    # observation that moves is blocked by hysteresis, and by the time the direction
    # has persisted the tick-to-tick delta has already collapsed to noise.
    h4 = horizons["4h"].get("bullish_probability")
    h8 = horizons["8h"].get("bullish_probability")
    b4 = _f(prev.get("baseline_h4_bullish"))
    b8 = _f(prev.get("baseline_h8_bullish"))
    if b4 is None:
        b4 = _f(prev.get("h4_bullish"))
    if b8 is None:
        b8 = _f(prev.get("h8_bullish"))
    d4 = None if (h4 is None or b4 is None) else round(h4 - b4, 2)
    d8 = None if (h8 is None or b8 is None) else round(h8 - b8, 2)
    base["h4_delta_points"] = d4
    base["h8_delta_points"] = d8
    base["baseline_h4_bullish"] = b4
    base["baseline_h8_bullish"] = b8
    base["baseline_forecast_id"] = prev.get("baseline_forecast_id") or prev.get("forecast_id")
    base["eligible"] = True

    biggest = max([abs(x) for x in (d4, d8) if x is not None] or [0.0])
    if biggest < MIN_SHIFT_POINTS:
        base["reasons"].append("below_min_shift_points:%.2f<%.2f" % (biggest, MIN_SHIFT_POINTS))
        return base

    # Dedup: identical evidence must never raise the same alert twice.
    if prev.get("evidence_hash") and prev.get("evidence_hash") == base.get("after_hash"):
        base["reasons"].append("duplicate_evidence_hash")
        return base

    # Hysteresis: the new direction must persist across consecutive observations
    # before the shift is confirmed, so a single flickering refresh cannot alert.
    rows = [r for r in _read_rows() if not r.get("__corrupt__")]
    direction_now = horizons["8h"].get("direction") or horizons["4h"].get("direction")
    need = max(0, HYSTERESIS_OBSERVATIONS - 1)
    recent = rows[-need:] if need else []
    persisted = (len(recent) >= need) and all(
        (r.get("h8_direction") or r.get("h4_direction")) == direction_now for r in recent)
    if need and not persisted:
        base["reasons"].append("direction_not_persistent_across_hysteresis_window")
        base["pending_confirmation"] = True
        return base

    base["detected"] = True
    base["state_change"] = STATE_SHIFT
    base["magnitude_points"] = round(biggest, 2)
    base["direction"] = direction_now
    base["reasons"].append("material_change_confirmed")
    return base


def _catalyst_risk(fc: Dict[str, Any], snapshot: Dict[str, Any]) -> Dict[str, Any]:
    raw = (snapshot or {}).get("data") or snapshot or {}
    macro_high = raw.get("macro_high_impact")
    earnings_risk = raw.get("earnings_catalyst_risk")
    # One clear calendar cannot establish that *both* calendars are clear.
    # Missing macro + no earnings event used to manufacture a LOW risk label.
    # Only actual booleans are evidence; strings such as "false" are unknown.
    inputs = {"macro": macro_high, "earnings": earnings_risk}
    missing_inputs = [name for name, value in inputs.items()
                      if not isinstance(value, bool)]
    known_high = any(value is True for value in inputs.values())
    known = known_high or not missing_inputs
    level = "HIGH" if known_high else ("UNKNOWN" if missing_inputs else "LOW")
    return {
        "level": level,
        "macro_high_impact": macro_high,
        "earnings_catalyst_risk": earnings_risk,
        "known": known,
        "coverage_complete": not missing_inputs,
        "missing_inputs": missing_inputs,
        "note": (("Known high-impact catalyst; additional calendar coverage is missing."
                  if known_high else
                  "Calendar coverage is incomplete; overall catalyst risk is UNKNOWN.")
                 if missing_inputs else ""),
    }
