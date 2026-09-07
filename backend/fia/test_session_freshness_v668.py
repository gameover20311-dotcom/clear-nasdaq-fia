"""V6.6.8 ONLINE: observation-freshness truth + US market holiday/session truth.

WHY THIS EXISTS
---------------
On 2026-09-07 (US Labor Day) the live deployment reported:

    market_quotes  age_seconds = 0.0   status = live
    candles        age_seconds = 0.0   status = live
    cash_equity_open = true

while QQQ, SPY, ^TNX and NQ=F each returned ZERO bars for the day and the quote
payload itself carried t = 2026-09-04T20:00:00Z (Friday's close, 68h earlier).

Two independent defects produced that:
  1. age_seconds measured the age of the HTTP REQUEST, not of the observation.
  2. No US holiday calendar existed, so a closed venue looked open.

Together they let three-day-old data satisfy the truth gate. Neither defect is a
forecasting question, and nothing here changes a weight, a threshold or a
calibration constant.
"""
from __future__ import annotations

import asyncio
import copy
import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from fia import market_sessions as ms                                # noqa: E402
from fia.market_sessions import (                                    # noqa: E402
    SESSION_CLOSED_HOLIDAY, SESSION_CLOSED_WEEKEND, SESSION_EARLY_CLOSE,
    SESSION_REGULAR, VENUE_CASH_EQUITY, VENUE_CASH_INDEX, VENUE_FUTURES,
    cash_session_phase, early_close_name, holiday_name, market_open,
    session_state, summarize, us_market_early_closes, us_market_holidays,
)
from fia.provider_reliability import enrich_provider_reliability     # noqa: E402

FAILURES = []


def check(name, cond, detail=""):
    if cond:
        print("  PASS  %s" % name)
    else:
        print("  FAIL  %s   %s" % (name, detail))
        FAILURES.append(name)


def et(y, m, d, hh=12, mm=0):
    return datetime(y, m, d, hh, mm, tzinfo=timezone.utc).astimezone(ms._ET)


def utc_at_et(y, m, d, hh, mm=0):
    """A UTC instant that lands at the requested ET wall-clock time."""
    naive = datetime(y, m, d, hh, mm)
    return naive.replace(tzinfo=ms._ET).astimezone(timezone.utc)


# --------------------------------------------------------------------------- #
print("\n[A] US MARKET HOLIDAY CALENDAR IS CORRECT")
h26 = us_market_holidays(2026)
expected_2026 = {
    date(2026, 1, 1): "New Year's Day",
    date(2026, 1, 19): "Martin Luther King Jr. Day",
    date(2026, 2, 16): "Washington's Birthday",
    date(2026, 4, 3): "Good Friday",
    date(2026, 5, 25): "Memorial Day",
    date(2026, 6, 19): "Juneteenth National Independence Day",
    date(2026, 7, 3): "Independence Day",          # Jul 4 is a Saturday -> Friday
    date(2026, 9, 7): "Labor Day",
    date(2026, 11, 26): "Thanksgiving Day",
    date(2026, 12, 25): "Christmas Day",
}
for d, name in expected_2026.items():
    check("2026 %s is %s" % (d, name), h26.get(d) == name, str(h26.get(d)))
check("2026 has exactly 10 full closures", len(h26) == 10, str(len(h26)))

# observance rules, both directions
check("Jul 4 on a Saturday is observed on the Friday",
      us_market_holidays(2026).get(date(2026, 7, 3)) == "Independence Day")
check("Jul 4 on a Sunday is observed on the Monday",
      us_market_holidays(2027).get(date(2027, 7, 5)) == "Independence Day",
      str(sorted(us_market_holidays(2027))))
check("Christmas on a Saturday is observed on the Friday",
      us_market_holidays(2027).get(date(2027, 12, 24)) == "Christmas Day")
