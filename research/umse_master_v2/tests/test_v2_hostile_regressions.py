from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import random
import unittest

from umse_master.contracts import DataClass, QualityState
from umse_master.liquidity import BookLevel, OrderBookSnapshot
from umse_master.replay import ReplayClass
from umse_master.validation import ConfirmatoryPlan, evaluate_paired_candidate
from umse_master_v2.contracts import (
    EvidenceStatus,
    MBOAction,
    MBORecord,
    QueueSurvivalObservation,
    Side,
)
from umse_master_v2.incremental_value import evaluate_incremental_information
from umse_master_v2.information_velocity import TimedShock
from umse_master_v2.leadlag_null import circular_shift_leadlag_evidence
from umse_master_v2.mechanism_competition import Mechanism, MechanismEvidence, compete_mechanisms
from umse_master_v2.paired_validation import (
    Horizon,
    V2PairedForecastRecord,
    V2ValidationPlan,
    evaluate_v2_horizon,
)
from umse_master_v2.queue_hazard import kaplan_meier_queue_lifetime
from umse_master_v2.queue_survival import reconstruct_queue_survival
from umse_master_v2.resistance_field import ResistanceConfig, estimate_resistance_field


UTC = timezone.utc
T0 = datetime(2026, 9, 12, 12, 0, tzinfo=UTC)
MODEL = "model-v2"
PROTOCOL = "protocol-v2"


def mbo(
    sequence: int,
    action: MBOAction,
    order_id: str,
    event_seconds: float,
    *,
    side: Side = Side.BID,
    size: float = 5.0,
) -> MBORecord:
    event = T0 + timedelta(seconds=event_seconds)
    return MBORecord(
        event_time_utc=event,
        available_time_utc=event,
        ingested_time_utc=event,
        source="CME",
        instrument="NQ",
        data_class=DataClass.REAL_HISTORICAL_MBO,
        quality_state=QualityState.FRESH,
        provenance_id=f"p-{sequence}-{order_id}-{action.value}",
        sequence=sequence,
        order_id=order_id,
        action=action,
        side=side,
        price=20000.0 if side is Side.BID else 20000.25,
        size=size,
    )


def book() -> OrderBookSnapshot:
    return OrderBookSnapshot(
        event_time_utc=T0,
        available_time_utc=T0,
        source="CME",
        instrument="NQ",
        data_class=DataClass.REAL_L2_DEPTH,
        quality_state=QualityState.FRESH,
        provenance_id="book",
        bids=(BookLevel(20000.0, 100.0),),
        asks=(BookLevel(20000.25, 100.0),),
    )


class QueueChronologyRegressionTests(unittest.TestCase):
    def test_sequence_event_time_conflict_fails_closed(self):
        rows = [
            mbo(10, MBOAction.ADD, "o1", 10, size=5),
            mbo(11, MBOAction.CANCEL, "o1", 5, size=5),
        ]
        result = reconstruct_queue_survival(
            rows,
            T0 + timedelta(seconds=20),
            sequence_domain_complete=True,
        )
        self.assertEqual(result.status, EvidenceStatus.PROTOCOL_INELIGIBLE)
        self.assertEqual(result.observations, ())
        self.assertIn("SEQUENCE_EVENT_TIME_ORDER_CONFLICT", result.reasons)

    def test_age_window_excludes_entire_left_truncated_lineage(self):
        rows = [
            mbo(10, MBOAction.ADD, "o1", 0, size=5),
            mbo(11, MBOAction.CANCEL, "o1", 100, size=5),
        ]
        result = reconstruct_queue_survival(
            rows,
            T0 + timedelta(seconds=101),
            max_age_seconds=10,
            sequence_domain_complete=True,
        )
        self.assertEqual(result.observations, ())
        self.assertTrue(any(x.startswith("LEFT_TRUNCATED_LINEAGE_EXCLUDED:o1") for x in result.reasons))
        self.assertNotEqual(result.status, EvidenceStatus.OBSERVED)


class MechanismIdentifiabilityRegressionTests(unittest.TestCase):
    def evidence(self, **overrides) -> MechanismEvidence:
        values = dict(
            aggression_imbalance=0.0,
            signed_price_response=0.0,
            failed_response_score=0.5,
            liquidity_thinness=0.5,
            bid_replenishment=0.5,
            ask_replenishment=0.5,
            queue_exit_asymmetry=0.0,
            information_lead=0.0,
            stress=0.5,
        )
        values.update(overrides)
        return MechanismEvidence(**values)

    def test_passive_accumulation_is_reachable_in_resilient_low_stress_context(self):
        result = compete_mechanisms(self.evidence(
            aggression_imbalance=-0.8,
            failed_response_score=0.5,
            liquidity_thinness=0.0,
            bid_replenishment=1.0,
            ask_replenishment=0.0,
            stress=0.0,
        ))
        self.assertEqual(result.leading_hypothesis, Mechanism.PASSIVE_ACCUMULATION)
        self.assertGreater(result.weights[Mechanism.PASSIVE_ACCUMULATION], result.weights[Mechanism.BID_ABSORPTION])

    def test_bid_absorption_is_reachable_in_stressed_failed_response_context(self):
        result = compete_mechanisms(self.evidence(
            aggression_imbalance=-1.0,
            failed_response_score=1.0,
            liquidity_thinness=1.0,
            bid_replenishment=1.0,
            ask_replenishment=0.0,
            stress=1.0,
        ))
        self.assertEqual(result.leading_hypothesis, Mechanism.BID_ABSORPTION)
        self.assertGreater(result.weights[Mechanism.BID_ABSORPTION], result.weights[Mechanism.PASSIVE_ACCUMULATION])


