"""Characterisation and regression tests from the final Cloud closeout re-audit.

WHY THIS FILE EXISTS
--------------------
The closeout re-ran the original 18-mutation battery against the repaired V2
from a valid baseline. Seven mutations survived, all of them destroying real
scientific computation while leaving the suite green:

    4  Kaplan-Meier restricted mean survival time forced to zero
    5  order-book half-life forced to a constant
    6  resistance depth term removed
    9  topological persistence entropy replaced
    10 topological fragmentation index forced constant
    12 information-velocity propagation rate forced constant
    14 complexity BIC penalty removed

They survived because the suite asserted status enums and hardcoded flags
rather than numeric behaviour. The tests below pin the actual output of each
estimator on a fixed fixture. They are characterisation tests, not correctness
proofs: the pinned values are what the current implementation produces, so any
change to the mathematics must be deliberate and must update the pin.

Pinned values are NOT calibration and carry no scientific authority.

The remaining classes are adversarial regressions for defects the closeout
found still open in the repaired build.
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT.parent / "umse_master" / "src"))

from umse_master.contracts import DataClass, QualityState
from umse_master.liquidity import BookLevel, OrderBookSnapshot
from umse_master.replay import ReplayClass

from umse_master_v2.contracts import (
    EvidenceStatus, MBOAction, MBORecord, QueueSurvivalObservation, Side)
from umse_master_v2.information_velocity import TimedShock, estimate_information_velocity
from umse_master_v2.model_competition import compare_predictive_complexity
from umse_master_v2.orderbook_memory import estimate_orderbook_memory
from umse_master_v2.paired_validation import (
    Horizon, V2PairedForecastRecord, V2ValidationPlan, evaluate_v2_horizon)
from umse_master_v2.queue_hazard import kaplan_meier_queue_lifetime
from umse_master_v2.queue_survival import reconstruct_queue_survival
from umse_master_v2.resistance_field import ResistanceConfig, estimate_resistance_field
from umse_master_v2.topology_regime import StatePoint, topological_regime_signature

UTC = timezone.utc
T = datetime(2026, 9, 12, 15, 0, tzinfo=UTC)
PLACES = 9


def _snap(idx, seconds_ago, bid, ask, source="cme", provenance=None):
    t = T - timedelta(seconds=seconds_ago)
    return OrderBookSnapshot(
        t, t, source, "NQZ6", DataClass.REAL_L2_DEPTH, QualityState.FRESH,
        provenance or f"s{idx}", (BookLevel(19999.75, bid),),
        (BookLevel(20000.25, ask),), 0.25)


def _obs(lifetime, censored):
    return QueueSurvivalObservation(
        "o", Side.BID, 20000.0, T, T + timedelta(seconds=lifetime),
        float(lifetime), 10.0, 5.0 if censored else 0.0,
        None if censored else MBOAction.CANCEL, censored)


def _mbo(idx, action, side, size, price=20000.0, source="cme", seconds_ago=5, order_id=None):
    t = T - timedelta(seconds=seconds_ago)
    return MBORecord(
        t, t, t, source, "NQZ6", DataClass.REAL_HISTORICAL_MBO,
        QualityState.FRESH, f"m{idx}", idx, order_id or f"o{idx}",
        action, side, price, size)


# ------------------------------------------------- mutation 4: KM / RMST ----
class KaplanMeierCharacterisation(unittest.TestCase):
    ROWS = ([_obs(1, False), _obs(2, False), _obs(2.5, True), _obs(3, False)]
            + [_obs(10, True)] * 6)

    def test_survival_curve_is_pinned(self):
        d = kaplan_meier_queue_lifetime(self.ROWS, minimum_orders=10, tau_seconds=8.0)
        expected = [(1.0, 0.9), (2.0, 0.8), (2.5, 0.8), (3.0, 0.6857142857142857),
                    (10.0, 0.6857142857142857)]
        self.assertEqual(len(d.curve), len(expected))
        for point, (t_expected, s_expected) in zip(d.curve, expected):
            self.assertAlmostEqual(point.time_seconds, t_expected, places=PLACES)
            self.assertAlmostEqual(point.survival_probability, s_expected, places=PLACES)

    def test_restricted_mean_is_pinned_at_an_explicit_tau(self):
        d = kaplan_meier_queue_lifetime(self.ROWS, minimum_orders=10, tau_seconds=8.0)
        self.assertAlmostEqual(d.restricted_mean_survival_seconds,
                               6.128571428571428, places=PLACES)
        self.assertAlmostEqual(d.restricted_mean_tau_seconds, 8.0, places=PLACES)

    def test_rmst_is_comparable_across_different_follow_up(self):
        """The closeout defect: identical exits gave 4.100 vs 350.600."""
        short = [_obs(1, False), _obs(2, False), _obs(3, False)] + [_obs(5, True)] * 7
        long_ = [_obs(1, False), _obs(2, False), _obs(3, False)] + [_obs(500, True)] * 7
        a = kaplan_meier_queue_lifetime(short, minimum_orders=10, tau_seconds=5.0)
        b = kaplan_meier_queue_lifetime(long_, minimum_orders=10, tau_seconds=5.0)
        self.assertAlmostEqual(a.restricted_mean_survival_seconds,
                               b.restricted_mean_survival_seconds, places=PLACES)

    def test_rmst_without_tau_is_flagged_as_follow_up_dependent(self):
        d = kaplan_meier_queue_lifetime(self.ROWS, minimum_orders=10)
        self.assertIsNone(d.restricted_mean_tau_seconds)
        self.assertIn("RMST_TAU_NOT_SUPPLIED_VALUE_IS_FOLLOW_UP_DEPENDENT", d.reasons)

    def test_short_follow_up_is_reported(self):
        d = kaplan_meier_queue_lifetime(self.ROWS, minimum_orders=10, tau_seconds=1000.0)
        self.assertFalse(d.follow_up_reaches_tau)
        self.assertIn("FOLLOW_UP_DOES_NOT_REACH_TAU", d.reasons)


# ---------------------------------------- mutation 5: order-book memory ----
class OrderBookMemoryCharacterisation(unittest.TestCase):
    SERIES = [(57.0, 3.0), (39.45, 20.55), (40.598, 19.402), (30.429, 29.571),
              (35.636, 24.364), (27.7, 32.3), (34.135, 25.865), (26.874, 33.126),
              (33.681, 26.319), (26.624, 33.376), (33.543, 26.457),
              (26.549, 33.451), (33.502, 26.498), (26.526, 33.474),
              (33.489, 26.511), (26.519, 33.481)]

    def _memory(self):
        snaps = [_snap(i, 160 - 10 * i, b, a) for i, (b, a) in enumerate(self.SERIES)]
        return estimate_orderbook_memory(snaps, T)

    def test_memory_values_are_pinned(self):
        m = self._memory()
        self.assertAlmostEqual(m.lag1_imbalance_correlation,
                               0.25746170482232156, places=PLACES)
        self.assertAlmostEqual(m.imbalance_half_life_steps, 1.0, places=PLACES)
        self.assertAlmostEqual(m.median_interval_seconds, 10.0, places=PLACES)

    def test_half_life_seconds_is_steps_times_interval_not_a_constant(self):
        m = self._memory()
        self.assertAlmostEqual(m.approximate_half_life_seconds, 10.0, places=PLACES)
        self.assertAlmostEqual(
            m.approximate_half_life_seconds,
            m.imbalance_half_life_steps * m.median_interval_seconds, places=PLACES)

    def test_republished_snapshots_do_not_manufacture_memory(self):
        """The closeout defect: lag-1 moved from -0.0981 to +0.4565 on republication."""
        snaps = [_snap(i, 160 - 10 * i, b, a) for i, (b, a) in enumerate(self.SERIES)]
        clean = estimate_orderbook_memory(snaps, T)
        republished = []
        for i, s in enumerate(snaps):
            republished.append(s)
            republished.append(_snap(f"{i}r", 160 - 10 * i - 1,
                                     self.SERIES[i][0], self.SERIES[i][1],
                                     provenance=f"s{i}-repub"))
        dirty = estimate_orderbook_memory(republished, T)
        self.assertEqual(dirty.duplicate_snapshots_dropped, len(snaps))
        self.assertAlmostEqual(dirty.lag1_imbalance_correlation,
                               clean.lag1_imbalance_correlation, places=PLACES)
        self.assertIn("DUPLICATE_SNAPSHOTS_DROPPED", dirty.reasons)


# --------------------------------------------- mutation 6: resistance ------
class ResistanceFieldCharacterisation(unittest.TestCase):
    BOOK = OrderBookSnapshot(
        T - timedelta(seconds=2), T - timedelta(seconds=1), "cme", "NQZ6",
        DataClass.REAL_L2_DEPTH, QualityState.FRESH, "bk",
        (BookLevel(19999.75, 10), BookLevel(19999.50, 20), BookLevel(19999.25, 30)),
        (BookLevel(20000.25, 8), BookLevel(20000.50, 12), BookLevel(20000.75, 16)),
        0.25)
    RECORDS = [
        _mbo(1, MBOAction.ADD, Side.BID, 30, 19999.75),
        _mbo(2, MBOAction.ADD, Side.ASK, 10, 20000.25),
        _mbo(3, MBOAction.CANCEL, Side.BID, 5, 19999.50),
        _mbo(4, MBOAction.TRADE, Side.ASK, 15, 20000.25),
    ]
    CONFIG = ResistanceConfig(1.0, 1.0, 1.0)

    def test_resistance_values_are_pinned(self):
        f = estimate_resistance_field(self.BOOK, self.RECORDS, T, self.CONFIG)
        self.assertAlmostEqual(f.bid_resistance, 0.8175744761936437, places=PLACES)
        self.assertAlmostEqual(f.ask_resistance, 0.4584295167832001, places=PLACES)
        self.assertAlmostEqual(f.directional_asymmetry, 0.35914495941044355, places=PLACES)

    def test_depth_term_actually_contributes(self):
        """Removing the depth term must change the field."""
        f = estimate_resistance_field(self.BOOK, self.RECORDS, T, self.CONFIG)
        no_depth = estimate_resistance_field(
            self.BOOK, self.RECORDS, T, ResistanceConfig(0.0, 1.0, 1.0))
        self.assertNotAlmostEqual(f.bid_resistance, no_depth.bid_resistance, places=6)

    def test_mixed_source_flow_is_refused(self):
        """The closeout defect: a second vendor double-counted provision."""
        mixed = self.RECORDS + [_mbo(9, MBOAction.ADD, Side.BID, 40, 19999.75,
                                     source="vendor2")]
        f = estimate_resistance_field(self.BOOK, mixed, T, self.CONFIG)
        self.assertEqual(f.status, EvidenceStatus.PROTOCOL_INELIGIBLE)
        self.assertIn("MIXED_SOURCE_FLOW_FOR_ONE_INSTRUMENT", f.reasons)

    def test_flow_outside_the_measured_depth_window_is_ignored(self):
        """The closeout defect: a 500-lot add 1000 points away drove the field."""
        f = estimate_resistance_field(self.BOOK, self.RECORDS, T, self.CONFIG)
        far = self.RECORDS + [_mbo(8, MBOAction.ADD, Side.BID, 500.0, 19000.0)]
        g = estimate_resistance_field(self.BOOK, far, T, self.CONFIG)
        self.assertAlmostEqual(f.bid_provision_share, g.bid_provision_share, places=PLACES)


# ------------------------------------- mutations 9 and 10: topology --------
class TopologyCharacterisation(unittest.TestCase):
    def _points(self, n=40, seed=11, dims=3):
        import random
        r = random.Random(seed)
        return [StatePoint(T - timedelta(seconds=n - i), T - timedelta(seconds=n - i),
                           tuple(r.gauss(0, 1) for _ in range(dims)), f"p{i}")
                for i in range(n)]

    def test_topology_values_are_pinned(self):
        s = topological_regime_signature(self._points(), T)
        self.assertAlmostEqual(s.persistence_entropy, 0.970360122799775, places=PLACES)
        self.assertAlmostEqual(s.fragmentation_index, 2.2672387233118334, places=PLACES)
        self.assertAlmostEqual(s.median_merge_scale, 0.687917587264369, places=PLACES)

    def test_entropy_is_a_real_distribution_entropy(self):
        s = topological_regime_signature(self._points(), T)
        self.assertGreater(s.persistence_entropy, 0.0)
        self.assertLessEqual(s.persistence_entropy, 1.0)

    def test_fragmentation_tracks_the_largest_edge(self):
        s = topological_regime_signature(self._points(), T)
        mean_edge = sum(s.mst_edge_lengths) / len(s.mst_edge_lengths)
        self.assertAlmostEqual(s.fragmentation_index,
                               max(s.mst_edge_lengths) / mean_edge, places=PLACES)

    def test_edge_count_is_always_n_minus_one_even_with_duplicates(self):
        """The closeout defect: duplicate points silently vanished from the MST."""
        pts = self._points()
        dupes = pts + [StatePoint(T, T, pts[0].vector, "dup1"),
                       StatePoint(T, T, pts[1].vector, "dup2")]
        s = topological_regime_signature(dupes, T)
        self.assertEqual(len(s.mst_edge_lengths), len(dupes) - 1)
        self.assertEqual(s.duplicate_points, 2)
        self.assertIn("DUPLICATE_STATE_POINTS_PRESENT", s.reasons)

    def test_normalised_merge_scale_is_comparable_across_sample_sizes(self):
        """The closeout defect: median merge fell 1.4539 -> 0.6036 as n grew."""
        small = topological_regime_signature(self._points(n=40, seed=3), T)
        large = topological_regime_signature(self._points(n=320, seed=3), T)
        self.assertGreater(small.median_merge_scale, large.median_merge_scale)
        ratio = small.scale_normalised_median_merge / large.scale_normalised_median_merge
        self.assertLess(abs(ratio - 1.0), 0.35, f"normalised scales diverge: {ratio}")
        self.assertIn("RAW_MERGE_SCALES_ARE_SAMPLE_SIZE_DEPENDENT_USE_NORMALISED",
                      small.reasons)


# ------------------------------------ mutation 12: information velocity ----
class InformationVelocityCharacterisation(unittest.TestCase):
    def _shocks(self):
        out = []
        for i, sec in enumerate([100, 80, 60, 40, 20]):
            t = T - timedelta(seconds=sec)
            out.append(TimedShock("A", t, t, f"a{i}", 1.0 + i))
        for i, sec in enumerate([98, 78, 58, 38, 18]):
            t = T - timedelta(seconds=sec)
            out.append(TimedShock("B", t, t, f"b{i}", 2.0 + i))
        return out

    def test_velocity_values_are_pinned(self):
        v = estimate_information_velocity(
            self._shocks(), T, source_node="A", target_node="B", max_lag_seconds=5.0)
        self.assertEqual(v.matched_pairs, 5)
        self.assertAlmostEqual(v.median_lag_seconds, 2.0, places=PLACES)
        self.assertAlmostEqual(v.propagation_rate_per_second, 0.5, places=PLACES)

    def test_rate_is_the_reciprocal_of_the_median_lag_not_a_constant(self):
        v = estimate_information_velocity(
            self._shocks(), T, source_node="A", target_node="B", max_lag_seconds=5.0)
        self.assertAlmostEqual(v.propagation_rate_per_second,
                               1.0 / v.median_lag_seconds, places=PLACES)


# -------------------------------------- mutation 14: complexity penalty ----
class ComplexityCharacterisation(unittest.TestCase):
    def _rows(self, n=60):
        outcomes, simple, complex_ = [], [], []
        for i in range(n):
            y = ("bullish", "bearish", "neutral")[i % 3]
            outcomes.append(y)
            simple.append({"bullish": 1 / 3, "bearish": 1 / 3, "neutral": 1 / 3})
            d = {"bullish": 0.2, "bearish": 0.2, "neutral": 0.2}
            d[y] = 0.6
            complex_.append(d)
        return simple, complex_, outcomes

    def test_complexity_values_are_pinned(self):
        s, c, o = self._rows()
        r = compare_predictive_complexity(s, c, o, simple_parameters=1, complex_parameters=9)
        self.assertAlmostEqual(r.simple_bic_like, 135.92781920239514, places=PLACES)
        self.assertAlmostEqual(r.complex_bic_like, 98.14817591191786, places=PLACES)
        self.assertAlmostEqual(r.delta_description_length, 37.77964329047728, places=PLACES)

    def test_extra_parameters_are_actually_penalised(self):
        """Removing the k*log(n) penalty must change the verdict."""
        s, c, o = self._rows()
        cheap = compare_predictive_complexity(s, c, o, simple_parameters=1, complex_parameters=9)
        costly = compare_predictive_complexity(s, c, o, simple_parameters=1, complex_parameters=400)
        self.assertGreater(cheap.delta_description_length, costly.delta_description_length)
        self.assertTrue(cheap.complex_preferred)
        self.assertFalse(costly.complex_preferred)


# ---------------------------- closeout protocol and MBO regressions --------
class ValidationProtocolCloseoutRegressions(unittest.TestCase):
    MF, PF = "model-fp", "protocol-fp"

    def _rec(self, i, *, evidence=None, extra_hours=8, spacing_hours=8):
        lock = T + timedelta(hours=i * spacing_hours)
        return V2PairedForecastRecord(
            forecast_id=f"f{i}", horizon=Horizon.H8, locked_at_utc=lock,
            outcome_time_utc=lock + timedelta(hours=extra_hours),
            base_probabilities={"bullish": 1 / 3, "bearish": 1 / 3, "neutral": 1 / 3},
            candidate_probabilities={"bullish": 0.5, "bearish": 0.25, "neutral": 0.25},
            outcome="bullish", evidence_hash=evidence or f"h{i}",
            model_fingerprint=self.MF, protocol_fingerprint=self.PF)

    def _plan(self, n, **kw):
        return V2ValidationPlan(
            plan_id="p", horizon=Horizon.H8, preregistered_n=n, target_delta=0.010,
            registered_at_utc=T - timedelta(days=7),
            expected_model_fingerprint=self.MF,
            expected_protocol_fingerprint=self.PF, **kw)

    def test_duplicate_evidence_hash_is_refused(self):
        rows = [self._rec(i, evidence="SAME_EVIDENCE") for i in range(120)]
        r = evaluate_v2_horizon(rows, self._plan(120))
        self.assertFalse(r.protocol_eligible)
        self.assertIn("DUPLICATE_EVIDENCE_HASH", r.blocking_reasons)

    def test_outcome_resolved_far_after_the_horizon_is_refused(self):
        rows = [self._rec(i, extra_hours=8 + 24 * 30) for i in range(120)]
        r = evaluate_v2_horizon(rows, self._plan(120))
        self.assertFalse(r.protocol_eligible)
        self.assertIn("OUTCOME_RESOLVED_AFTER_MAXIMUM_LAG", r.blocking_reasons)

    def test_overlapping_forecasts_require_a_larger_block_size(self):
        """8H forecasts locked hourly are ~8-deep dependent; block_size 5 is too small."""
        rows = [self._rec(i, spacing_hours=1) for i in range(120)]
        r = evaluate_v2_horizon(rows, self._plan(120))
        self.assertFalse(r.protocol_eligible)
        self.assertIn("BLOCK_SIZE_BELOW_FORECAST_OVERLAP", r.blocking_reasons)
        ok = evaluate_v2_horizon(rows, self._plan(120, block_size=8))
        self.assertNotIn("BLOCK_SIZE_BELOW_FORECAST_OVERLAP", ok.blocking_reasons)

    def test_non_overlapping_forecasts_pass_the_overlap_guard(self):
        rows = [self._rec(i) for i in range(120)]
        r = evaluate_v2_horizon(rows, self._plan(120))
        self.assertNotIn("BLOCK_SIZE_BELOW_FORECAST_OVERLAP", r.blocking_reasons)
        self.assertTrue(r.protocol_eligible)


class QueueSurvivalCloseoutRegressions(unittest.TestCase):
    def _rec(self, seq, order_id, action, seconds_ago, size=10.0):
        return _mbo(seq, action, Side.BID, size, 20000.0,
                    seconds_ago=seconds_ago, order_id=order_id)

    def test_duplicate_packets_do_not_close_a_partially_filled_order(self):
        """The closeout defect: a duplicated fill closed a half-filled order."""
        rows = [self._rec(1, "D", MBOAction.ADD, 100, 10.0),
                self._rec(2, "D", MBOAction.TRADE, 50, 5.0)]
        duplicate = self._rec(2, "D", MBOAction.TRADE, 50, 5.0)
        r = reconstruct_queue_survival(rows + [duplicate], T,
                                       sequence_domain_complete=True)
        self.assertEqual(len(r.observations), 1)
        self.assertTrue(r.observations[0].censored)
        self.assertAlmostEqual(r.observations[0].terminal_remaining_size, 5.0, places=PLACES)
        self.assertIn("DUPLICATE_RECORDS_DROPPED", r.reasons)

    def test_distinct_partial_fills_still_close_the_order(self):
        rows = [self._rec(1, "C", MBOAction.ADD, 100, 10.0),
                self._rec(2, "C", MBOAction.TRADE, 60, 5.0),
                self._rec(3, "C", MBOAction.TRADE, 50, 5.0)]
        r = reconstruct_queue_survival(rows, T, sequence_domain_complete=True)
        self.assertEqual(len(r.observations), 1)
        self.assertFalse(r.observations[0].censored)
        self.assertAlmostEqual(r.observations[0].lifetime_seconds, 50.0, places=PLACES)


class WorkflowIsolationPathRegression(unittest.TestCase):
    def test_workflow_lookup_does_not_depend_on_the_working_directory(self):
        """The closeout defect: the isolation guard used a CWD-relative path.

        Run from anywhere but the repository root it raised FileNotFoundError,
        so the guard silently errored instead of validating. That also masked
        the true mutation result, because every run reported a failure.
        """
        workflow = ROOT.parents[1] / ".github" / "workflows" / "umse-v2-research.yml"
        self.assertTrue(workflow.is_file(), f"workflow not found at {workflow}")
        text = workflow.read_text(encoding="utf-8")
        self.assertIn("research/umse-master-v2-full", text)
        push_block = text.split("push:", 1)[1].split("workflow_dispatch", 1)[0]
        self.assertNotIn("paths:", push_block)


if __name__ == "__main__":
    unittest.main()