# Good Friday moves with Easter
check("Good Friday 2025 = 2025-04-18", holiday_name(date(2025, 4, 18)) == "Good Friday")
check("Good Friday 2026 = 2026-04-03", holiday_name(date(2026, 4, 3)) == "Good Friday")
check("Good Friday 2027 = 2027-03-26", holiday_name(date(2027, 3, 26)) == "Good Friday")
check("a normal trading Tuesday is NOT a holiday", holiday_name(date(2026, 9, 8)) is None)

print("\n[B] EARLY CLOSES")
check("day after Thanksgiving 2026 is a half day",
      early_close_name(date(2026, 11, 27)) == "Day after Thanksgiving")
check("Christmas Eve 2026 is a half day",
      early_close_name(date(2026, 12, 24)) == "Christmas Eve")
check("an early close is never also a full closure",
      not (set(us_market_early_closes(2026)) & set(us_market_holidays(2026))))
check("13:30 ET on a half day is CLOSED",
      cash_session_phase(et(2026, 11, 27, 18, 30))["phase"] != SESSION_EARLY_CLOSE
      or not market_open(VENUE_CASH_EQUITY, utc_at_et(2026, 11, 27, 13, 30)),
      "half day must end at 13:00 ET")
check("11:00 ET on a half day is OPEN",
      market_open(VENUE_CASH_EQUITY, utc_at_et(2026, 11, 27, 11, 0)))

print("\n[C] SESSION PHASE ACROSS THE WEEK, HOLIDAYS AND DST")
cases = [
    ("normal weekday 11:00 ET (DST summer)", utc_at_et(2026, 9, 8, 11, 0), SESSION_REGULAR, True),
    ("normal weekday 08:00 ET pre-open",     utc_at_et(2026, 9, 8, 8, 0),  "CLOSED_OUTSIDE_HOURS", False),
    ("normal weekday 17:00 ET post-close",   utc_at_et(2026, 9, 8, 17, 0), "CLOSED_OUTSIDE_HOURS", False),
    ("Saturday",                              utc_at_et(2026, 9, 5, 12, 0), SESSION_CLOSED_WEEKEND, False),
    ("Sunday",                                utc_at_et(2026, 9, 6, 12, 0), SESSION_CLOSED_WEEKEND, False),
    ("LABOR DAY 2026-09-07 12:00 ET",         utc_at_et(2026, 9, 7, 12, 0), SESSION_CLOSED_HOLIDAY, False),
    ("Thanksgiving 2026",                     utc_at_et(2026, 11, 26, 12, 0), SESSION_CLOSED_HOLIDAY, False),
    ("winter weekday 11:00 ET (DST off)",     utc_at_et(2026, 1, 6, 11, 0), SESSION_REGULAR, True),
    ("MLK Day 2026 (winter holiday)",         utc_at_et(2026, 1, 19, 11, 0), SESSION_CLOSED_HOLIDAY, False),
]
for label, when, phase, is_open in cases:
    p = cash_session_phase(when.astimezone(ms._ET))
    check("[C] %-38s phase=%s" % (label, phase), p["phase"] == phase,
          "got %s" % p["phase"])
    check("[C] %-38s cash_open=%s" % (label, is_open),
          market_open(VENUE_CASH_EQUITY, when) is is_open,
          "got %s" % market_open(VENUE_CASH_EQUITY, when))

check("[C] futures are also closed on a full-day holiday",
      market_open(VENUE_FUTURES, utc_at_et(2026, 9, 7, 12, 0)) is False)
check("[C] futures are open on a normal weekday", 
      market_open(VENUE_FUTURES, utc_at_et(2026, 9, 8, 12, 0)) is True)