class LeadLagConfoundRegressionTests(unittest.TestCase):
    def test_symmetric_common_driver_does_not_pass_directional_screen(self):
        # Independent node reactions are clustered around the same external
        # burst clock. Neither node causes the other, but a one-direction shift
        # null sees strong apparent lead/lag in both directions.
        rng = random.Random(1)
        shocks = []
        for i in range(30):
            base = T0 + timedelta(seconds=i * 30)
            for j in range(8):
                t = base + timedelta(seconds=rng.uniform(0.0, 5.0))
                shocks.append(TimedShock("ES", t, t, f"es-{i}-{j}", 1.0))
            for j in range(8):
                t = base + timedelta(seconds=rng.uniform(0.0, 5.0))
                shocks.append(TimedShock("NQ", t, t, f"nq-{i}-{j}", 1.0))

        result = circular_shift_leadlag_evidence(
            shocks,
            T0 + timedelta(seconds=1000),
            source_node="ES",
            target_node="NQ",
            max_lag_seconds=5.0,
            permutations=99,
            alpha=0.05,
            seed=7,
            minimum_events_per_node=20,
        )
        self.assertLessEqual(result.p_value, 0.05)
        self.assertTrue(result.reverse_significant_screen)
        self.assertFalse(result.significant_screen)
        self.assertFalse(result.directional_asymmetry_pass)
        self.assertIn("BIDIRECTIONAL_OR_COMMON_DRIVER_PATTERN", result.reasons)


class SurvivalAndResistanceMutationTests(unittest.TestCase):
    def observation(self, order_id: str, lifetime: float, censored: bool) -> QueueSurvivalObservation:
        entered = T0
        terminal = T0 + timedelta(seconds=lifetime)
        return QueueSurvivalObservation(
            order_id=order_id,
            side=Side.BID,
            price=20000.0,
            entered_time_utc=entered,
            observed_until_utc=terminal,
            lifetime_seconds=lifetime,
            initial_size=1.0,
            terminal_remaining_size=1.0 if censored else 0.0,
            terminal_action=None if censored else MBOAction.CANCEL,
            censored=censored,
        )

    def test_kaplan_meier_survival_must_move_when_exits_occur(self):
        rows = [
            self.observation("a", 1.0, False),
            self.observation("b", 2.0, True),
            self.observation("c", 3.0, False),
            self.observation("d", 4.0, True),
        ]
        result = kaplan_meier_queue_lifetime(rows, minimum_orders=2)
        self.assertEqual(result.status, EvidenceStatus.UNCALIBRATED)
        self.assertAlmostEqual(result.curve[0].survival_probability, 0.75)
        self.assertAlmostEqual(result.curve[2].survival_probability, 0.375)
        self.assertEqual(result.median_survival_seconds, 3.0)

    def test_bid_depletion_reduces_bid_resistance(self):
        rows = [
            mbo(1, MBOAction.CANCEL, "b", 1, side=Side.BID, size=9),
            mbo(2, MBOAction.CANCEL, "a", 2, side=Side.ASK, size=1),
        ]
        result = estimate_resistance_field(
            book(),
            rows,
            T0 + timedelta(seconds=10),
            ResistanceConfig(depth_weight=1.0, provision_weight=0.0, depletion_weight=1.0),
        )
        self.assertEqual(result.status, EvidenceStatus.UNCALIBRATED)
        self.assertLess(result.bid_resistance, result.ask_resistance)


