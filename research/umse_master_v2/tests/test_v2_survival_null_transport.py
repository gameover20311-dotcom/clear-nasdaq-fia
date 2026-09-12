from __future__ import annotations

from datetime import datetime, timedelta, timezone
import unittest

from umse_master_v2.contracts import EvidenceStatus, MBOAction, QueueSurvivalObservation, Side
from umse_master_v2.cross_scale_transport import TransportConfig, assess_transport
from umse_master_v2.information_velocity import TimedShock
from umse_master_v2.leadlag_null import circular_shift_leadlag_evidence
from umse_master_v2.model_competition import compare_predictive_complexity
from umse_master_v2.queue_hazard import kaplan_meier_queue_lifetime


UTC = timezone.utc
T0 = datetime(2026, 9, 12, 12, 0, tzinfo=UTC)


def qobs(i: int, lifetime: float, censored: bool) -> QueueSurvivalObservation:
    return QueueSurvivalObservation(
        order_id=f"o{i}",
        side=Side.BID,
        price=20000.0,
        entered_time_utc=T0,
        observed_until_utc=T0 + timedelta(seconds=lifetime),
        lifetime_seconds=lifetime,
        initial_size=10.0,
        terminal_remaining_size=5.0 if censored else 0.0,
        terminal_action=None if censored else MBOAction.CANCEL,
        censored=censored,
    )


class QueueHazardTests(unittest.TestCase):
    def test_all_censored_is_not_maximum_persistence(self):
        rows = [qobs(i, 10 + i, True) for i in range(12)]
        result = kaplan_meier_queue_lifetime(rows, minimum_orders=10)
        self.assertEqual(result.status, EvidenceStatus.NOT_IDENTIFIABLE)
        self.assertIsNone(result.median_survival_seconds)
        self.assertIsNone(result.restricted_mean_survival_seconds)
        self.assertIn("ALL_ORDERS_CENSORED", result.reasons)

    def test_kaplan_meier_retains_censoring(self):
        rows = [qobs(i, float(i + 1), i >= 8) for i in range(12)]
        result = kaplan_meier_queue_lifetime(rows, minimum_orders=10)
        self.assertEqual(result.status, EvidenceStatus.UNCALIBRATED)
        self.assertEqual(result.observed_exits, 8)
        self.assertEqual(result.censored_count, 4)
        self.assertTrue(result.curve)
        self.assertFalse(result.calibrated)


class LeadLagNullTests(unittest.TestCase):
    def test_small_sample_fails_closed(self):
        shocks = []
        for i in range(8):
            s = T0 + timedelta(seconds=10 * i)
            shocks.append(TimedShock("ES", s, s, f"es-{i}", 1.0))
            t = s + timedelta(seconds=2)
            shocks.append(TimedShock("NQ", t, t, f"nq-{i}", 1.0))
        result = circular_shift_leadlag_evidence(
            shocks,
            T0 + timedelta(seconds=200),
            source_node="ES",
            target_node="NQ",
            max_lag_seconds=5.0,
            permutations=199,
            alpha=0.01,
            minimum_events_per_node=20,
        )
        self.assertEqual(result.status, EvidenceStatus.INSUFFICIENT_DATA)
        self.assertFalse(result.significant_screen)

    def test_clear_alignment_beats_shift_null_but_is_not_predictive_proof(self):
        shocks = []
        for i in range(30):
            source = T0 + timedelta(seconds=20 * i)
            target = source + timedelta(seconds=1)
            shocks.append(TimedShock("ES", source, source, f"es-{i}", float(i % 3 - 1)))
            shocks.append(TimedShock("NQ", target, target, f"nq-{i}", float(i % 3 - 1)))
        result = circular_shift_leadlag_evidence(
            shocks,
            T0 + timedelta(seconds=1000),
            source_node="ES",
            target_node="NQ",
            max_lag_seconds=3.0,
            permutations=199,
            alpha=0.01,
            minimum_events_per_node=20,
            seed=7,
        )
        self.assertEqual(result.status, EvidenceStatus.UNCALIBRATED)
        self.assertGreater(result.observed_score, result.null_mean)
        self.assertTrue(result.significant_screen)
        self.assertFalse(result.calibrated)
        self.assertFalse(result.promotion_eligible)

    def test_unresolvable_alpha_raises(self):
        with self.assertRaises(ValueError):
            circular_shift_leadlag_evidence(
                [], T0,
                source_node="ES",
                target_node="NQ",
                max_lag_seconds=3.0,
                permutations=20,
                alpha=0.01,
            )