print("\n[D] LABOR DAY: FRIDAY'S CLOSE IS CURRENT_FOR_SESSION, NOT STALE")
LABOR = utc_at_et(2026, 9, 7, 12, 0)
# Friday 2026-09-04 16:00 ET close -> age at Monday noon ET
friday_close = utc_at_et(2026, 9, 4, 16, 0)
age = (LABOR - friday_close).total_seconds()
st = session_state("us10y", age, 21600.0, now=LABOR)
check("[D] us10y is admissible on the holiday", st["usable"] is True, json.dumps(st)[:200])
check("[D] labelled CURRENT_FOR_SESSION, not STALE",
      st["freshness"] == "CURRENT_FOR_SESSION", st["freshness"])
check("[D] the session phase names the holiday",
      st.get("session_phase") == SESSION_CLOSED_HOLIDAY and st.get("holiday") == "Labor Day",
      json.dumps({k: st.get(k) for k in ("session_phase", "holiday")}))
check("[D] market_open is False", st["market_open"] is False)

# ... but something older than the last real close is still genuinely stale
ancient = session_state("us10y", age + 8 * 86400, 21600.0, now=LABOR)
check("[D] an 8-day-old print is STILL STALE on a holiday",
      ancient["freshness"] == "STALE" and ancient["usable"] is False,
      json.dumps(ancient)[:180])

print("\n[E] DURING AN OPEN SESSION A LATE PRINT IS STILL STALE")
OPEN_TUE = utc_at_et(2026, 9, 8, 11, 0)
late = session_state("us10y", 5 * 3600, 21600.0, now=OPEN_TUE)
check("[E] within ceiling while open -> LIVE", late["freshness"] == "LIVE", late["freshness"])
very_late = session_state("us10y", 30 * 3600, 21600.0, now=OPEN_TUE)
check("[E] beyond ceiling while open -> STALE and excluded",
      very_late["freshness"] == "STALE" and very_late["usable"] is False)
check("[E] holiday closure is never an excuse during an open session",
      very_late["market_open"] is True)

print("\n[F] summarize() TELLS THE TRUTH")
sm = summarize(LABOR)
check("[F] holiday_calendar_modelled is now True", sm["holiday_calendar_modelled"] is True)
check("[F] cash venues reported closed", sm["cash_equity_open"] is False and sm["cash_index_open"] is False)
check("[F] the reason is named", sm["market_closed_reason"] == "Labor Day", str(sm["market_closed_reason"]))
check("[F] session_phase published", sm["session_phase"] == SESSION_CLOSED_HOLIDAY)

print("\n[G] FRESHNESS IS THE AGE OF THE OBSERVATION, NOT OF THE FETCH")


class _H:
    keys = {}


def health(d):
    return asyncio.run(enrich_provider_reliability(_H(), copy.deepcopy(d)))["source_health"]


now = datetime.now(timezone.utc)
base = {
    "provider_quotes_available": 17, "provider_quotes_requested": 17,
    "provider_candle_evidence": "available",
    "nq_structure_last_bar_end_utc": (now - timedelta(hours=66)).isoformat(),
    "quote_observed_at": (now - timedelta(hours=68)).isoformat(),
    "quote_observation_age_seconds": 68 * 3600.0,
    "quote_timestamp_quality": "PROVIDER_EXCHANGE_TIMESTAMP",
    "news_articles": 0, "news_scored_articles": 0, "news_status": "live_empty",
    "earnings_status": "no_tracked_events", "macro_status": "missing_event_calendar",
}
sh = health(base)
check("[G1] quote age is the exchange print age, NOT 0.0",
      abs((sh["market_quotes"]["age_seconds"] or 0) - 68 * 3600.0) < 1.0,
      str(sh["market_quotes"]["age_seconds"]))
check("[G2] candle age is the last completed bar age, NOT 0.0",
      65 * 3600 < (sh["candles"]["age_seconds"] or 0) < 67 * 3600,
      str(sh["candles"]["age_seconds"]))
check("[G3] quote observed_at is the exchange timestamp",
      sh["market_quotes"]["observed_at"] == base["quote_observed_at"])
