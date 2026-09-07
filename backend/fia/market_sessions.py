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
* Holidays ARE modelled (V6.6.8). Before this, a holiday looked like an open day,
  so every cash input was judged against the intraday live ceiling and flagged
  STALE. That failed closed, but it also mislabelled a correct last print as
  degraded data and it let a stale-but-fetched-now quote read as LIVE. Verified
  on 2026-09-07 (Labor Day): QQQ, SPY, ^TNX and NQ=F each returned ZERO bars for
  the day, yet the session layer reported cash_equity_open=true.
* Early closes are modelled as a 13:00 ET close.
* No non-US holiday calendar, and no exchange-specific ad-hoc closure (weather,
  national mourning). Those still fail closed as STALE.
* No fabricated value is ever produced for a closed market.
"""
from __future__ import annotations

from calendar import monthrange
from datetime import date, datetime, time, timedelta, timezone
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


# --------------------------------------------------------------- US holidays
# NYSE/Nasdaq full-day closures. Rule-derived rather than hardcoded per year, so
# the calendar does not silently expire. Observance: a Saturday holiday is taken
# on the preceding Friday, a Sunday holiday on the following Monday.
SESSION_REGULAR = "REGULAR"
SESSION_EARLY_CLOSE = "EARLY_CLOSE"
SESSION_CLOSED_WEEKEND = "CLOSED_WEEKEND"
SESSION_CLOSED_HOLIDAY = "CLOSED_HOLIDAY"
SESSION_CLOSED_OUTSIDE_HOURS = "CLOSED_OUTSIDE_HOURS"

EARLY_CLOSE_HOUR = 13  # 13:00 ET on a half day


def _nth_weekday(year: int, month: int, weekday: int, n: int) -> date:
    """n-th (1-based) `weekday` of a month; n=-1 means the last one."""
    if n > 0:
        d = date(year, month, 1)
        d += timedelta(days=(weekday - d.weekday()) % 7)
        return d + timedelta(weeks=n - 1)
    d = date(year, month, monthrange(year, month)[1])
    d -= timedelta(days=(d.weekday() - weekday) % 7)
    return d


def _easter(year: int) -> date:
    """Anonymous Gregorian algorithm. Good Friday is Easter minus two days."""
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month, day = divmod(h + l - 7 * m + 114, 31)
    return date(year, month, day + 1)


def _observed(d: date) -> date:
    if d.weekday() == 5:          # Saturday -> Friday
        return d - timedelta(days=1)
    if d.weekday() == 6:          # Sunday -> Monday
        return d + timedelta(days=1)
    return d


def us_market_holidays(year: int) -> Dict[date, str]:
    """Full-day NYSE/Nasdaq closures for `year`."""
    h: Dict[date, str] = {}
    h[_observed(date(year, 1, 1))] = "New Year's Day"
    h[_nth_weekday(year, 1, 0, 3)] = "Martin Luther King Jr. Day"
    h[_nth_weekday(year, 2, 0, 3)] = "Washington's Birthday"
    h[_easter(year) - timedelta(days=2)] = "Good Friday"
    h[_nth_weekday(year, 5, 0, -1)] = "Memorial Day"
    if year >= 2022:
        h[_observed(date(year, 6, 19))] = "Juneteenth National Independence Day"
    h[_observed(date(year, 7, 4))] = "Independence Day"
    h[_nth_weekday(year, 9, 0, 1)] = "Labor Day"
    h[_nth_weekday(year, 11, 3, 4)] = "Thanksgiving Day"
    h[_observed(date(year, 12, 25))] = "Christmas Day"
    return h


def us_market_early_closes(year: int) -> Dict[date, str]:
    """Scheduled 13:00 ET half days."""
    e: Dict[date, str] = {}
    e[_nth_weekday(year, 11, 3, 4) + timedelta(days=1)] = "Day after Thanksgiving"
    jul3 = date(year, 7, 3)
    if jul3.weekday() < 5 and _observed(date(year, 7, 4)) == date(year, 7, 4):
        e[jul3] = "Independence Day eve"
    dec24 = date(year, 12, 24)
    if dec24.weekday() < 5:
        e[dec24] = "Christmas Eve"
    return {d: n for d, n in e.items() if d not in us_market_holidays(year)}


def holiday_name(d: date) -> Optional[str]:
    return us_market_holidays(d.year).get(d)


def early_close_name(d: date) -> Optional[str]:
    return us_market_early_closes(d.year).get(d)


def _cash_close_hour(d: date) -> int:
    return EARLY_CLOSE_HOUR if early_close_name(d) else 16


def cash_session_phase(now_et: datetime) -> Dict[str, Any]:
    """What phase the US cash session is in, holidays included."""
    d, t = now_et.date(), now_et.time()
    if d.weekday() >= 5:
        return {"phase": SESSION_CLOSED_WEEKEND, "holiday": None, "early_close": None}
    hol = holiday_name(d)
    if hol:
        return {"phase": SESSION_CLOSED_HOLIDAY, "holiday": hol, "early_close": None}
    early = early_close_name(d)
    close_h = EARLY_CLOSE_HOUR if early else 16
    if time(9, 30) <= t < time(close_h, 0):
        return {"phase": SESSION_EARLY_CLOSE if early else SESSION_REGULAR,
                "holiday": None, "early_close": early}
    return {"phase": SESSION_CLOSED_OUTSIDE_HOURS, "holiday": None, "early_close": early}


def _now_et(now: Optional[datetime] = None) -> datetime:
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    return now.astimezone(_ET)


def _last_cash_close(now_et: datetime) -> datetime:
    """Most recent cash close at or before `now_et`.

    V6.6.8: skips weekends AND full-day holidays, and uses 13:00 ET on a
    scheduled half day. Previously a holiday counted as a normal trading day, so
    the reference close was a session that never happened and the last real print
    was measured as hours late.
    """
    probe = now_et
    for _ in range(12):
        d = probe.date()
        if d.weekday() < 5 and not holiday_name(d):
            close = probe.replace(hour=_cash_close_hour(d), minute=0,
                                  second=0, microsecond=0)
            if now_et >= close:
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
    if holiday_name(now_et.date()):
        # Closed for the holiday: reference the previous real session close.
        probe = now_et - timedelta(days=1)
        for _ in range(8):
            d = probe.date()
            if d.weekday() < 5 and not holiday_name(d):
                return probe.replace(hour=17, minute=0, second=0, microsecond=0)
            probe -= timedelta(days=1)
    return now_et                                 # open


def market_open(venue: str, now: Optional[datetime] = None) -> bool:
    et = _now_et(now)
    wd, t = et.weekday(), et.time()
    if venue == VENUE_CONTINUOUS:
        return True
    if venue in (VENUE_CASH_EQUITY, VENUE_CASH_INDEX):
        # V6.6.8: a holiday is a closed day, not an open day with missing prints.
        return cash_session_phase(et)["phase"] in (SESSION_REGULAR, SESSION_EARLY_CLOSE)
    if venue == VENUE_FUTURES:
        if wd == 5:
            return False
        if wd == 6:
            return t >= time(18, 0)
        if wd == 4:
            return t < time(17, 0)
        # Equity-index futures observe the full-day US holidays too (Globex runs a
        # shortened session; treating the day as closed is the truthful direction
        # and matches the observed zero-bar behaviour).
        if holiday_name(et.date()):
            return False
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
        _ph = cash_session_phase(et)
        return {"freshness": FRESH_LIVE if usable else FRESH_STALE,
                "venue": venue, "market_open": is_open, "usable": usable,
                "session_phase": _ph["phase"], "holiday": _ph["holiday"],
                "early_close": _ph["early_close"],
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
    _ph = cash_session_phase(et)
    return {"freshness": FRESH_CURRENT_FOR_SESSION if usable else FRESH_STALE,
            "venue": venue, "market_open": False, "usable": usable,
            "session_phase": _ph["phase"], "holiday": _ph["holiday"],
            "early_close": _ph["early_close"],
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
    phase = cash_session_phase(et)
    return {
        "now_et": et.isoformat(),
        "weekday": et.weekday() < 5,
        "cash_equity_open": market_open(VENUE_CASH_EQUITY, now),
        "cash_index_open": market_open(VENUE_CASH_INDEX, now),
        "futures_open": market_open(VENUE_FUTURES, now),
        "session_phase": phase["phase"],
        "holiday": phase["holiday"],
        "early_close": phase["early_close"],
        "market_closed_reason": (
            phase["holiday"] if phase["phase"] == SESSION_CLOSED_HOLIDAY
            else "weekend" if phase["phase"] == SESSION_CLOSED_WEEKEND
            else "outside regular hours" if phase["phase"] == SESSION_CLOSED_OUTSIDE_HOURS
            else None),
        "holiday_calendar_modelled": True,
        "note": ("US full-day market holidays and scheduled 13:00 ET early closes are "
                 "modelled. A closed venue's last print is CURRENT_FOR_SESSION, not "
                 "stale, and is never presented as current intraday evidence. "
                 "Non-US holidays and unscheduled closures are not modelled and still "
                 "fail closed as STALE."),
    }
