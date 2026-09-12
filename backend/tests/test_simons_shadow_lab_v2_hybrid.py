import copy
import tempfile
import unittest
from pathlib import Path

from simons_shadow_lab_v1.causal_discovery import discover_causal_grid
from simons_shadow_lab_v1.causal_features import extract_lock_time_features
from simons_shadow_lab_v1.drift_monitor import permutation_drift_report
from simons_shadow_lab_v1.experiment_registry import ExperimentRegistry
from simons_shadow_lab_v1.isolation_guard import ProductionGuard, ReadOnlyViolation, tree_seal
from simons_shadow_lab_v1.scientific_stats import required_sample_for_rate_difference, search_wide_permutation_null
from simons_shadow_lab_v1.strict_contract import LeakageError, LockTimeRowView, validate_horizon_distribution


def _row(i=0, actual="BULLISH", bull=60.0):
    return {
        "forecast_id": f"F{i}",
        "lock_event_hash": f"lock-{i}",
        "locked_at_utc": f"2026-09-{(i % 20) + 1:02d}T13:00:00+00:00",
        "campaign": "TEST",
        "base": {
            "direction": "BULLISH" if bull >= 50 else "BEARISH",
            "confidence": 55.0,
            "regime": "TREND",
            "status": "LIVE",
            "data_coverage": 0.9,
            "intelligence_coverage": 0.8,
            "h4": {"bullish_probability": bull, "bearish_probability": 100.0-bull, "direction": "BULLISH" if bull >= 50 else "BEARISH", "confidence": 55.0, "state": "WATCH", "actionable": True},
            "h8": {"bullish_probability": bull, "bearish_probability": 100.0-bull, "direction": "BULLISH" if bull >= 50 else "BEARISH", "confidence": 50.0, "state": "WATCH", "actionable": True},
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


class ShadowLabV2HybridTests(unittest.TestCase):
    def test_lock_time_view_blocks_outcomes_even_with_get(self):
        view = LockTimeRowView(_row())
        with self.assertRaises(LeakageError):
            view.get("outcomes")

    def test_nested_future_like_field_is_blocked(self):
        r = _row()
        r["base"]["future_signal"] = 123
        base = LockTimeRowView(r).get("base")
        with self.assertRaises(LeakageError):
            base.get("future_signal")

    def test_features_identical_when_outcomes_change(self):
        a = _row(actual="BULLISH")
        b = copy.deepcopy(a)
        b["outcomes"]["4h"]["actual_direction"] = "BEARISH"
        b["outcomes"]["4h"]["outcome_price"] = 999999.0
        self.assertEqual(extract_lock_time_features(a, 4), extract_lock_time_features(b, 4))
        self.assertTrue(extract_lock_time_features(a, 4)["lock_time_barrier_enforced"])

    def test_real_two_way_distribution_contract(self):
        good = validate_horizon_distribution(_row()["base"], 4)
        self.assertTrue(good["ok"])
        bad = _row()["base"]
        bad["h4"] = dict(bad["h4"])
        bad["h4"]["bullish_probability"] = 80
        bad["h4"]["bearish_probability"] = 30
        self.assertFalse(validate_horizon_distribution(bad, 4)["ok"])
        with self.assertRaises(ValueError):
            extract_lock_time_features({**_row(), "base": bad}, 4)

    def test_discovery_prices_the_full_search(self):
        rows = [_row(i, "BULLISH" if i % 2 == 0 else "BEARISH") for i in range(40)]
        result = discover_causal_grid(rows, min_n=12, permutations=20, permutation_seed=7)
        self.assertGreater(result["tests_run"], 100)
        self.assertTrue(result["full_grid_is_multiplicity_denominator"])
        self.assertIn("SEARCH_WIDE_PERMUTATION_NULL", result["multiple_testing_control"])
        self.assertTrue(result["grid_hash"])
        self.assertTrue(all("bonferroni_p_value" in r for r in result["results"]))
        self.assertTrue(all("search_wide_permutation_p_value" in r for r in result["results"] if r["hit_rate"] is not None))

    def test_discovery_uses_unconditional_direction_baseline(self):
        rows = [_row(i, "BULLISH") for i in range(30)] + [_row(100+i, "BEARISH") for i in range(10)]
        result = discover_causal_grid(rows, min_n=10, permutations=10, permutation_seed=1)
        self.assertAlmostEqual(result["unconditional_direction_baselines"]["4"]["BULLISH"], 0.75)
        bull = next(r for r in result["results"] if r["predicted_direction"] == "BULLISH" and r["n"] >= 10)
        self.assertAlmostEqual(bull["unconditional_direction_baseline"], 0.75)
        self.assertIn("p_value_vs_unconditional_baseline", bull)
        self.assertEqual(result["primary_parametric_null"], "UNCONDITIONAL_HORIZON_DIRECTION_RATE")

    def test_discovery_permutation_null_is_deterministic(self):
        rows = [_row(i, "BULLISH" if i % 2 == 0 else "BEARISH") for i in range(30)]
        a = discover_causal_grid(rows, min_n=10, permutations=10, permutation_seed=99)
        b = discover_causal_grid(rows, min_n=10, permutations=10, permutation_seed=99)
        self.assertEqual(a["grid_hash"], b["grid_hash"])
        self.assertEqual(a["search_wide_permutation_null"], b["search_wide_permutation_null"])

    def test_search_budget_fails_closed(self):
        with self.assertRaises(RuntimeError):
            discover_causal_grid([_row()], max_tests=10)

    def test_generic_permutation_null_runs_search_wide(self):
        null = search_wide_permutation_null(
            {4: ["BULLISH", "BEARISH"] * 10},
            [{"horizon_hours": 4, "predicted_direction": "BULLISH", "selected_indexes": list(range(20))}],
            permutations=20,
            seed=3,
            min_n=10,
        )
        self.assertEqual(null["permutations"], 20)
        self.assertIsNotNone(null["best_by_chance_p95_hit_rate"])

    def test_drift_monitor_does_not_call_small_sample_proven(self):
        report = permutation_drift_report([1, 0, 1, 0], permutations=20, min_segment=3)
        self.assertFalse(report["assessed"])
        self.assertIn("NOT_PROVEN", report["status"])

    def test_drift_monitor_detects_large_break(self):
        report = permutation_drift_report([1.0]*25 + [0.0]*25, permutations=200, alpha=0.05, min_segment=10, seed=5)
        self.assertTrue(report["assessed"])
        self.assertTrue(report["degrading"])
        self.assertLessEqual(report["p_value"], 0.05)

    def test_power_floor_is_not_a_fake_fixed_50(self):
        n = required_sample_for_rate_difference(0.50, 0.58, 0.05, 0.80)
        self.assertGreater(n, 50)

    def test_production_guard_blocks_pathlib_and_preserves_tree(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "production"
            root.mkdir()
            target = root / "ledger.jsonl"
            target.write_text("sealed\n", encoding="utf-8")
            guard = ProductionGuard(root)
            with guard.barrier():
                with self.assertRaises(ReadOnlyViolation):
                    target.write_text("tampered\n", encoding="utf-8")
                self.assertEqual(target.read_text(encoding="utf-8"), "sealed\n")
            self.assertTrue(guard.verify_unchanged()["unchanged"])

    def test_tree_seal_detects_real_change(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            p = root / "x.txt"; p.write_text("a", encoding="utf-8")
            before = tree_seal(root)
            p.write_text("b", encoding="utf-8")
            after = tree_seal(root)
            self.assertNotEqual(before["tree_sha256"], after["tree_sha256"])

    def test_experiment_registry_seals_search_metadata(self):
        with tempfile.TemporaryDirectory() as td:
            reg = ExperimentRegistry(Path(td))
            event = reg.append(
                "CAUSAL_GRID",
                "S1",
                {"thresholds": [55, 60]},
                {"tests_run": 2},
                origin="AI",
                correction_method="BH+BONFERRONI+PERMUTATION",
                acceptance_criteria={"search_wide_p_lte": 0.05},
                search_family="PREDECLARED_GRID",
            )
            self.assertTrue(event["search_space_sha256"])
            self.assertEqual(event["origin"], "AI")
            self.assertTrue(reg.audit()["all_search_spaces_hashed"])


if __name__ == "__main__":
    unittest.main()