check("[G4] candle observed_at is the bar end",
      sh["candles"]["observed_at"] == base["nq_structure_last_bar_end_utc"])
check("[G5] a 68h-old quote is NEVER labelled 'live'",
      sh["market_quotes"]["status"] != "live", str(sh["market_quotes"]["status"]))
check("[G6] a 66h-old candle set is NEVER labelled 'live'",
      sh["candles"]["status"] != "live", str(sh["candles"]["status"]))
check("[G7] the note publishes fetched_at AND observed_at",
      "fetched_at=" in sh["market_quotes"]["note"] and "observed_at=" in sh["market_quotes"]["note"])
check("[G8] timestamp quality is declared",
      "PROVIDER_EXCHANGE_TIMESTAMP" in sh["market_quotes"]["note"])

no_ts = dict(base, quote_observed_at=None, quote_observation_age_seconds=None,
             quote_timestamp_quality="NO_PROVIDER_TIMESTAMP_AVAILABLE")
sh2 = health(no_ts)
check("[G9] absent provider timestamp -> unknown age, never a fabricated 0.0",
      sh2["market_quotes"]["age_seconds"] is None
      and sh2["market_quotes"]["freshness"] == "unknown",
      json.dumps(sh2["market_quotes"])[:200])

fresh = dict(base,
             quote_observed_at=(now - timedelta(minutes=2)).isoformat(),
             quote_observation_age_seconds=120.0,
             nq_structure_last_bar_end_utc=(now - timedelta(minutes=20)).isoformat())
sh3 = health(fresh)
check("[G10] a genuinely fresh quote during RTH is still reported live-or-session",
      sh3["market_quotes"]["age_seconds"] == 120.0
      and sh3["market_quotes"]["status"] in ("live", "current_for_session"),
      json.dumps({k: sh3["market_quotes"][k] for k in ("age_seconds", "status")}))

print("\n[H] NO FUTURE LEAKAGE")
future = dict(base,
              quote_observed_at=(now + timedelta(hours=2)).isoformat(),
              quote_observation_age_seconds=-7200.0)
sh4 = health(future)
check("[H1] a future-dated quote is not reported as fresh-and-live",
      sh4["market_quotes"]["status"] != "live"
      or (sh4["market_quotes"]["age_seconds"] or 0) < 0,
      json.dumps({k: sh4["market_quotes"][k] for k in ("age_seconds", "status")}))
check("[H2] the negative age is preserved rather than clamped to look fresh",
      sh4["market_quotes"]["age_seconds"] == -7200.0)

print("\n[I] NOTHING PREDICTIVE MOVED")
from fia.premove_watch import (                                      # noqa: E402
    HORIZON_WEIGHTS, MAX_AGE_SECONDS_BY_SOURCE, MIN_CONFIDENCE_FOR_DIRECTION,
    MIN_EDGE_POINTS,
)
check("[I1] conviction thresholds unchanged",
      MIN_EDGE_POINTS == 2.0 and MIN_CONFIDENCE_FOR_DIRECTION == 5.0)
check("[I2] news ceiling unchanged (12h)", MAX_AGE_SECONDS_BY_SOURCE["news"] == 43200.0)
check("[I3] quote ceiling unchanged (30m)", MAX_AGE_SECONDS_BY_SOURCE["market_quotes"] == 1800.0)
check("[I4] candle ceiling unchanged (90m)", MAX_AGE_SECONDS_BY_SOURCE["candles"] == 5400.0)
check("[I5] 4H and 8H weight sets still differ (horizons not blended)",
      HORIZON_WEIGHTS["4h"] != HORIZON_WEIGHTS["8h"])

print("\n" + "=" * 68)
if FAILURES:
    print("FAILED %d check(s):" % len(FAILURES))
    for f in FAILURES:
        print("   -", f)
    sys.exit(1)
print("ALL V6.6.8 SESSION / FRESHNESS TRUTH CHECKS PASSED")