class CrossScaleTransportTests(unittest.TestCase):
    def test_missing_half_life_blocks_transport(self):
        result = assess_transport(
            source_status=EvidenceStatus.UNCALIBRATED,
            measured_half_life_seconds=None,
            config=TransportConfig(target_horizon_seconds=3600.0, minimum_survival_weight=0.1),
        )
        self.assertEqual(result.status, EvidenceStatus.NOT_IDENTIFIABLE)
        self.assertFalse(result.transport_eligible)

    def test_long_horizon_requires_actual_survival(self):
        result = assess_transport(
            source_status=EvidenceStatus.UNCALIBRATED,
            measured_half_life_seconds=300.0,
            config=TransportConfig(target_horizon_seconds=4 * 3600.0, minimum_survival_weight=0.01),
        )
        self.assertFalse(result.transport_eligible)
        self.assertLess(result.survival_weight, 0.01)

    def test_measured_long_half_life_can_open_gate_without_claiming_edge(self):
        result = assess_transport(
            source_status=EvidenceStatus.OBSERVED,
            measured_half_life_seconds=8 * 3600.0,
            config=TransportConfig(target_horizon_seconds=4 * 3600.0, minimum_survival_weight=0.5),
        )
        self.assertTrue(result.transport_eligible)
        self.assertAlmostEqual(result.survival_weight, 2 ** -0.5)
        self.assertFalse(result.calibrated)


class ModelCompetitionTests(unittest.TestCase):
    def test_small_sample_cannot_prefer_complex_model(self):
        simple = [{"bullish": 1 / 3, "bearish": 1 / 3, "neutral": 1 / 3}] * 10
        complex_ = [{"bullish": 0.9, "bearish": 0.05, "neutral": 0.05}] * 10
        outcomes = ["bullish"] * 10
        result = compare_predictive_complexity(
            simple, complex_, outcomes,
            simple_parameters=1,
            complex_parameters=20,
            minimum_n=30,
        )
        self.assertEqual(result.status, EvidenceStatus.INSUFFICIENT_DATA)
        self.assertFalse(result.complex_preferred)
        self.assertFalse(result.predictive_proof)

    def test_complexity_penalty_can_reject_tiny_fit_improvement(self):
        n = 100
        simple = [{"bullish": 0.60, "bearish": 0.20, "neutral": 0.20}] * n
        complex_ = [{"bullish": 0.605, "bearish": 0.1975, "neutral": 0.1975}] * n
        outcomes = ["bullish"] * n
        result = compare_predictive_complexity(
            simple, complex_, outcomes,
            simple_parameters=2,
            complex_parameters=30,
            minimum_n=30,
        )
        self.assertEqual(result.status, EvidenceStatus.UNCALIBRATED)
        self.assertFalse(result.complex_preferred)
        self.assertFalse(result.predictive_proof)

    def test_large_fit_gain_can_pay_complexity_cost_but_is_still_diagnostic(self):
        n = 100
        simple = [{"bullish": 1 / 3, "bearish": 1 / 3, "neutral": 1 / 3}] * n
        complex_ = [{"bullish": 0.9, "bearish": 0.05, "neutral": 0.05}] * n
        outcomes = ["bullish"] * n
        result = compare_predictive_complexity(
            simple, complex_, outcomes,
            simple_parameters=2,
            complex_parameters=6,
            minimum_n=30,
        )
        self.assertTrue(result.complex_preferred)
        self.assertGreater(result.delta_description_length, 0)
        self.assertFalse(result.predictive_proof)


if __name__ == "__main__":
    unittest.main()
