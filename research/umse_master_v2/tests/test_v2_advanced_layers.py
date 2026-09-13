from __future__ import annotations

from datetime import datetime, timedelta, timezone
import unittest

from umse_master.replay import ReplayClass
from umse_master_v2.contracts import EvidenceStatus
from umse_master_v2.counterfactual import CounterfactualObservation, estimate_stratified_counterfactual
from umse_master_v2.mechanism_competition import Mechanism, MechanismEvidence, compete_mechanisms
from umse_master_v2.paired_validation import (
    Horizon,
    V2PairedForecastRecord,
    V2ValidationPlan,
    evaluate_v2_horizon,
    evaluate_v2_suite,
)
from umse_master_v2.topology_regime import StatePoint, topological_regime_signature


UTC = timezone.utc
T0 = datetime(2026, 9, 12, 12, 0, tzinfo=UTC)
MODEL = "model-frozen-v2"
PROTOCOL = "protocol-frozen-v2"


class MechanismCompetitionTests(unittest.TestCase):
    def test_inadequate_source_status_fails_closed(self):
        result = compete_mechanisms(MechanismEvidence(
            aggression_imbalance=0.8,
            signed_price_response=0.8,
            failed_response_score=0.1,
            liquidity_thinness=0.5,
            bid_replenishment=0.2,
            ask_replenishment=0.2,
            queue_exit_asymmetry=0.2,
            information_lead=0.5,
            stress=0.4,
            source_status=EvidenceStatus.INSUFFICIENT_DATA,
        ))
        self.assertEqual(result.status, EvidenceStatus.INSUFFICIENT_DATA)
        self.assertEqual(result.weights, {})
        self.assertIsNone(result.leading_hypothesis)

    def test_weights_are_competition_not_predictive_probabilities(self):
        result = compete_mechanisms(MechanismEvidence(
            aggression_imbalance=0.9,
            signed_price_response=0.8,
            failed_response_score=0.1,
            liquidity_thinness=0.2,
            bid_replenishment=0.2,
            ask_replenishment=0.1,
            queue_exit_asymmetry=0.1,
            information_lead=0.7,
            stress=0.2,
        ))
        self.assertEqual(result.status, EvidenceStatus.UNCALIBRATED)
        self.assertAlmostEqual(sum(result.weights.values()), 1.0)
        self.assertEqual(result.leading_hypothesis, Mechanism.INFORMED_BUYING)
        self.assertFalse(result.calibrated)
        self.assertFalse(result.predictive)
        self.assertFalse(result.trader_identity_identifiable)
        self.assertFalse(result.strategic_equilibrium_identified)


class CounterfactualTests(unittest.TestCase):
    def test_post_treatment_conditioning_is_protocol_ineligible(self):
        rows = [
            CounterfactualObservation("a", True, 1.0, True, "p1"),
            CounterfactualObservation("a", False, 0.0, False, "p2"),
        ]
        result = estimate_stratified_counterfactual(rows, minimum_per_arm_per_stratum=1)
        self.assertEqual(result.status, EvidenceStatus.PROTOCOL_INELIGIBLE)
        self.assertIsNone(result.estimate)

    def test_missing_overlap_is_not_identifiable(self):
        rows = [CounterfactualObservation("a", True, float(i), True, f"t{i}") for i in range(10)]
        rows += [CounterfactualObservation("b", False, float(i), True, f"c{i}") for i in range(10)]
        result = estimate_stratified_counterfactual(rows, minimum_per_arm_per_stratum=3)
        self.assertEqual(result.status, EvidenceStatus.NOT_IDENTIFIABLE)
        self.assertIsNone(result.estimate)
        self.assertFalse(result.causal_claim_allowed)

    def test_balanced_overlap_yields_diagnostic_not_causal_claim(self):
        rows = []
        for stratum in ("low", "high"):
            for i in range(8):
                rows.append(CounterfactualObservation(stratum, True, 2.0 + i * 0.01, True, f"{stratum}-t-{i}"))
                rows.append(CounterfactualObservation(stratum, False, 1.0 + i * 0.01, True, f"{stratum}-c-{i}"))
        result = estimate_stratified_counterfactual(rows, minimum_per_arm_per_stratum=5)
        self.assertEqual(result.status, EvidenceStatus.UNCALIBRATED)
        self.assertAlmostEqual(result.estimate, 1.0)
        self.assertAlmostEqual(result.overlap_fraction, 1.0)
        self.assertFalse(result.causal_claim_allowed)
        self.assertFalse(result.promotion_eligible)


