"""Session-aware freshness for CLEAR NASDAQ evidence.

WHY THIS EXISTS
---------------
The V6.6.4 age gate measured wall-clock age only. That is wrong for any
cash-session instrument, and it produced a false diagnosis:

    Sunday 22:18 ET, ^TNX age 55.6h  -> reported "STALE, feed broken"

Nothing was broken. ^TNX is a CBOE cash index; it does not trade at the weekend.
Its last print genuinely IS Friday afternoon, and that is the true, current,
best-available value for the 10-year yield until the cash session reopens.
Verified empirically on 2026-09-07T02:28Z:

    ^TNX      last bar Fri 13:55 CDT  age 55.6h   cash index, market closed
    ^VIX      last bar Fri 15:10 CDT  age 54.3h   cash index, market closed
    QQQ       last bar Fri 15:55 EDT  age 54.6h   cash equity, market closed
    NQ=F      last bar Sun 22:15 EDT  age  0.2h   future, reopened 18:00 ET
    DX-Y.NYB  last bar Sun 22:15 EDT  age  0.2h   future-based, reopened

Treating the first three as "stale evidence to exclude" would discard every
cash input for ~62 hours of every week, and would also be dishonest in the other
direction: it implies the data is degraded when it is simply the last true print
of a closed market.

WHAT THIS MODULE DOES
---------------------
It answers one question per source: *should this instrument have produced a newer
observation by now?*

    MARKET_OPEN   -> age is measured against the live ceiling. Late = STALE.
    MARKET_CLOSED -> age is measured against the time the venue closed. An
                     observation at/after the last close is CURRENT_FOR_SESSION,
                     not stale, and is admissible with an explicit label.

A value that is stale even relative to its own last close IS genuinely stale and
is still excluded. Closure is never an excuse for missing data.

DELIBERATE NON-GOALS
--------------------
* No holiday calendar. US market holidays are not modelled, so a holiday looks
  like an open day and its inputs will be correctly flagged STALE rather than
  silently accepted. That fails closed, which is the safe direction, and it is
  reported honestly rather than approximated.
* No fabricated value is ever produced for a closed market.
"""
from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from typing import Any, Dict, Optional

try:  # stdlib on 3.9+, present in this venv
    from zoneinfo import ZoneInfo
    _ET = ZoneInfo("America/New_York")
except Exception:  # pragma: no cover - fail closed to UTC rather than crash
    _ET = timezone.utc

# ---------------------------------------------------------------- venue types
VENUE_CASH_EQUITY = "CASH_EQUITY"      # QQQ, SPY, single stocks: 09:30-16:00 ET Mon-Fri
VENUE_CASH_INDEX = "CASH_INDEX"        # ^TNX, ^VIX: quoted only during the cash session
VENUE_FUTURES = "FUTURES"              # NQ=F, ES=F, ZN=F, DX-Y.NYB: Sun 18:00 -> Fri 17:00 ET
VENUE_CONTINUOUS = "CONTINUOUS"        # news, calendars: no session concept
VENUE_UNKNOWN = "UNKNOWN"

# Which venue each provider source trades on.
SOURCE_VENUE: Dict[str, str] = {
    "market_quotes": VENUE_CASH_EQUITY,
    "candles": VENUE_CASH_EQUITY,
    "liquidity": VENUE_FUTURES,
    "dxy": VENUE_FUTURES,
    "us10y": VENUE_CASH_INDEX,
    "volatility": VENUE_CASH_INDEX,
    "news": VENUE_CONTINUOUS,
    "macro": VENUE_CONTINUOUS,
    "earnings": VENUE_CONTINUOUS,
    "earnings_calendar": VENUE_CONTINUOUS,
}

# Freshness states
FRESH_LIVE = "LIVE"
FRESH_CURRENT_FOR_SESSION = "CURRENT_FOR_SESSION"   # market shut; this IS the latest true print
FRESH_STALE = "STALE"                               # late even allowing for closure
FRESH_UNKNOWN_AGE = "UNKNOWN_AGE"


def _now_et(now: Optional[datetime] = None) -> datetime:
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    return now.astimezone(_ET)


def _last_cash_close(now_et: datetime) -> datetime:
    """Most recent 16:00 ET weekday close at or before `now_et`."""
    probe = now_et
    for _ in range(8):
        close = probe.replace(hour=16, minute=0, second=0, microsecond=0)
        if probe.weekday() < 5 and now_et >= close:
            return close
        probe = (probe - timedelta(days=1)).replace(hour=23, minute=59)
    return now_et - timedelta(days=7)


