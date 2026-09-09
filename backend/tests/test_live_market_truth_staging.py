import asyncio
import time
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fia.live_market_truth import (
    _completed_structure_from_candles,
    _direct_nq_structure,
    _direct_spx_confirmation,
    _earnings_primary_truth,
    _macro_calendar,
    _macro_type,
)


class FakeHub:
    def __init__(self):
        self.keys = {"FINNHUB_API_KEY": "test", "POLYGON_API_KEY": "test"}
        self.macro_payload = None

    @staticmethod
    def normalize_change(value):
        if value is None:
            return None
        return max(-1.0, min(1.0, float(value) / 2.0))

    async def polygon_futures_candles(self, ticker, multiplier=1, timespan="hour", start_ts=None, end_ts=None):
        now = int(time.time())
        # 12 completed bars plus one still-forming bar. The forming value is an
        # extreme outlier so the test fails loudly if it leaks into structure.
        stamps = [now - (13 - i) * 3600 for i in range(12)] + [now - 1200]
        closes = [100.0 + i for i in range(12)] + [1000.0]
        return {
            "s": "ok",
            "t": stamps,
            "c": closes,
            "h": closes,
            "l": closes,
            "v": [1.0] * len(closes),
            "ticker": ticker,
        }

    async def get(self, url, params=None, timeout=15, headers=None):
        if "calendar/economic" in url:
            return self.macro_payload
        if "calendar/earnings" in url:
            return {"earningsCalendar": []}
        return None


class LiveMarketTruthTests(unittest.TestCase):
    def test_completed_structure_rejects_forming_bar(self):
        now = int(time.time())
        completed_t = [now - (13 - i) * 3600 for i in range(12)]
        completed_c = [100.0 + i for i in range(12)]

        clean = _completed_structure_from_candles(
            {"t": completed_t, "c": completed_c}, 3600
        )
        contaminated = _completed_structure_from_candles(
            {
                "t": completed_t + [now - 1200],
                "c": completed_c + [9999.0],
            },
            3600,
        )
        self.assertIsNotNone(clean)
        self.assertIsNotNone(contaminated)
        self.assertEqual(contaminated["completed_bars"], 12)
        # The output must be byte-for-byte equivalent on all derived fields when
        # the only added observation is a still-forming bar.
        self.assertEqual(contaminated, clean)
        self.assertLessEqual(
            int(__import__("datetime").datetime.fromisoformat(
                contaminated["last_completed_bar_end_utc"]
            ).timestamp()),
            now,
        )

    def test_direct_nq_requires_explicit_contract(self):
        hub = FakeHub()
        missing = asyncio.run(_direct_nq_structure(hub, {
            "nq_liquidity": {"symbol": "NQ=F", "source_quality": "CONTINUOUS_FALLBACK"}
        }))
        self.assertEqual(missing["nq_truth_status"], "DIRECT_EXPLICIT_CONTRACT_UNAVAILABLE")

        direct = asyncio.run(_direct_nq_structure(hub, {
            "nq_liquidity": {"symbol": "NQU6", "source_quality": "EXPLICIT_CONTRACT"}
        }))
        self.assertEqual(direct["nq_truth_status"], "DIRECT_EXPLICIT_CONTRACT")
        self.assertEqual(direct["nq_structure_contract"], "NQU6")
        self.assertFalse(direct["nq_structure_is_proxy"])
        self.assertIn("NQU6", direct["nq_structure_basis"])

    def test_direct_spx_accepts_only_fresh_index(self):
        hub = FakeHub()
        fresh = SimpleNamespace(
            value=6800.0,
            change_percent=0.4,
            age_seconds=120.0,
            observed_at="2026-09-09T17:00:00+00:00",
        )
        with patch("fia.provider_reliability.yahoo_observation", new=AsyncMock(return_value=fresh)):
            out = asyncio.run(_direct_spx_confirmation(hub))
        self.assertEqual(out["spx_truth_status"], "DIRECT_SPX_INDEX")
        self.assertFalse(out["spx_confirmation_is_proxy"])
        self.assertAlmostEqual(out["spx_confirmation"], 0.2)

        stale = SimpleNamespace(
            value=6800.0,
            change_percent=0.4,
            age_seconds=3600.0,
            observed_at="2026-09-09T16:00:00+00:00",
        )
        with patch("fia.provider_reliability.yahoo_observation", new=AsyncMock(return_value=stale)):
            out = asyncio.run(_direct_spx_confirmation(hub))
        self.assertEqual(out["spx_truth_status"], "DIRECT_SPX_STALE")
        self.assertNotIn("spx_confirmation", out)

    def test_macro_type_mapping_is_narrow(self):
        self.assertEqual(_macro_type("Consumer Price Index CPI"), "CPI")
        self.assertEqual(_macro_type("Core PCE Price Index"), "CORE_PCE")
        self.assertEqual(_macro_type("Nonfarm Payrolls"), "NFP")
        self.assertIsNone(_macro_type("Random market commentary"))

    def test_macro_calendar_scores_only_actual_vs_consensus(self):
        hub = FakeHub()
        now = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
        hub.macro_payload = {
            "economicCalendar": [{
                "country": "US",
                "event": "Consumer Price Index CPI",
                "actual": 3.2,
                "estimate": 3.0,
                "prev": 3.1,
                "time": (now - __import__("datetime").timedelta(minutes=30)).isoformat(),
                "unit": "%",
            }]
        }
        out = asyncio.run(_macro_calendar(hub))
        self.assertTrue(out["macro_calendar_available"])
        self.assertEqual(out["macro_status"], "released_surprise")
        self.assertIsNotNone(out["macro"])
        self.assertLess(out["macro"], 0.0)  # hotter CPI maps bearish for NQ

        hub.macro_payload = {
            "economicCalendar": [{
                "country": "US",
                "event": "Consumer Price Index CPI",
                "actual": None,
                "estimate": 3.0,
                "time": (now + __import__("datetime").timedelta(hours=3)).isoformat(),
            }]
        }
        out = asyncio.run(_macro_calendar(hub))
        self.assertTrue(out["macro_calendar_available"])
        self.assertIsNone(out["macro"])
        # The official fallback intentionally replaces the vendor-only status
        # while still refusing to fabricate a neutral/directional score.
        self.assertEqual(out["macro_status"], "official_calendar_live_no_point_in_time_consensus")
        self.assertIn("macro_official_calendar", out)
        self.assertFalse(out["macro_official_calendar"]["consensus_available"])

    def test_no_earnings_event_is_not_provider_failure(self):
        hub = FakeHub()
        out = asyncio.run(_earnings_primary_truth(hub, {
            "earnings_calendar_available": True,
            "earnings_events": 0,
        }))
        self.assertEqual(out["earnings_primary_evidence_status"], "NO_RELEVANT_EVENT")
        self.assertEqual(out["guidance_primary_evidence_status"], "NO_RELEVANT_EVENT")


if __name__ == "__main__":
    unittest.main()