class TopologyTests(unittest.TestCase):
    def point(self, i: int, vector: tuple[float, ...], *, future: bool = False) -> StatePoint:
        event = T0 + timedelta(seconds=i)
        available = T0 + timedelta(days=1) if future else event
        return StatePoint(event, available, vector, f"p-{i}-{future}")

    def test_future_unavailable_points_are_excluded(self):
        rows = [self.point(i, (float(i), float(i % 3))) for i in range(20)]
        rows += [self.point(100 + i, (1000.0, 1000.0), future=True) for i in range(5)]
        result = topological_regime_signature(rows, T0 + timedelta(seconds=200), minimum_points=20)
        self.assertEqual(result.status, EvidenceStatus.UNCALIBRATED)
        self.assertEqual(result.samples, 20)
        self.assertFalse(result.predictive)

    def test_degenerate_cloud_is_not_identifiable(self):
        rows = [self.point(i, (1.0, 1.0)) for i in range(20)]
        result = topological_regime_signature(rows, T0 + timedelta(seconds=100), minimum_points=20)
        self.assertEqual(result.status, EvidenceStatus.NOT_IDENTIFIABLE)
        self.assertIsNone(result.persistence_entropy)

    def test_two_clusters_create_large_merge_scale(self):
        rows = []
        for i in range(10):
            rows.append(self.point(i, (i * 0.01, i * 0.01)))
        for i in range(10, 20):
            rows.append(self.point(i, (10.0 + (i - 10) * 0.01, 10.0)))
        result = topological_regime_signature(rows, T0 + timedelta(seconds=100), minimum_points=20)
        self.assertEqual(result.status, EvidenceStatus.UNCALIBRATED)
        self.assertIsNotNone(result.largest_gap_ratio)
        self.assertGreater(result.largest_gap_ratio, 2.0)
        self.assertIn("LARGE_COMPONENT_MERGE_GAP_PRESENT", result.reasons)


class PairedValidationTests(unittest.TestCase):
    def make_plan(self, horizon: Horizon, n: int, *, registered: datetime | None = None) -> V2ValidationPlan:
        return V2ValidationPlan(
            plan_id=f"plan-{horizon.value}-{n}",
            horizon=horizon,
            preregistered_n=n,
            target_delta=0.010,
            registered_at_utc=registered or (T0 - timedelta(days=1)),
            expected_model_fingerprint=MODEL,
            expected_protocol_fingerprint=PROTOCOL,
            block_size=5,
            power_design_reference="synthetic-test-only",
        )

    def make_rows(self, horizon: Horizon, n: int, *, model: str = MODEL):
        rows = []
        classes = ("bullish", "bearish", "neutral")
        for i in range(n):
            outcome = classes[i % 3]
            wrong1 = classes[(i + 1) % 3]
            wrong2 = classes[(i + 2) % 3]
            # Vary the skill margin so the paired bootstrap has real spread.
            base_correct = 0.42 + 0.02 * (i % 5)
            cand_correct = 0.70 + 0.02 * (i % 4)
            base_rest = (1.0 - base_correct) / 2.0
            cand_rest = (1.0 - cand_correct) / 2.0
            # Non-overlapping locks. Spacing forecasts one minute apart for an
            # 8H horizon makes every outcome window overlap ~480 deep, so the
            # sample carries far less independent information than its row
            # count suggests and the block bootstrap is invalid. The protocol
            # layer now refuses that, so the fixture uses honest spacing.
            lock = T0 + timedelta(seconds=i * horizon.seconds)
            rows.append(V2PairedForecastRecord(
                forecast_id=f"{horizon.value}-{i}",
                horizon=horizon,
                locked_at_utc=lock,
                outcome_time_utc=lock + timedelta(seconds=horizon.seconds),
                base_probabilities={outcome: base_correct, wrong1: base_rest, wrong2: base_rest},
                candidate_probabilities={outcome: cand_correct, wrong1: cand_rest, wrong2: cand_rest},
                outcome=outcome,
                evidence_hash=f"e-{horizon.value}-{i}",
                model_fingerprint=model,
                protocol_fingerprint=PROTOCOL,
                replay_class=ReplayClass.FORWARD_OOS,
            ))
        return rows

    def test_identity_mismatch_blocks_before_numerical_gate(self):
        rows = self.make_rows(Horizon.H8, 100)
        rows[10] = V2PairedForecastRecord(
            **{**rows[10].__dict__, "model_fingerprint": "wrong-model"}
        )
        result = evaluate_v2_horizon(rows, self.make_plan(Horizon.H8, 100))
        self.assertFalse(result.protocol_eligible)
        self.assertIsNone(result.numerical_result)
        self.assertIn("MODEL_FINGERPRINT_MISMATCH", result.blocking_reasons)

    def test_plan_must_predate_first_lock(self):
        rows = self.make_rows(Horizon.H8, 100)
        plan = self.make_plan(Horizon.H8, 100, registered=T0)
        result = evaluate_v2_horizon(rows, plan)
        self.assertFalse(result.protocol_eligible)
        self.assertIn("PLAN_NOT_REGISTERED_BEFORE_FIRST_FORECAST", result.blocking_reasons)

    def test_primary_8h_can_open_secondary_4h_hierarchy_on_strong_synthetic_case(self):
        rows8 = self.make_rows(Horizon.H8, 100)
        rows4 = self.make_rows(Horizon.H4, 100)
        suite = evaluate_v2_suite(
            records_8h=rows8,
            plan_8h=self.make_plan(Horizon.H8, 100),
            records_4h=rows4,
            plan_4h=self.make_plan(Horizon.H4, 100),
            seed=11,
        )
        self.assertTrue(suite.primary_8h.protocol_eligible)
        self.assertIsNotNone(suite.primary_8h.numerical_result)
        self.assertTrue(suite.primary_8h.promotion_gate_pass)
        self.assertTrue(suite.secondary_4h_interpretation_open)
        self.assertTrue(suite.promotion_gate_pass)
        self.assertFalse(suite.predictive_edge_proven)


if __name__ == "__main__":
    unittest.main()
