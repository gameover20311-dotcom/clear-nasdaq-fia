# PHASE28_MARKET_GRADE_REPLAY_V1
from __future__ import annotations

from bisect import bisect_right
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple
import json

UTC = timezone.utc
BACKEND = Path(__file__).resolve().parents[1]
P20 = BACKEND / "fia_backtest_phase20" / "data"
NQ_CACHE = P20 / "nq_5m_multicontract_20250901_20260831.json"
ES_CACHE = Path(__file__).resolve().parent / "data" / "es_5m_multicontract_20250901_20260831.json"
MACRO_CACHE = Path(__file__).resolve().parent / "data" / "finnhub_macro_calendar_20250901_20260831.json"


def parse_dt(value: Any) -> Optional[datetime]:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        text = str(value).strip().replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(text)
        except Exception:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def _ns_to_dt(value: Any) -> Optional[datetime]:
    try:
        return datetime.fromtimestamp(int(value) / 1_000_000_000, tz=UTC)
    except Exception:
        return None


class FuturesCache:
    """Raw overlapping futures contracts with point-in-time dominant-contract selection.

    IMPORTANT: selection uses only completed 5-minute bars available at `asof`.
    It never uses full-day or future volume and never creates a back-adjusted series.
    """

    def __init__(self, path: Path):
        self.path = Path(path)
        self.provider = "missing"
        self.symbol = ""
        self.by_contract: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        self.times: Dict[str, List[datetime]] = {}
        self._load()

    @property
    def available(self) -> bool:
        return bool(self.by_contract)

    @property
    def bar_count(self) -> int:
        return sum(len(v) for v in self.by_contract.values())

    def _load(self) -> None:
        if not self.path.exists():
            return
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        self.provider = str(payload.get("provider") or "unknown")
        self.symbol = str(payload.get("symbol") or "")
        for raw in payload.get("bars") or []:
            contract = str(raw.get("contract") or "")
            if not contract:
                continue
            ts = parse_dt(raw.get("timestamp")) or _ns_to_dt(raw.get("window_start"))
            if ts is None:
                continue
            try:
                row = {
                    "contract": contract,
                    "timestamp": ts,
                    "open": float(raw.get("open")),
                    "high": float(raw.get("high")),
                    "low": float(raw.get("low")),
                    "close": float(raw.get("close")),
                    "volume": float(raw.get("volume") or 0.0),
                }
            except Exception:
                continue
            self.by_contract[contract].append(row)
        for contract, rows in self.by_contract.items():
            rows.sort(key=lambda r: r["timestamp"])
            self.times[contract] = [r["timestamp"] for r in rows]

    def _slice(self, contract: str, start: datetime, end_completed: datetime) -> List[Dict[str, Any]]:
        rows = self.by_contract.get(contract) or []
        times = self.times.get(contract) or []
        if not rows:
            return []
        # 5-minute bar timestamp is bar start. Require bar_start + 5m <= asof.
        completed_cutoff = end_completed - timedelta(minutes=5)
        lo = bisect_right(times, start - timedelta(microseconds=1))
        hi = bisect_right(times, completed_cutoff)
        return rows[lo:hi]

    def dominant_contract(self, asof: datetime, lookback_hours: int = 24) -> Optional[str]:
        asof = parse_dt(asof) or asof
        start = asof - timedelta(hours=lookback_hours)
        best = None
        best_volume = -1.0
        best_last = None
        for contract in self.by_contract:
            rows = self._slice(contract, start, asof)
            if not rows:
                continue
            volume = sum(max(0.0, float(r.get("volume") or 0.0)) for r in rows)
            last = rows[-1]["timestamp"]
            if volume > best_volume or (volume == best_volume and (best_last is None or last > best_last)):
                best = contract
                best_volume = volume
                best_last = last
        return best

    def bars_asof(self, asof: datetime, lookback_days: int = 12) -> Tuple[Optional[str], List[Dict[str, Any]]]:
        asof = parse_dt(asof) or asof
        contract = self.dominant_contract(asof)
        if not contract:
            return None, []
        return contract, self._slice(contract, asof - timedelta(days=lookback_days), asof)

    def last_completed(self, asof: datetime, max_staleness_minutes: int = 90) -> Tuple[Optional[str], Optional[Dict[str, Any]], Optional[float]]:
        asof = parse_dt(asof) or asof
        contract, rows = self.bars_asof(asof, lookback_days=2)
        row, stale = self.last_completed_for_contract(
            contract, asof, max_staleness_minutes
        )
        return contract, row, stale

    def last_completed_for_contract(
        self,
        contract: Optional[str],
        asof: datetime,
        max_staleness_minutes: int = 90,
    ) -> Tuple[Optional[Dict[str, Any]], Optional[float]]:
        """Return a completed bar for one frozen contract.

        Replay entry chooses the dominant contract using information available
        at the checkpoint. Outcomes must remain on that same contract so a
        later roll decision cannot create an artificial price move.
        """
        if not contract:
            return None, None
        asof = parse_dt(asof) or asof
        rows = self._slice(contract, asof - timedelta(days=2), asof)
        if not rows:
            return None, None
        row = rows[-1]
        bar_end = row["timestamp"] + timedelta(minutes=5)
        stale = (asof - bar_end).total_seconds() / 60.0
        if stale < -1e-9 or stale > max_staleness_minutes:
            return None, stale
        return row, stale


