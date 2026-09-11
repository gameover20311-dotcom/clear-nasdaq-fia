import unittest

from simons_shadow_lab_v1.research_metrics import (
    calibration_report,
    candidate_forward_metrics,
    full_research_diagnostic,
    parameter_robustness_report,
    regime_report,
    state_transition_report,
)


def _row(fid, ts, regime, bull, confidence, actual):
    return {
        "forecast_id": fid,
        "locked_at_utc": ts,
        "base": {
            "direction": "BULLISH" if bull >= 50 else "BEARISH",
            "confidence": confidence,
            "regime": regime,
            "h4": {
                "bullish_probability": bull,
                "bearish_probability": 100 - bull,
                "direction": "BULLISH" if bull >= 50 else "BEARISH",
                "confidence": confidence,
                "actionable": True,
            },
            "h8": {
                "bullish_probability": bull,
                "bearish_probability": 100 - bull,
                "direction": "BULLISH" if bull >= 50 else "BEARISH",
                "confidence": confidence,
                "actionable": True,
            },
        },
        "outcomes": {
            "4h": {"actual_direction": actual},
            "8h": {"actual_direction": actual},
        },
    }


def _rows():
    return [
        _row("F1", "2026-09-01T13:00:00+00:00", "TREND", 70, 60, "BULLISH"),
        _row("F2", "2026-09-02T13:00:00+00:00", "TREND", 65, 55, "BULLISH"),
        _row("F3", "2026-09-03T13:00:00+00:00", "CONFLICTED", 35, 50, "BEARISH"),
        _row("F4", "2026-09-04T13:00:00+00:00", "CONFLICTED", 40, 45, "BEARISH"),
        _row("F5", "2026-09-05T13:00:00+00:00", "TREND", 60, 40, "BEARISH"),
        _row("F6", "2026-09-06T13:00:00+00:00", "TREND", 75, 65, "BULLISH"),
    ]


class ShadowLabAdvancedMetricsTests(unittest.TestCase):
    def test_calibration_report_is_descriptive_and_not_proven(self):
        report = calibration_report(_rows(), 4)
        self.assertEqual(report["n"], 6)
        self.assertIsNotNone(report["brier_score"])
        self.assertIsNotNone(report["log_loss"])
        self.assertIsNotNone(report["ece"])
        self.assertEqual(report["scientific_status"], "INSUFFICIENT_SAMPLE_NOT_PROVEN")

    def test_regime_and_transition_reports_keep_small_groups_exploratory(self):
        regimes = regime_report(_rows(), 4, min_group_n=3)
        self.assertEqual({g["regime"] for g in regimes["groups"]}, {"CONFLICTED", "TREND"})
        self.assertTrue(all(g["status"] == "EXPLORATORY_ONLY_NOT_PROVEN" for g in regimes["groups"]))

        transitions = state_transition_report(_rows(), 4, min_group_n=1)
        labels = {t["transition"] for t in transitions["transitions"]}
        self.assertIn("TREND->TREND", labels)
        self.assertIn("TREND->CONFLICTED", labels)
        self.assertFalse(transitions["automatic_candidate_generation"])

    def test_parameter_robustness_never_becomes_validation(self):
        candidate = {
            "spec": {
                "horizon_hours": 4,
                "predicted_direction": "BULLISH",
                "conditions": [
                    {"field": "bullish_probability", "op": "gte", "value": 60.0},
                    {"field": "confidence", "op": "gte", "value": 40.0},
                ],
            }
        }
        report = parameter_robustness_report(candidate, _rows())
        self.assertEqual(report["scientific_status"], "DISCOVERY_ROBUSTNESS_ONLY_NOT_VALIDATION")
        self.assertGreater(len(report["variants"]), 1)
        self.assertEqual(report["variants"][0]["label"], "BASE")

    def test_forward_metrics_separate_gross_from_assumed_friction(self):
        events = [
            {
                "event_type": "DECISION_LOCK",
                "forecast_id": "F7",
                "created_at_utc": "2026-09-07T13:00:00+00:00",
                "payload": {"decision": "FIRE", "predicted_direction": "BULLISH"},
            },
            {
                "event_type": "DECISION_RESOLUTION",
                "forecast_id": "F7",
                "payload": {
                    "predicted_direction": "BULLISH",
                    "correct": True,
                    "entry_price": 25000.0,
                    "outcome_price": 25010.0,
                },
            },
            {
                "event_type": "DECISION_LOCK",
                "forecast_id": "F8",
                "created_at_utc": "2026-09-08T13:00:00+00:00",
                "payload": {"decision": "FIRE", "predicted_direction": "BEARISH"},
            },
            {
                "event_type": "DECISION_RESOLUTION",
                "forecast_id": "F8",
                "payload": {
                    "predicted_direction": "BEARISH",
                    "correct": True,
                    "entry_price": 25020.0,
                    "outcome_price": 25012.0,
                },
            },
        ]
        report = candidate_forward_metrics(events, round_trip_cost_points=2.0)
        self.assertEqual(report["resolved_fires"], 2)
        self.assertEqual(report["gross_average_points"], 9.0)
        self.assertEqual(report["net_average_points_after_assumed_friction"], 7.0)
        self.assertFalse(report["predictive_edge_proven"])
        self.assertFalse(report["automatic_production_promotion"])

    def test_full_diagnostic_contains_no_auto_strategy_selection(self):
        report = full_research_diagnostic(_rows(), 8)
        self.assertFalse(report["automatic_strategy_selection"])
        self.assertEqual(report["scientific_status"], "DISCOVERY_ONLY_NOT_PROVEN")
        self.assertIn("calibration", report)
        self.assertIn("regimes", report)
        self.assertIn("state_transitions", report)


if __name__ == "__main__":
    unittest.main()
