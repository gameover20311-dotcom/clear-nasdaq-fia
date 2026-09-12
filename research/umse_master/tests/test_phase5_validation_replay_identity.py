from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from umse_master.adapters import AdapterDeclaration, Capability
from umse_master.contracts import DataClass, QualityState
from umse_master.events import EventType, MarketEvent
from umse_master.replay import CausalReplay, ReplayClass
from umse_master.research_identity import fingerprints, unclassified_files
from umse_master.validation import evaluate_paired_candidate

UTC = timezone.utc
T = datetime(2026, 9, 12, 15, 0, tzinfo=UTC)


class ValidationReplayIdentityTests(unittest.TestCase):
    def event(self, idx, minutes):
        return MarketEvent(
            EventType.BUY_AGGRESSION, T + timedelta(minutes=minutes), T + timedelta(minutes=minutes),
            T + timedelta(minutes=minutes, seconds=1), "test", "NQ", DataClass.REAL_TRADES_QUOTES,
            QualityState.FRESH, f"e{idx}", 20000, 1
        )

    def test_candidate_beats_uniform_at_fixed_n(self):
        outcomes = ["bullish"] * 10
        base = [{"bullish": 1/3, "bearish": 1/3, "neutral": 1/3}] * 10
        cand = [{"bullish": .9, "bearish": .05, "neutral": .05}] * 10
        r = evaluate_paired_candidate(base, cand, outcomes, expected_n=10)
        self.assertTrue(r.confirmatory_eligible)
        self.assertGreater(r.mean_delta, .01)
        self.assertTrue(r.promotion_gate_pass)

    def test_diagnostic_without_fixed_n_cannot_promote(self):
        outcomes = ["bullish"] * 3
        p = [{"bullish": .8, "bearish": .1, "neutral": .1}] * 3
        r = evaluate_paired_candidate(p, p, outcomes)
        self.assertFalse(r.confirmatory_eligible)
        self.assertFalse(r.promotion_gate_pass)

    def test_historical_replay_is_not_prospective(self):
        replay = CausalReplay([self.event(1, -1), self.event(2, 1)])
        row = next(replay.decisions([T], replay_class=ReplayClass.UNTOUCHED_HISTORICAL_TEST))
        self.assertFalse(row.prospective_proof)
        self.assertEqual(len(row.events), 1)

    def test_mbo_capability_cannot_be_claimed_by_l2(self):
        with self.assertRaises(ValueError):
            AdapterDeclaration("bad", DataClass.REAL_L2_DEPTH, (Capability.MBO, Capability.L2))

    def test_research_identity_is_complete_and_deterministic(self):
        self.assertEqual(unclassified_files(), ())
        a = fingerprints()
        b = fingerprints()
        self.assertEqual(a, b)
        for key in ("model", "protocol", "infrastructure"):
            self.assertEqual(len(a[key]["digest"]), 64)
            self.assertGreater(a[key]["file_count"], 0)


if __name__ == "__main__":
    unittest.main()