def _last_futures_close(now_et: datetime) -> datetime:
    """Futures run Sun 18:00 ET -> Fri 17:00 ET. Only closed Fri 17:00 -> Sun 18:00."""
    wd, t = now_et.weekday(), now_et.time()
    friday_close = (now_et - timedelta(days=(wd - 4) % 7)).replace(
        hour=17, minute=0, second=0, microsecond=0)
    if wd == 5:                                   # Saturday
        return friday_close
    if wd == 6 and t < time(18, 0):               # Sunday before reopen
        return friday_close - timedelta(days=1) if friday_close > now_et else friday_close
    if wd == 4 and t >= time(17, 0):              # Friday after close
        return now_et.replace(hour=17, minute=0, second=0, microsecond=0)
    return now_et                                 # open


def market_open(venue: str, now: Optional[datetime] = None) -> bool:
    et = _now_et(now)
    wd, t = et.weekday(), et.time()
    if venue == VENUE_CONTINUOUS:
        return True
    if venue in (VENUE_CASH_EQUITY, VENUE_CASH_INDEX):
        return wd < 5 and time(9, 30) <= t < time(16, 0)
    if venue == VENUE_FUTURES:
        if wd == 5:
            return False
        if wd == 6:
            return t >= time(18, 0)
        if wd == 4:
            return t < time(17, 0)
        return True
    return True                                   # unknown venue: do not excuse lateness


def session_state(source: str, age_seconds: Optional[float],
                  live_ceiling_seconds: float,
                  now: Optional[datetime] = None) -> Dict[str, Any]:
    """Classify one source's observation against its own trading session.

    Returns a dict carrying the freshness state, whether the evidence may be
    used, and the reason — so the decision is always auditable.
    """
    venue = SOURCE_VENUE.get(source, VENUE_UNKNOWN)
    et = _now_et(now)
    is_open = market_open(venue, now)

    if age_seconds is None:
        return {"freshness": FRESH_UNKNOWN_AGE, "venue": venue, "market_open": is_open,
                "usable": False, "age_seconds": None,
                "reason": "observation age could not be established"}

    if is_open or venue == VENUE_CONTINUOUS:
        usable = age_seconds <= live_ceiling_seconds
        return {"freshness": FRESH_LIVE if usable else FRESH_STALE,
                "venue": venue, "market_open": is_open, "usable": usable,
                "age_seconds": round(age_seconds, 1),
                "live_ceiling_seconds": live_ceiling_seconds,
                "reason": ("within live ceiling" if usable
                           else "market open but observation exceeds live ceiling")}

    # Market closed: judge the observation against the moment the venue shut.
    close_et = _last_cash_close(et) if venue in (VENUE_CASH_EQUITY, VENUE_CASH_INDEX) \
        else _last_futures_close(et)
    seconds_since_close = max(0.0, (et - close_et).total_seconds())
    # Allowance for the venue's own last-print lag (a cash index prints its final
    # tick slightly before the bell, and providers settle a few minutes later).
    grace = max(live_ceiling_seconds, 3600.0)
    lateness = age_seconds - seconds_since_close
    usable = lateness <= grace
    return {"freshness": FRESH_CURRENT_FOR_SESSION if usable else FRESH_STALE,
            "venue": venue, "market_open": False, "usable": usable,
            "age_seconds": round(age_seconds, 1),
            "seconds_since_venue_close": round(seconds_since_close, 1),
            "lateness_vs_close_seconds": round(lateness, 1),
            "close_grace_seconds": grace,
            "venue_closed_at_et": close_et.isoformat(),
            "reason": ("market closed; this is the latest true print of the last session"
                       if usable else
                       "market closed AND the observation predates the last close by more "
                       "than the allowed grace — genuinely stale")}


def summarize(now: Optional[datetime] = None) -> Dict[str, Any]:
    """Human-readable session snapshot, for provenance blocks."""
    et = _now_et(now)
    return {
        "now_et": et.isoformat(),
        "weekday": et.weekday() < 5,
        "cash_equity_open": market_open(VENUE_CASH_EQUITY, now),
        "cash_index_open": market_open(VENUE_CASH_INDEX, now),
        "futures_open": market_open(VENUE_FUTURES, now),
        "holiday_calendar_modelled": False,
        "note": ("US market holidays are not modelled. On a holiday the cash venues look "
                 "open, so their inputs are flagged STALE rather than silently accepted. "
                 "That fails closed."),
    }
