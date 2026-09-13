# PHASE23_DATA_RELIABILITY_V1
# PHASE22_TRUTH_CONSISTENCY_V1
import yfinance as yf
import os
import time
import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional
from zoneinfo import ZoneInfo

import httpx
from dotenv import load_dotenv

load_dotenv()

"""CLEAR NASDAQ — ProviderHub facade over the three-way split.

WHY THE FACADE EXISTS
providers.py was 6427 lines mixing three identities: code that can change the
forecast (MODEL), code that decides what counts as evidence (PROTOCOL), and
transport (INFRASTRUCTURE). The split map recorded that mixture; this is it
applied. Callers are unaffected: `from fia.providers import ProviderHub` and
every method on it behave exactly as before, because the methods were MOVED,
not rewritten, and ProviderHub still composes all of them.

The MRO order below is deliberate and the three mixins share no method names,
so composition cannot silently shadow anything.

A narrow protocol override exists for earnings temporal admission.  The provider
calendar can contain epsActual on a future or same-day row without proving when
that value became available.  Such a row must not become released evidence.
"""

from .providers_model import ModelMixin
from .providers_protocol import ProtocolMixin
from .providers_infrastructure import InfrastructureMixin


class ProviderHub(ModelMixin, ProtocolMixin, InfrastructureMixin):
    """Central provider layer for CLEAR NASDAQ FIA."""

    NY_TZ = ZoneInfo("America/New_York")
    UTC = timezone.utc

    SNAPSHOT_CACHE_SECONDS = 8

    async def _snapshot_earnings_calendar(self, data, finnhub_key):
        """Fail-closed temporal admission for earnings surprise evidence.

        Finnhub's earnings calendar exposes a calendar date and may expose an
        actual value, but an actual value by itself is not an availability
        timestamp.  We therefore count directional surprise only for a tracked
        event whose calendar date is strictly before the current New-York date.
        Same-day and future rows remain catalyst risk only.  This is deliberately
        conservative; verified intraday/SEC availability can be admitted by a
        separate point-in-time evidence path later.
        """
        try:
            now_ny = datetime.now(timezone.utc).astimezone(self.NY_TZ)
            start_date = (now_ny.date() - timedelta(days=1)).isoformat()
            end_date = (now_ny.date() + timedelta(days=7)).isoformat()
            earnings = await self.get(
                "https://finnhub.io/api/v1/calendar/earnings",
                {"from": start_date, "to": end_date, "token": finnhub_key},
                timeout=15,
            )
            events = (earnings or {}).get("earningsCalendar", [])
            tracked = {
                "NVDA", "MSFT", "AAPL", "AMZN", "META", "AVGO", "GOOGL",
                "GOOG", "TSLA", "NFLX", "AMD", "MU", "INTC", "QCOM", "SMCI",
            }
            tracked_events = [event for event in events if event.get("symbol") in tracked]

            positive = negative = counted = temporal_rejected = 0
            for event in tracked_events:
                actual = event.get("epsActual")
                estimate = event.get("epsEstimate")
                if actual is None or estimate is None:
                    continue
                try:
                    event_date = datetime.strptime(str(event.get("date") or ""), "%Y-%m-%d").date()
                except (TypeError, ValueError):
                    # An actual without a parseable release/calendar date has no
                    # trustworthy point-in-time meaning.
                    temporal_rejected += 1
                    continue
                if event_date >= now_ny.date():
                    temporal_rejected += 1
                    continue
                try:
                    actual_f = float(actual)
                    estimate_f = float(estimate)
                except (TypeError, ValueError):
                    continue
                if actual_f > estimate_f:
                    positive += 1
                    counted += 1
                elif actual_f < estimate_f:
                    negative += 1
                    counted += 1

            data["earnings_calendar_available"] = True
            data["earnings_catalyst_risk"] = bool(tracked_events)
            if counted:
                data["earnings"] = max(-1.0, min(1.0, (positive - negative) / counted))
                data["earnings_status"] = "released_surprise_verified_by_prior_date"
            elif tracked_events:
                data["earnings"] = None
                data["earnings_status"] = "upcoming_or_unverified_release_no_directional_vote"
            else:
                data["earnings"] = None
                data["earnings_status"] = "no_tracked_events"

            data["earnings_events"] = len(tracked_events)
            data["earnings_surprises_counted"] = counted
            data["earnings_temporal_rejected_count"] = temporal_rejected
            data["earnings_positive"] = positive
            data["earnings_negative"] = negative
            data["earnings_temporal_rule"] = (
                "epsActual is directional only when event date is before current America/New_York date; "
                "same-day/future actuals are catalyst-only without verified availability timestamp"
            )
        except Exception as exc:
            data["earnings"] = None
            data["earnings_calendar_available"] = False
            data["earnings_status"] = "provider_error"
            data["earnings_catalyst_risk"] = False
            data["earnings_temporal_rejected_count"] = 0
            print("Earnings intelligence error -> %s" % exc)
