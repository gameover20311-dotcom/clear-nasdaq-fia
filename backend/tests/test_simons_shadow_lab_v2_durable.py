import unittest
from datetime import datetime, timezone

from simons_shadow_lab_v1.durable_reader import contract_filter_rows, events_as_of, rows_from_events
from simons_shadow_lab_v1.lab import GENESIS, canonical_bytes, sha256_bytes


def _event(seq, event_type, fid, created, prev, payload):
    unsigned = {
        "schema_version": "TEST",
        "seq": seq,
        "event_type": event_type,
        "forecast_id": fid,
        "created_at_utc": created,
        "prev_event_hash": prev,
        "payload": payload,
    }
    return {**unsigned, "event_hash": sha256_bytes(canonical_bytes(unsigned))}


def _lock(seq=1, fid="F1", created="2026-09-10T13:00:00+00:00", prev=GENESIS, include_h8=True):
    hp = {
        "4h": {"bullish_probability": 60.0, "bearish_probability": 40.0, "direction": "BULLISH", "confidence": 50.0},
    }
    if include_h8:
        hp["8h"] = {"bullish_probability": 58.0, "bearish_probability": 42.0, "direction": "BULLISH", "confidence": 48.0}
    payload = {
        "locked_at_utc": created,
        "models": {
            "BASE_FIA": {
                "direction": "BULLISH",
                "confidence": 50.0,
                "regime": "TREND",
                "data_coverage": 0.9,
                "intelligence_coverage": 0.8,
                "horizon_probabilities": hp,
                "signals": [],
                "source_status": {},
            }
        },
    }
    return _event(seq, "FORECAST_LOCK", fid, created, prev, payload)


class ShadowLabV2DurableTests(unittest.TestCase):
    def test_as_of_snapshot_excludes_future_resolution(self):
        lock = _lock()
        resolution = _event(
            2,
            "RESOLUTION_4H",
            "F1",
            "2026-09-10T17:05:00+00:00",
            lock["event_hash"],
            {
                "resolved_at_utc": "2026-09-10T17:00:00+00:00",
                "actual_direction": "BULLISH",
                "entry_price": 100.0,
                "outcome_price": 101.0,
            },
        )
        kept, audit = events_as_of(
            [lock, resolution],
            datetime(2026, 9, 10, 15, 0, tzinfo=timezone.utc),
        )
        self.assertEqual(len(kept), 1)
        self.assertEqual(audit["future_events_excluded"], 1)
        rows = rows_from_events(kept)
        self.assertEqual(rows[0]["outcomes"], {})

    def test_as_of_timestamp_regression_fails_closed(self):
        lock = _lock(created="2026-09-10T13:00:00+00:00")
        later_seq_earlier_time = _event(
            2, "RESOLUTION_4H", "F1", "2026-09-10T12:00:00+00:00", lock["event_hash"],
            {"resolved_at_utc": "2026-09-10T12:00:00+00:00", "actual_direction": "BULLISH"},
        )
        with self.assertRaises(RuntimeError):
            events_as_of([lock, later_seq_earlier_time], datetime(2026, 9, 11, tzinfo=timezone.utc))

    def test_contract_filter_keeps_real_two_way_row(self):
        rows = rows_from_events([_lock()])
        eligible, excluded = contract_filter_rows(rows)
        self.assertEqual(len(eligible), 1)
        self.assertEqual(excluded, [])

    def test_contract_filter_records_missing_horizon_instead_of_imputing(self):
        rows = rows_from_events([_lock(include_h8=False)])
        eligible, excluded = contract_filter_rows(rows)
        self.assertEqual(eligible, [])
        self.assertEqual(len(excluded), 1)
        self.assertEqual(excluded[0]["reason"], "LOCK_TIME_CONTRACT_FAIL_CLOSED")
        self.assertFalse(excluded[0]["contract_audit"]["h8"]["ok"])


if __name__ == "__main__":
    unittest.main()
