import tempfile
import unittest
from pathlib import Path

from simons_shadow_lab_v1.causal_features import extract_lock_time_features
from simons_shadow_lab_v1.negative_controls import (
    lock_time_feature_invariance,
    resolved_counts,
    run_negative_control_harness,
    scramble_outcome_directions,
)
from simons_shadow_lab_v1.sequential_testing import (
    AlphaSpendingPlan,
    SequentialAlphaLedger,
    alpha_schedule,
    evaluate_look,
)


def _row(i: int, actual: str = "BULLISH", bull: float = 60.0):
    return {
        "forecast_id": f"CTRL-{i}",
        "lock_event_hash": f"lock-{i}",
        "locked_at_utc": f"2026-09-{(i % 20) + 1:02d}T13:00:00+00:00",
        "campaign": "TEST",
        "base": {
            "direction": "BULLISH" if bull >= 50 else "BEARISH",
            "confidence": 55.0,
            "regime": "TREND" if i % 2 == 0 else "TRANSITION",
            "status": "LIVE",
            "data_coverage": 0.9,
            "intelligence_coverage": 0.8,
            "h4": {
                "bullish_probability": bull,
                "bearish_probability": 100.0 - bull,
                "direction": "BULLISH" if bull >= 50 else "BEARISH",
                "confidence": 55.0,
                "state": "WATCH",
                "actionable": True,
            },
            "h8": {
                "bullish_probability": bull,
                "bearish_probability": 100.0 - bull,
                "direction": "BULLISH" if bull >= 50 else "BEARISH",
                "confidence": 50.0,
                "state": "WATCH",
                "actionable": True,
            },
            "signals": [
                {"name": "NQ structure", "score": 0.2, "freshness": "LIVE"},
                {"name": "DXY", "score": -0.1, "freshness": "LIVE"},
                {"name": "US10Y", "score": -0.1, "freshness": "LIVE"},
            ],
            "source_status": {"macro": "FRED | live", "dxy": "Yahoo | live"},
        },
        "outcomes": {
            "4h": {"actual_direction": actual, "entry_price": 100.0, "outcome_price": 101.0},
            "8h": {"actual_direction": actual, "entry_price": 100.0, "outcome_price": 101.0},
        },
    }


