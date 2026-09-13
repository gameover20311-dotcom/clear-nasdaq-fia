"""Characterisation tests: the suite must FAIL when the science is broken.

WHY THIS EXISTS
---------------
The hostile audit mutation-tested the pre-repair suite. Six of seven mutations
that destroy core scientific computation left all 38 tests green:

    criticality index  -> constant 0.123     suite OK
    MST numerator      -> always 0           suite OK
    Hawkes excitation  -> disabled           suite OK
    weighted depth     -> always 0           suite OK
    impact nonlinearity-> removed            suite OK
    state inference    -> uniform            suite OK
    mutual information -> constant           suite FAILED

The old suite asserted status enums, hardcoded False flags, hash lengths and
bounds that the implementation itself enforced. None of that can detect a
changed formula.

These tests pin the actual NUMERIC output of each estimator on a fixed
fixture. They are characterisation tests, not correctness proofs: the pinned
values are what the current implementation produces, so any change to the
mathematics must be deliberate and must update the pin. That is the point.

Pinned values are NOT calibration and carry no scientific authority.
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from umse_master.contracts import DataClass, QualityState
from umse_master.criticality import compute_criticality
from umse_master.events import EventType, EventWindow, MarketEvent
from umse_master.hawkes import HawkesNetworkConfig, hawkes_diagnostics
from umse_master.impact import ImpactContext, expected_price_impact
from umse_master.information import (
    conditional_mutual_information, mutual_information, transfer_entropy)
from umse_master.liquidity import BookLevel, OrderBookSnapshot, estimate_liquidity_field
from umse_master.mechanisms import MechanismEvidence, compete_mechanisms
from umse_master.mst import MSTComponents, MSTStatus, compute_mst
from umse_master.primitives import compute_primitives
from umse_master.replay import ReplayClass
from umse_master.state import StateEvidence, infer_state
from umse_master.validation import ConfirmatoryPlan, evaluate_paired_candidate

UTC = timezone.utc
T = datetime(2026, 9, 12, 15, 0, tzinfo=UTC)
PLACES = 9


def _event(idx, typ, size, minute, price=20000.0, order_id=None,
           data_class=DataClass.REAL_L2_DEPTH):
    return MarketEvent(
        typ, T + timedelta(minutes=minute), T + timedelta(minutes=minute),
        T + timedelta(minutes=minute, seconds=1), "fx", "NQ", data_class,
        QualityState.FRESH, f"e{idx}", price, size, None, order_id, False)


def _book():
    return OrderBookSnapshot(
        T - timedelta(seconds=2), T - timedelta(seconds=1), "fx", "NQ",
        DataClass.REAL_L2_DEPTH, QualityState.FRESH, "bk",
        (BookLevel(19999.75, 10), BookLevel(19999.50, 20), BookLevel(19999.25, 30)),
        (BookLevel(20000.25, 8), BookLevel(20000.50, 12), BookLevel(20000.75, 16)),
        0.25)


class WeightedLiquidityDepthCharacterisation(unittest.TestCase):
    """Detects: weighted depth zeroed, decay removed, gradient/curvature broken."""

    def setUp(self):
        self.field = estimate_liquidity_field(
            _book(), T,
            [_event(1, EventType.REPLENISH_BID, 8, -3),
             _event(2, EventType.CANCEL_ASK, 2, -2),
             _event(3, EventType.BUY_AGGRESSION, 15, -1)])

    def test_weighted_depth_values_are_pinned(self):
        self.assertAlmostEqual(self.field.weighted_bid_depth, 38.99132090811655, places=PLACES)
        self.assertAlmostEqual(self.field.weighted_ask_depth, 24.40162193728711, places=PLACES)

    def test_distance_decay_actually_discounts_far_levels(self):
        # Raw depth is 60/36; weighted must be strictly less or the exponential
        # distance decay has been removed.
        self.assertEqual(self.field.bid_depth, 60.0)
        self.assertLess(self.field.weighted_bid_depth, self.field.bid_depth)
        self.assertLess(self.field.weighted_ask_depth, self.field.ask_depth)

    def test_derived_liquidity_values_are_pinned(self):
        self.assertAlmostEqual(self.field.thinness, 0.19361069061881195, places=PLACES)
        self.assertAlmostEqual(self.field.depth_imbalance, 0.25, places=PLACES)
        self.assertAlmostEqual(self.field.bid_gradient, 0.5, places=PLACES)


class HawkesCharacterisation(unittest.TestCase):
    """Detects: excitation disabled, decay ignored, spectral method broken."""

    CONFIG = HawkesNetworkConfig(
        (EventType.BUY_AGGRESSION, EventType.SELL_AGGRESSION),
        (0.1, 0.1), ((0.2, 0.1), (0.05, 0.2)), ((0.5, 0.5), (0.5, 0.5)))

    def _events(self):
        def at(idx, typ, sec):
            return MarketEvent(
                typ, T - timedelta(seconds=sec), T - timedelta(seconds=sec),
                T - timedelta(seconds=sec), "fx", "NQ",
                DataClass.REAL_TRADES_QUOTES, QualityState.FRESH,
                f"h{idx}", 20000.0, 1)
        return [at(1, EventType.BUY_AGGRESSION, 1),
                at(2, EventType.BUY_AGGRESSION, 3),
                at(3, EventType.SELL_AGGRESSION, 2)]

    def test_intensities_are_pinned(self):
        d = hawkes_diagnostics(self.CONFIG, self._events(), T)
        self.assertAlmostEqual(d.intensities["BUY_AGGRESSION"], 0.302720108089, places=PLACES)
        self.assertAlmostEqual(d.intensities["SELL_AGGRESSION"], 0.215058929227, places=PLACES)

    def test_excitation_actually_raises_intensity_above_baseline(self):
        # With excitation disabled every intensity collapses to the baseline.
        d = hawkes_diagnostics(self.CONFIG, self._events(), T)
        for name, value in d.intensities.items():
            self.assertGreater(value, 0.1 + 1e-6, f"{name} fell back to baseline")

    def test_spectral_radius_is_pinned(self):
        d = hawkes_diagnostics(self.CONFIG, self._events(), T)
        self.assertAlmostEqual(d.spectral_radius_upper, 0.541421357105, places=8)


class CriticalityCharacterisation(unittest.TestCase):
    """Detects: index replaced by a constant, components dropped or reweighted."""

    def _diag(self):
        return compute_criticality(
            hawkes_spectral_radius=0.6,
            state_series=[0.1, 0.25, 0.3, 0.28, 0.42],
            recovery_responses=[1.0, 0.7, 0.35, 0.2],
            relative_price_change=0.02, relative_liquidity_change=0.15)

    def test_index_is_pinned(self):
        self.assertAlmostEqual(self._diag().candidate_index,
                               0.34125918977485775, places=PLACES)

    def test_every_component_is_pinned(self):
        expected = {
            "hawkes_spectral_radius": 0.37499999999999994,
            "lag1_autocorrelation": 0.08712121212121222,
            "normalized_variance": 0.1265276779295471,
            "recovery_time_fraction": 1.0,
            "liquidity_elasticity": 0.11764705882352941,
        }
        got = dict(self._diag().components)
        self.assertEqual(sorted(got), sorted(expected))
        for name, value in expected.items():
            self.assertAlmostEqual(got[name], value, places=PLACES, msg=name)

    def test_index_actually_depends_on_its_inputs(self):
        a = self._diag().candidate_index
        b = compute_criticality(
            hawkes_spectral_radius=0.95,
            state_series=[0.1, 0.25, 0.3, 0.28, 0.42],
            recovery_responses=[1.0, 0.7, 0.35, 0.2],
            relative_price_change=0.02,
            relative_liquidity_change=0.15).candidate_index
        self.assertNotAlmostEqual(a, b, places=6)


class MSTCharacterisation(unittest.TestCase):
    """Detects: MST numerator/denominator altered or zeroed."""

    SOURCES = {k: k for k in (
        "pressure", "criticality", "flow_urgency", "information_asymmetry",
        "structural_stress", "entropy", "redundancy", "uncertainty",
        "data_degradation")}

    def _result(self):
        return compute_mst(MSTComponents(
            0.8, 0.6, 0.4, 0.5, 0.3, 0.2, 0.1, 0.2, 0.05, sources=self.SOURCES))

    def test_mst_values_are_pinned(self):
        r = self._result()
        self.assertEqual(r.status, MSTStatus.AVAILABLE)
        self.assertAlmostEqual(r.original_concept_value,
                               0.01858064516129032, places=PLACES)
        self.assertAlmostEqual(r.log_stable_value,
                               0.8253968253968255, places=PLACES)

    def test_numerator_is_a_real_product_of_every_component(self):
        # Zeroing or dropping any numerator factor collapses the value.
        r = self._result()
        self.assertGreater(r.original_concept_value, 0.0)
        weaker = compute_mst(MSTComponents(
            0.4, 0.6, 0.4, 0.5, 0.3, 0.2, 0.1, 0.2, 0.05, sources=self.SOURCES))
        self.assertAlmostEqual(weaker.original_concept_value,
                               r.original_concept_value / 2.0, places=PLACES)


class ImpactCharacterisation(unittest.TestCase):
    """Detects: nonlinearity removed, volatility or resilience terms dropped."""

    CTX = ImpactContext(120.0, 60.0, 0.2, 0.3)

    def test_expected_impact_is_pinned(self):
        self.assertAlmostEqual(expected_price_impact(self.CTX),
                               1.3527260161716879, places=PLACES)

    def test_participation_exponent_is_actually_applied(self):
        # participation = 2.0; with alpha removed the value changes materially.
        half = ImpactContext(60.0, 60.0, 0.2, 0.3)
        ratio = expected_price_impact(self.CTX) / expected_price_impact(half)
        self.assertAlmostEqual(ratio, 2 ** 0.5, places=6)


class StateInferenceCharacterisation(unittest.TestCase):
    """Detects: state inference flattened to uniform or rescored."""

    def _state(self):
        m = compete_mechanisms(MechanismEvidence(0.7, 0.5, 0.6, 0.3, 0.5, 0.2, 0.2, 0.3))
        return m, infer_state(StateEvidence(m.hypothesis_weights, 0.4, 0.5, 0.2, 0.3, 0.4))

    def test_mechanism_values_are_pinned(self):
        m, _ = self._state()
        self.assertEqual(m.top_mechanism, "INFORMED_BUYING")
        self.assertAlmostEqual(m.concentration, 0.2252907282670392, places=PLACES)
        self.assertAlmostEqual(m.directional_identification, 0.09530928531288918, places=PLACES)

    def test_state_values_are_pinned(self):
        _, s = self._state()
        self.assertEqual(s.top_state, "BALANCED_AUCTION")
        self.assertAlmostEqual(s.entropy, 0.9780931471232319, places=PLACES)
        self.assertAlmostEqual(s.state_weights["BALANCED_AUCTION"],
                               0.17060956974979585, places=PLACES)
        self.assertAlmostEqual(s.state_weights["DIRECTIONAL_CASCADE"],
                               0.1326551073023838, places=PLACES)

    def test_state_distribution_is_not_uniform(self):
        _, s = self._state()
        spread = max(s.state_weights.values()) - min(s.state_weights.values())
        self.assertGreater(spread, 0.02, "state inference collapsed to uniform")


class InformationCharacterisation(unittest.TestCase):
    """Detects: MI/CMI/TE formulas altered or replaced by constants."""

    X = [0, 0, 1, 1, 0, 0, 1, 1, 0, 1, 1, 0]
    Y = [0, 0, 1, 1, 1, 0, 1, 0, 0, 1, 1, 1]
    Z = [0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1]

    def test_values_are_pinned(self):
        self.assertAlmostEqual(mutual_information(self.X, self.Y),
                               0.19570962879973108, places=PLACES)
        self.assertAlmostEqual(conditional_mutual_information(self.X, self.Y, self.Z),
                               0.27042604148637794, places=PLACES)
        self.assertAlmostEqual(transfer_entropy(self.X, self.Y),
                               0.3190704549388128, places=PLACES)

    def test_identity_and_independence_endpoints_hold(self):
        self.assertAlmostEqual(mutual_information(self.X, self.X), 1.0, places=PLACES)
        self.assertAlmostEqual(mutual_information(self.X, [0] * len(self.X)),
                               0.0, places=PLACES)


class ChronologyCharacterisation(unittest.TestCase):
    """Detects: price path reverting to feed-arrival order."""

    def _ev(self, pid, price, event_min, avail_min):
        return MarketEvent(
            EventType.BUY_AGGRESSION, T + timedelta(minutes=event_min),
            T + timedelta(minutes=avail_min), T + timedelta(minutes=avail_min),
            "fx", "NQ", DataClass.REAL_TRADES_QUOTES, QualityState.FRESH,
            pid, price, 1)

    def test_price_path_follows_event_order_not_arrival_order(self):
        rows = [self._ev("fast", 20010.0, -5, -5), self._ev("slow", 20000.0, -9, -1)]
        p = compute_primitives(EventWindow(rows), T)
        self.assertAlmostEqual(p.observed_price_change, +10.0, places=PLACES)

    def test_eligibility_still_follows_availability(self):
        rows = [self._ev("pending", 20000.0, -60, +1)]
        self.assertEqual(len(EventWindow(rows).causal_slice(T)), 0)


class PromotionGateCharacterisation(unittest.TestCase):
    """Detects: gate semantics loosened in any direction."""

    def _sample(self, n, seed):
        import random
        r = random.Random(seed)
        outcomes, base, cand = [], [], []
        for _ in range(n):
            y = r.choice(["bullish", "bearish", "neutral"])
            outcomes.append(y)
            base.append({"bullish": 1 / 3, "bearish": 1 / 3, "neutral": 1 / 3})
            favoured = y if r.random() < 0.62 else r.choice(
                [c for c in ("bullish", "bearish", "neutral") if c != y])
            d = {"bullish": 0.30, "bearish": 0.30, "neutral": 0.30}
            d[favoured] = 0.40
            cand.append(d)
        return base, cand, outcomes

    def _plan(self, n, ec=ReplayClass.FORWARD_OOS):
        return ConfirmatoryPlan("char", n, 0.010, T - timedelta(days=30), ec)

    def test_gate_closes_and_opens_on_exactly_the_right_conditions(self):
        base, cand, outcomes = self._sample(600, 21)
        self.assertTrue(evaluate_paired_candidate(
            base, cand, outcomes, plan=self._plan(600)).promotion_gate_pass)
        # every single guard, removed one at a time, must close the gate
        self.assertFalse(evaluate_paired_candidate(
            base, cand, outcomes).promotion_gate_pass)
        self.assertFalse(evaluate_paired_candidate(
            base, cand, outcomes, plan=self._plan(601)).promotion_gate_pass)
        self.assertFalse(evaluate_paired_candidate(
            base, cand, outcomes,
            plan=self._plan(600, ReplayClass.UNTOUCHED_HISTORICAL_TEST)).promotion_gate_pass)
        under_powered = evaluate_paired_candidate(
            base[:50], cand[:50], outcomes[:50], plan=self._plan(50))
        self.assertFalse(under_powered.promotion_gate_pass)
        # Assert the SPECIFIC guard, so removing the block floor cannot be
        # masked by some other reason happening to block the same sample.
        self.assertIn("INSUFFICIENT_EFFECTIVE_BLOCKS", under_powered.blocking_reasons)

    def test_degenerate_sample_is_refused_at_large_n(self):
        n = 600
        outcomes = ["bullish"] * n
        base = [{"bullish": 1 / 3, "bearish": 1 / 3, "neutral": 1 / 3}] * n
        cand = [{"bullish": 0.9, "bearish": 0.05, "neutral": 0.05}] * n
        r = evaluate_paired_candidate(base, cand, outcomes, plan=self._plan(n))
        self.assertTrue(r.degenerate_bootstrap)
        self.assertFalse(r.promotion_gate_pass)


if __name__ == "__main__":
    unittest.main()