class ValidationProtocolMutationTests(unittest.TestCase):
    def plan(self, n: int, *, alpha: float = 0.05) -> V2ValidationPlan:
        return V2ValidationPlan(
            plan_id=f"p-{n}-{alpha}",
            horizon=Horizon.H8,
            preregistered_n=n,
            target_delta=0.01,
            registered_at_utc=T0 - timedelta(days=1),
            expected_model_fingerprint=MODEL,
            expected_protocol_fingerprint=PROTOCOL,
            block_size=5,
            alpha=alpha,
            power_design_reference="hostile-regression",
        )

    def record(self, i: int, *, early: bool = False) -> V2PairedForecastRecord:
        lock = T0 + timedelta(minutes=i)
        return V2PairedForecastRecord(
            forecast_id=f"f-{i}",
            horizon=Horizon.H8,
            locked_at_utc=lock,
            outcome_time_utc=lock + timedelta(hours=1 if early else 8),
            base_probabilities={"bullish": 0.4, "bearish": 0.3, "neutral": 0.3},
            candidate_probabilities={"bullish": 0.7, "bearish": 0.15, "neutral": 0.15},
            outcome="bullish",
            evidence_hash=f"e-{i}",
            model_fingerprint=MODEL,
            protocol_fingerprint=PROTOCOL,
            replay_class=ReplayClass.FORWARD_OOS,
        )

    def test_fixed_n_check_is_not_optional(self):
        rows = [self.record(i) for i in range(20)]
        result = evaluate_v2_horizon(rows, self.plan(21))
        self.assertFalse(result.protocol_eligible)
        self.assertIn("N_DOES_NOT_MATCH_PREREGISTERED_N", result.blocking_reasons)

    def test_outcome_horizon_check_is_not_optional(self):
        rows = [self.record(i, early=(i == 7)) for i in range(20)]
        result = evaluate_v2_horizon(rows, self.plan(20))
        self.assertFalse(result.protocol_eligible)
        self.assertIn("OUTCOME_RESOLVED_BEFORE_HORIZON", result.blocking_reasons)

    def test_preregistered_alpha_controls_bootstrap_confidence(self):
        outcomes = []
        base = []
        candidate = []
        for i in range(100):
            y = ("bullish", "bearish", "neutral")[i % 3]
            outcomes.append(y)
            other = [c for c in ("bullish", "bearish", "neutral") if c != y]
            margin = 0.01 * (i % 5)
            base.append({y: 0.46 + margin, other[0]: 0.27 - margin / 2, other[1]: 0.27 - margin / 2})
            candidate.append({y: 0.62 + margin, other[0]: 0.19 - margin / 2, other[1]: 0.19 - margin / 2})
        plan = ConfirmatoryPlan(
            plan_id="alpha-001",
            preregistered_n=100,
            target_delta=0.01,
            registered_at_utc=T0 - timedelta(days=1),
            evidence_class=ReplayClass.FORWARD_OOS,
            alpha=0.01,
            block_size=5,
            power_design_reference="hostile-regression",
        )
        result = evaluate_paired_candidate(base, candidate, outcomes, plan=plan, seed=9)
        # The gate is ONE-SIDED (lower bound above zero), so a two-sided
        # (1 - alpha) interval would run the test at alpha/2. The stored
        # two-sided confidence is 1 - 2*alpha, which puts exactly alpha in the
        # lower tail and makes the declared alpha the real test level.
        self.assertAlmostEqual(result.ci_confidence, 0.98)


class IncrementalInformationRegressionTests(unittest.TestCase):
    def test_pure_conditional_noise_does_not_establish_incremental_information(self):
        umse = []
        future = []
        fia = []
        for _ in range(25):
            for z in (0, 1):
                for x in (0, 1):
                    for y in (0, 1):
                        umse.append(x)
                        future.append(y)
                        fia.append(z)
        result = evaluate_incremental_information(
            umse, future, fia, permutations=99, alpha=0.05, seed=3
        )
        self.assertFalse(result.significant_screen)
        self.assertFalse(result.promotion_eligible)

    def test_clear_incremental_signal_can_only_pass_as_uncalibrated_screen(self):
        umse = []
        future = []
        fia = []
        for _ in range(100):
            for z in (0, 1):
                for x in (0, 1):
                    umse.append(x)
                    future.append(x)
                    fia.append(z)
        result = evaluate_incremental_information(
            umse, future, fia, permutations=99, alpha=0.05, seed=4
        )
        self.assertTrue(result.significant_screen)
        self.assertEqual(result.status, EvidenceStatus.UNCALIBRATED)
        self.assertFalse(result.promotion_eligible)


class WorkflowIsolationRegressionTests(unittest.TestCase):
    def test_isolation_workflow_is_not_path_gated(self):
        # Resolve from this file, not the working directory. A CWD-relative
        # path made the guard raise FileNotFoundError whenever the suite ran
        # from anywhere but the repository root, so it errored instead of
        # validating -- and that error masked the true mutation-battery result.
        workflow = (Path(__file__).resolve().parents[3]
                    / ".github" / "workflows" / "umse-v2-research.yml")
        self.assertTrue(workflow.is_file(), f"workflow not found at {workflow}")
        text = workflow.read_text(encoding="utf-8")
        self.assertNotIn("    paths:\n", text)
        self.assertIn("Prove production isolation", text)


if __name__ == "__main__":
    unittest.main()