def load_macro_cache(path: Path = MACRO_CACHE) -> Dict[str, Any]:
    if not Path(path).exists():
        return {"status": "missing", "events": [], "source": "Finnhub Economic Calendar"}
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return {"status": "invalid", "events": [], "source": "Finnhub Economic Calendar"}
    if not isinstance(payload, dict):
        return {"status": "invalid", "events": [], "source": "Finnhub Economic Calendar"}
    return payload


HIGH_IMPACT_TERMS = (
    "cpi", "consumer price", "pce", "personal consumption expenditures",
    "nonfarm", "non-farm", "payroll", "unemployment", "jobless claims",
    "fomc", "fed funds", "interest rate", "federal reserve",
    "ism manufacturing", "ism services", "pmi", "gross domestic product", "gdp",
    "retail sales",
)


def macro_context_asof(target: datetime, payload: Dict[str, Any]) -> Dict[str, Any]:
    """Point-in-time macro context. No unreleased actual/estimate is used in the forecast.

    The current production engine has no validated directional macro-surprise model.
    Phase 28 therefore uses real calendar timing as catalyst/risk context but leaves
    the directional `macro` signal missing rather than inventing a neutral vote or
    an unvalidated direction.
    """
    target = parse_dt(target) or target
    events = []
    upcoming = []
    released = []
    for raw in payload.get("events") or []:
        country = str(raw.get("country") or "").upper()
        if country not in {"US", "USA", "UNITED STATES"}:
            continue
        name = str(raw.get("event") or raw.get("name") or "")
        low = name.lower()
        impact = str(raw.get("impact") or "").lower()
        important = impact == "high" or any(term in low for term in HIGH_IMPACT_TERMS)
        if not important:
            continue
        dt = parse_dt(raw.get("time") or raw.get("timestamp") or raw.get("datetime"))
        if dt is None:
            continue
        item = dict(raw)
        item["_dt"] = dt
        events.append(item)
        if target - timedelta(hours=18) <= dt <= target:
            # Released values are only visible after event time.
            released.append(item)
        if target < dt <= target + timedelta(hours=8):
            # Upcoming event actual is intentionally NOT exposed.
            safe = {k: v for k, v in item.items() if k not in {"actual", "_dt"}}
            safe["time"] = dt.isoformat()
            upcoming.append(safe)

    nearest = min((x["_dt"] for x in events if x["_dt"] > target), default=None)
    return {
        "macro": None,
        "macro_status": "calendar_timing_only" if events else "missing",
        "macro_high_impact": bool(upcoming) or bool(released),
        "macro_event_risk": bool(upcoming),
        "macro_upcoming_events": len(upcoming),
        "macro_released_events": len(released),
        "macro_hours_to_next": round((nearest - target).total_seconds() / 3600.0, 3) if nearest else None,
        "macro_source": payload.get("source") or "Finnhub Economic Calendar",
        "macro_source_status": payload.get("status") or "unknown",
        "macro_upcoming_safe": upcoming[:10],
        "macro_released": [
            {k: (v.isoformat() if k == "_dt" else v) for k, v in x.items()}
            for x in released[:10]
        ],
    }
