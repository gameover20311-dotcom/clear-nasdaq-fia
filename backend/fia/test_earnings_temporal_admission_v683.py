"""V6.8.3 — point-in-time earnings admission regression.

An epsActual field is not itself proof that the value was available before a
forecast.  Directional earnings surprise is admitted only when the provider row
is strictly before the current America/New_York date.  Same-day/future actuals
remain catalyst risk, never a directional vote.
"""
from __future__ import annotations

import asyncio
import sys
from datetime import datetime as _RealDatetime, timezone
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from fia import providers as P  # noqa: E402
from fia.providers import ProviderHub  # noqa: E402

FAILURES = []


def check(name, cond, detail=""):
    if cond:
        print("  PASS  %s" % name)
    else:
        print("  FAIL  %s   %s" % (name, detail))
        FAILURES.append(name)


class FrozenDatetime(_RealDatetime):
    @classmethod
    def now(cls, tz=None):
        return _RealDatetime(2026, 9, 13, 16, 0, tzinfo=tz or timezone.utc)


async def run_case(events, *, raises=False):
    hub = ProviderHub()

    async def fake_get(url, params=None, timeout=15, **kwargs):
        if raises:
            raise RuntimeError("fixture provider failure")
        return {"earningsCalendar": list(events)}

    hub.get = fake_get
    data = {}
    real_datetime = P.datetime
    P.datetime = FrozenDatetime
    try:
        await hub._snapshot_earnings_calendar(data, "TEST-FINNHUB")
    finally:
        P.datetime = real_datetime
    return data


print("\n[A] PRIOR-DATE ACTUAL MAY VOTE; SAME-DAY/FUTURE ACTUALS MAY NOT")
rows = [
    {"symbol": "NVDA", "date": "2026-09-12", "epsActual": 2.0, "epsEstimate": 1.0},
    {"symbol": "AAPL", "date": "2026-09-13", "epsActual": 0.5, "epsEstimate": 1.0},
    {"symbol": "MSFT", "date": "2026-09-14", "epsActual": 3.0, "epsEstimate": 2.0},
    {"symbol": "AMD", "date": "not-a-date", "epsActual": 1.0, "epsEstimate": 2.0},
    {"symbol": "META", "date": "2026-09-15", "epsEstimate": 4.0},
    {"symbol": "UNTRACKED", "date": "2026-09-12", "epsActual": 99.0, "epsEstimate": 1.0},
]
data = asyncio.run(run_case(rows))
check("[A1] tracked events remain catalyst risk", data.get("earnings_catalyst_risk") is True)
check("[A2] exactly one prior-date surprise is counted", data.get("earnings_surprises_counted") == 1, str(data))
check("[A3] admitted prior-date surprise is bullish", data.get("earnings") == 1.0, str(data.get("earnings")))
check("[A4] status names prior-date verification",
      data.get("earnings_status") == "released_surprise_verified_by_prior_date", str(data.get("earnings_status")))
check("[A5] same-day/future/malformed dated actuals are rejected",
      data.get("earnings_temporal_rejected_count") == 3, str(data.get("earnings_temporal_rejected_count")))
check("[A6] untracked symbol is excluded", data.get("earnings_events") == 5, str(data.get("earnings_events")))
check("[A7] temporal rule is explicit", "same-day/future" in str(data.get("earnings_temporal_rule")))

print("\n[B] ONLY UNVERIFIED CURRENT/FUTURE ACTUALS => NO DIRECTIONAL VOTE")
rows2 = [
    {"symbol": "NVDA", "date": "2026-09-13", "epsActual": 2.0, "epsEstimate": 1.0},
    {"symbol": "AAPL", "date": "2026-09-14", "epsActual": 0.5, "epsEstimate": 1.0},
]
data2 = asyncio.run(run_case(rows2))
check("[B1] earnings vote is withheld", data2.get("earnings") is None, str(data2))
check("[B2] status is fail-closed",
      data2.get("earnings_status") == "upcoming_or_unverified_release_no_directional_vote",
      str(data2.get("earnings_status")))
check("[B3] catalyst risk remains visible", data2.get("earnings_catalyst_risk") is True)
check("[B4] zero directional surprises counted", data2.get("earnings_surprises_counted") == 0)
check("[B5] both actuals rejected temporally", data2.get("earnings_temporal_rejected_count") == 2)

print("\n[C] PROVIDER FAILURE FAILS CLOSED")
data3 = asyncio.run(run_case([], raises=True))
check("[C1] no directional vote on provider error", data3.get("earnings") is None)
check("[C2] calendar availability false", data3.get("earnings_calendar_available") is False)
check("[C3] status provider_error", data3.get("earnings_status") == "provider_error")
check("[C4] temporal rejected count resets honestly", data3.get("earnings_temporal_rejected_count") == 0)

print("\n" + "=" * 68)
if FAILURES:
    print("FAILED %d check(s):" % len(FAILURES))
    for failure in FAILURES:
        print("   -", failure)
    raise SystemExit(1)
print("EARNINGS TEMPORAL ADMISSION REGRESSION: PASS")