class ShadowLabV2ControlsTests(unittest.TestCase):
    def test_alpha_schedule_spends_no_more_than_allocated_family_budget(self):
        plan = AlphaSpendingPlan(
            "H1", [0.25, 0.50, 0.75, 1.0], family_alpha=0.05, family_size=5
        )
        out = alpha_schedule(plan)
        self.assertAlmostEqual(out["hypothesis_alpha_bound"], 0.01, places=12)
        self.assertLessEqual(out["total_local_alpha"], 0.01 + 1e-12)
        self.assertAlmostEqual(out["looks"][-1]["cumulative_alpha_spent"], 0.01, places=12)
        self.assertLess(out["looks"][0]["cumulative_alpha_spent"], out["looks"][-1]["cumulative_alpha_spent"])
        self.assertFalse(out["exact_lan_demets_boundary_claimed"])

    def test_alpha_plan_rejects_unregistered_or_nonfinal_information_schedule(self):
        with self.assertRaises(ValueError):
            AlphaSpendingPlan("H1", [0.5, 0.4, 1.0]).normalized()
        with self.assertRaises(ValueError):
            AlphaSpendingPlan("H1", [0.25, 0.5]).normalized()

    def test_sequential_look_uses_incremental_not_full_alpha(self):
        plan = AlphaSpendingPlan("H1", [0.25, 0.50, 1.0], family_alpha=0.05)
        schedule = alpha_schedule(plan)
        local = schedule["looks"][0]["local_alpha_for_ordinary_p_value"]
        self.assertLess(local, 0.05)
        result = evaluate_look(plan, 1, min(1.0, local * 1.1))
        self.assertFalse(result["threshold_met"])
        self.assertFalse(result["predictive_edge_proven"])

    def test_sequential_ledger_is_frozen_ordered_and_stops_after_crossing(self):
        with tempfile.TemporaryDirectory() as td:
            plan = AlphaSpendingPlan("H1", [0.5, 1.0], family_alpha=0.05)
            ledger = SequentialAlphaLedger(Path(td), "H1")
            ledger.freeze_plan(plan)
            with self.assertRaises(FileExistsError):
                ledger.freeze_plan(plan)
            with self.assertRaises(ValueError):
                ledger.append_look(2, 0.5, 20)
            schedule = alpha_schedule(plan)
            threshold = schedule["looks"][0]["local_alpha_for_ordinary_p_value"]
            event = ledger.append_look(1, threshold / 2.0, 20)
            self.assertTrue(event["payload"]["threshold_met"])
            self.assertFalse(event["payload"]["predictive_edge_proven"])
            with self.assertRaises(RuntimeError):
                ledger.append_look(2, 0.5, 40)

    def test_scrambled_labels_preserve_marginals_and_lock_time_features(self):
        rows = [_row(i, "BULLISH" if i < 12 else "BEARISH") for i in range(20)]
        before_counts = resolved_counts(rows)
        before_features = [extract_lock_time_features(r, 4) for r in rows]
        scrambled = scramble_outcome_directions(rows, seed=123)
        self.assertEqual(before_counts, resolved_counts(scrambled))
        self.assertEqual(before_features, [extract_lock_time_features(r, 4) for r in scrambled])
        self.assertTrue(lock_time_feature_invariance(rows, scrambled)["ok"])

    def test_negative_control_fails_closed_when_real_resolutions_are_insufficient(self):
        result = run_negative_control_harness([_row(1)], trials=100, min_n=12)
        self.assertEqual(result["status"], "INSUFFICIENT_REAL_RESOLUTIONS")
        self.assertFalse(result["negative_control_pass"])
        self.assertEqual(result["trials_run"], 0)
        self.assertFalse(result["predictive_edge_proven"])

    def test_negative_control_detects_pipeline_that_always_finds_fake_edge(self):
        rows = [_row(i, "BULLISH" if i % 2 == 0 else "BEARISH") for i in range(20)]

        def broken_search(*args, **kwargs):
            return {"results": [{
                "robust_discovery_screen": True,
                "search_wide_permutation_p_value": 0.001,
            }]}

        result = run_negative_control_harness(
            rows,
            trials=20,
            min_n=10,
            discovery_permutations=1,
            search_runner=broken_search,
        )
        self.assertIn("FAIL_NEGATIVE_CONTROL", result["status"])
        self.assertEqual(result["false_positive_trial_rate"], 1.0)
        self.assertFalse(result["negative_control_pass"])

    def test_negative_control_requires_enough_trials_before_pass(self):
        rows = [_row(i, "BULLISH" if i % 2 == 0 else "BEARISH") for i in range(20)]

        def clean_search(*args, **kwargs):
            return {"results": [{
                "robust_discovery_screen": False,
                "search_wide_permutation_p_value": 1.0,
            }]}

        result = run_negative_control_harness(
            rows,
            trials=20,
            min_n=10,
            discovery_permutations=1,
            search_runner=clean_search,
        )
        self.assertEqual(result["status"], "INCONCLUSIVE_NEGATIVE_CONTROL_MORE_TRIALS_REQUIRED")
        self.assertFalse(result["gate_evaluable"])
        self.assertFalse(result["negative_control_pass"])

    def test_negative_control_can_pass_only_with_strict_100_trial_gate(self):
        rows = [_row(i, "BULLISH" if i % 2 == 0 else "BEARISH") for i in range(20)]

        def clean_search(*args, **kwargs):
            return {"results": [{
                "robust_discovery_screen": False,
                "search_wide_permutation_p_value": 1.0,
            }]}

        result = run_negative_control_harness(
            rows,
            trials=100,
            min_n=10,
            discovery_permutations=1,
            search_runner=clean_search,
        )
        self.assertEqual(result["status"], "PASS_NEGATIVE_CONTROL")
        self.assertTrue(result["gate_evaluable"])
        self.assertTrue(result["negative_control_pass"])
        self.assertLessEqual(result["false_positive_trial_rate_wilson_95"][1], 0.05)
        self.assertFalse(result["predictive_edge_proven"])


if __name__ == "__main__":
    unittest.main()
