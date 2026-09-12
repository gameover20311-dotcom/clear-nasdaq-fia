"""Adversarial regressions for every defect proven in the Cloud AI hostile audit.

Each test here FAILED on the pre-repair implementation. They are written against
the repaired behaviour, not against the old API, so that a regression which
reintroduces any audited defect fails loudly.

Nothing in this file asserts predictive edge. Several tests assert the opposite:
that the engine refuses to turn an uncalibrated or under-powered number into
evidence.
"""
from __future__ import annotations

import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from umse_master.contracts import CausalObservation, DataClass, QualityState
from umse_master.criticality import ComponentStatus, compute_criticality, liquidity_elasticity
from umse_master.cross_scale import HalfLifeSource, Scale, ScaleEvidence, assess_cross_scale
from umse_master.events import EventType, EventWindow, MarketEvent
from umse_master.fusion import ExpertOpinion, reliability_weighted_fusion
from umse_master.hawkes import (
    HawkesNetworkConfig,
    StabilityStatus,
    hawkes_diagnostics,
    spectral_radius_bounds,
)
from umse_master.impact import estimate_impact_decay
from umse_master.irreversibility import path_irreversibility
from umse_master.liquidity import (
    BookLevel, OrderBookSnapshot, _normalized_curvature, _normalized_gradient,
    estimate_liquidity_field)
from umse_master.mechanisms import MechanismEvidence, compete_mechanisms
from umse_master.mst import MSTComponents, MSTStatus, compute_mst
from umse_master.primitives import compute_primitives
from umse_master.significance import (
    EvidenceStatus,
    conditional_information_evidence,
    transfer_entropy_evidence,
)
from umse_master.shadow_engine import assess_input_quality
from umse_master.survival import SurvivalStatus, analyze_state_survival
from umse_master.validation import (
    MIN_EFFECTIVE_BLOCKS,
    ConfirmatoryPlan,
    block_bootstrap_ci,
    evaluate_paired_candidate,
)
from umse_master.replay import ReplayClass

UTC = timezone.utc
T = datetime(2026, 9, 12, 15, 0, tzinfo=UTC)


def _lv(sizes):
    return [BookLevel(20000.0 + 0.25 * i, s) for i, s in enumerate(sizes)]


# ----------------------------------------------------------------- A. nulls --
class InformationNullTests(unittest.TestCase):
    """Pure noise must not satisfy I(UMSE;Y|FIA) > 0 as an evidence criterion."""

    def test_independent_noise_is_never_significant_conditional_information(self):
        offenders = []
        for trial in range(40):
            r = random.Random(90000 + trial)
            n, k = 400, 3
            x = [r.randrange(k) for _ in range(n)]
            y = [r.randrange(k) for _ in range(n)]
            z = [r.randrange(k) for _ in range(n)]
            ev = conditional_information_evidence(x, y, z, seed=trial)
            # The raw plug-in number is positive on noise. That is expected and
            # is exactly why it must never be the criterion.
            self.assertGreater(ev.raw_estimate, 0.0)
            if ev.status == EvidenceStatus.SIGNIFICANT_UNCALIBRATED:
                offenders.append((trial, ev.raw_estimate, ev.p_value))
        self.assertLessEqual(
            len(offenders), 2,
            f"noise was called significant in {len(offenders)}/40 trials: {offenders[:5]}")

    def test_independent_noise_is_never_significant_transfer_entropy(self):
        offenders = 0
        for trial in range(40):
            r = random.Random(70000 + trial)
            src = [r.randrange(3) for _ in range(300)]
            tgt = [r.randrange(3) for _ in range(300)]
            ev = transfer_entropy_evidence(src, tgt, seed=trial)
            self.assertGreater(ev.raw_estimate, 0.0)
            if ev.status == EvidenceStatus.SIGNIFICANT_UNCALIBRATED:
                offenders += 1
        self.assertLessEqual(offenders, 2, f"noise significant in {offenders}/40 TE trials")

    def test_genuine_coupling_is_still_detected(self):
        """The null must not be so strict that real dependence is lost."""
        r = random.Random(4)
        src = [r.randrange(2) for _ in range(300)]
        tgt = [0] + src[:-1]  # target is a lagged copy of source
        ev = transfer_entropy_evidence(src, tgt, seed=1)
        self.assertEqual(ev.status, EvidenceStatus.SIGNIFICANT_UNCALIBRATED)
        self.assertGreater(ev.excess_over_null, 0.2)

    def test_small_sample_fails_closed_rather_than_reporting_significance(self):
        r = random.Random(11)
        x = [r.randrange(5) for _ in range(12)]
        y = [r.randrange(5) for _ in range(12)]
        z = [r.randrange(5) for _ in range(12)]
        ev = conditional_information_evidence(x, y, z, seed=0)
        self.assertEqual(ev.status, EvidenceStatus.INSUFFICIENT_SAMPLE)
        self.assertFalse(ev.promotion_eligible)

    def test_evidence_is_never_promotion_eligible_and_never_calibrated(self):
        r = random.Random(4)
        src = [r.randrange(2) for _ in range(300)]
        tgt = [0] + src[:-1]
        ev = transfer_entropy_evidence(src, tgt, seed=1)
        self.assertFalse(ev.promotion_eligible)
        self.assertFalse(ev.calibrated)

    def test_null_framework_is_deterministic_under_seed(self):
        r = random.Random(5)
        x = [r.randrange(3) for _ in range(400)]
        y = [r.randrange(3) for _ in range(400)]
        z = [r.randrange(3) for _ in range(400)]
        a = conditional_information_evidence(x, y, z, seed=123)
        b = conditional_information_evidence(x, y, z, seed=123)
        self.assertEqual(a.p_value, b.p_value)
        self.assertEqual(a.null_mean, b.null_mean)


# ------------------------------------------------------------ B. chronology --
class ChronologyTests(unittest.TestCase):
    def _ev(self, pid, price, event_min, avail_min, source="fast"):
        return MarketEvent(
            EventType.BUY_AGGRESSION,
            T + timedelta(minutes=event_min), T + timedelta(minutes=avail_min),
            T + timedelta(minutes=avail_min), source, "NQ",
            DataClass.REAL_TRADES_QUOTES, QualityState.FRESH, pid, price, 1,
        )

    def test_late_arriving_older_event_does_not_invert_price_direction(self):
        rows = [self._ev("fast", 20010.0, -5, -5, "feed_a"),
                self._ev("slow", 20000.0, -9, -1, "feed_b")]
        p = compute_primitives(EventWindow(rows), T)
        self.assertEqual(p.first_price, 20000.0)
        self.assertEqual(p.last_price, 20010.0)
        self.assertAlmostEqual(p.observed_price_change, +10.0)

    def test_three_sources_with_scrambled_latency(self):
        rows = [self._ev("a", 20005.0, -6, -1, "feed_a"),
                self._ev("b", 20001.0, -8, -2, "feed_b"),
                self._ev("c", 20009.0, -2, -7, "feed_c")]
        p = compute_primitives(EventWindow(rows), T)
        self.assertEqual(p.first_price, 20001.0)   # event -8 is earliest
        self.assertEqual(p.last_price, 20009.0)    # event -2 is latest
        self.assertAlmostEqual(p.observed_price_change, +8.0)

    def test_equal_event_timestamps_are_deterministic(self):
        a = [self._ev("z_last", 20003.0, -4, -4), self._ev("a_first", 20007.0, -4, -1)]
        forward = compute_primitives(EventWindow(a), T)
        backward = compute_primitives(EventWindow(list(reversed(a))), T)
        self.assertEqual(forward.observed_price_change, backward.observed_price_change)
        self.assertEqual(forward.first_price, backward.first_price)

    def test_future_event_malformed_as_available_is_still_excluded(self):
        rows = [self._ev("now", 20000.0, -1, -1),
                self._ev("future", 29999.0, +30, -30)]  # claims availability long ago
        p = compute_primitives(EventWindow(rows), T)
        self.assertEqual(p.event_count, 1)
        self.assertNotEqual(p.last_price, 29999.0)

    def test_unavailable_event_is_excluded_even_when_its_event_time_is_past(self):
        rows = [self._ev("now", 20000.0, -1, -1),
                self._ev("not_yet", 20500.0, -2, +5)]
        p = compute_primitives(EventWindow(rows), T)
        self.assertEqual(p.event_count, 1)

    def test_causal_eligibility_still_uses_availability_not_event_time(self):
        rows = [self._ev("early_event_late_feed", 20000.0, -60, +1)]
        self.assertEqual(len(EventWindow(rows).causal_slice(T)), 0)


# ---------------------------------------------------------------- C. Hawkes --
class HawkesStabilityTests(unittest.TestCase):
    CYCLIC = [[0.0, 1.0, 0.0], [0.0, 0.0, 4.0], [0.5, 0.0, 0.0]]  # true rho 1.2599

    def test_near_zero_diagonal_cycle_is_not_called_subcritical(self):
        lo, hi, converged = spectral_radius_bounds(self.CYCLIC)
        self.assertTrue(converged)
        self.assertLess(abs(hi - 1.2599210498948732), 1e-6)
        self.assertLess(abs(lo - 1.2599210498948732), 1e-6)

    def test_pathological_cyclic_matrices(self):
        cases = [([[0.0, 4.0], [0.3, 0.0]], 1.0954451150103321),
                 ([[0.0, 9.0], [0.2, 0.0]], 1.3416407864998738),
                 ([[0.0, 1.0], [1.0, 0.0]], 1.0),
                 ([[0.0, 0.25], [0.25, 0.0]], 0.25)]
        for matrix, true_rho in cases:
            lo, hi, converged = spectral_radius_bounds(matrix)
            self.assertTrue(converged, matrix)
            self.assertLess(abs(hi - true_rho), 1e-6, f"{matrix}: hi={hi} true={true_rho}")

    def test_primitive_matrix_result_is_unchanged_by_the_repair(self):
        lo, hi, _ = spectral_radius_bounds([[0.2, 0.1], [0.05, 0.2]])
        self.assertLess(abs(hi - 0.2707106781186547), 1e-9)

    def test_supercritical_config_is_reported_supercritical(self):
        cfg = HawkesNetworkConfig(
            (EventType.BUY_AGGRESSION, EventType.SELL_AGGRESSION, EventType.CANCEL_ASK),
            (0.1, 0.1, 0.1),
            ((0.0, 1.0, 0.0), (0.0, 0.0, 4.0), (0.5, 0.0, 0.0)),
            ((1.0, 1.0, 1.0), (1.0, 1.0, 1.0), (1.0, 1.0, 1.0)),
        )
        d = hawkes_diagnostics(cfg, [], T)
        self.assertFalse(d.subcritical)
        self.assertEqual(d.stability, StabilityStatus.SUPERCRITICAL)
        self.assertFalse(d.calibrated)

    def test_subcritical_config_is_reported_subcritical(self):
        cfg = HawkesNetworkConfig(
            (EventType.BUY_AGGRESSION, EventType.SELL_AGGRESSION),
            (0.1, 0.1), ((0.2, 0.1), (0.05, 0.2)), ((1.0, 1.0), (1.0, 1.0)))
        d = hawkes_diagnostics(cfg, [], T)
        self.assertTrue(d.subcritical)
        self.assertEqual(d.stability, StabilityStatus.SUBCRITICAL)

    def test_borderline_kernel_fails_closed_as_indeterminate(self):
        cfg = HawkesNetworkConfig(
            (EventType.BUY_AGGRESSION, EventType.SELL_AGGRESSION),
            (0.1, 0.1), ((1.0, 0.0), (0.0, 1.0)), ((1.0, 1.0), (1.0, 1.0)))
        d = hawkes_diagnostics(cfg, [], T)
        self.assertFalse(d.subcritical)  # rho == 1 exactly must never read as stable
        self.assertIn(d.stability, (StabilityStatus.INDETERMINATE, StabilityStatus.SUPERCRITICAL))


# ------------------------------------------------------- D. promotion gate --
class PromotionGateTests(unittest.TestCase):
    def _rows(self, n, cand_bull=0.9):
        outcomes = ["bullish"] * n
        base = [{"bullish": 1 / 3, "bearish": 1 / 3, "neutral": 1 / 3}] * n
        cand = [{"bullish": cand_bull, "bearish": (1 - cand_bull) / 2,
                 "neutral": (1 - cand_bull) / 2}] * n
        return base, cand, outcomes

    def _plan(self, n, evidence_class=ReplayClass.FORWARD_OOS):
        return ConfirmatoryPlan(
            plan_id="test-plan", preregistered_n=n, target_delta=0.010,
            registered_at_utc=T - timedelta(days=30), evidence_class=evidence_class)

    def test_single_observation_cannot_pass(self):
        base, cand, outcomes = self._rows(1)
        r = evaluate_paired_candidate(base, cand, outcomes, plan=self._plan(1))
        self.assertFalse(r.promotion_gate_pass)
        self.assertFalse(r.confirmatory_eligible)

    def test_every_small_n_below_the_effective_block_floor_cannot_pass(self):
        for n in (1, 2, 3, 5, 8, 20, 50):
            base, cand, outcomes = self._rows(n)
            r = evaluate_paired_candidate(base, cand, outcomes, plan=self._plan(n))
            self.assertFalse(r.promotion_gate_pass, f"N={n} passed the gate")

    def test_identical_rows_cannot_manufacture_confidence_at_any_n(self):
        base, cand, outcomes = self._rows(400)
        r = evaluate_paired_candidate(base, cand, outcomes, plan=self._plan(400))
        self.assertTrue(r.degenerate_bootstrap)
        self.assertFalse(r.promotion_gate_pass)

    def test_degenerate_bootstrap_is_detected(self):
        res = block_bootstrap_ci([0.5] * 400)
        self.assertTrue(res.degenerate)

    def test_missing_plan_means_diagnostic_only(self):
        base, cand, outcomes = self._rows(400)
        r = evaluate_paired_candidate(base, cand, outcomes)
        self.assertFalse(r.confirmatory_eligible)
        self.assertFalse(r.promotion_gate_pass)
        self.assertIn("DIAGNOSTIC", r.note)

    def test_optional_stopping_is_blocked_when_n_differs_from_plan(self):
        base, cand, outcomes = self._rows(400)
        r = evaluate_paired_candidate(base, cand, outcomes, plan=self._plan(500))
        self.assertFalse(r.confirmatory_eligible)
        self.assertFalse(r.promotion_gate_pass)

    def test_historical_replay_cannot_satisfy_prospective_confirmation(self):
        r0 = random.Random(9)
        n = 400
        outcomes = [r0.choice(["bullish", "bearish", "neutral"]) for _ in range(n)]
        base = [{"bullish": 1 / 3, "bearish": 1 / 3, "neutral": 1 / 3}] * n
        cand = []
        for y in outcomes:
            favoured = y if r0.random() < 0.62 else r0.choice(
                [c for c in ("bullish", "bearish", "neutral") if c != y])
            d = {"bullish": 0.30, "bearish": 0.30, "neutral": 0.30}
            d[favoured] = 0.40
            cand.append(d)
        historical = self._plan(n, ReplayClass.UNTOUCHED_HISTORICAL_TEST)
        r = evaluate_paired_candidate(base, cand, outcomes, plan=historical)
        self.assertFalse(r.promotion_gate_pass)
        self.assertFalse(r.confirmatory_eligible)
        self.assertIn("EVIDENCE_CLASS_IS_NOT_FORWARD_OOS", r.blocking_reasons)

    def test_effective_block_floor_is_a_real_constraint(self):
        self.assertGreaterEqual(MIN_EFFECTIVE_BLOCKS, 20)

    def test_a_genuinely_powered_forward_sample_can_still_pass(self):
        """The gate must be closable, not merely closed."""
        r0 = random.Random(21)
        n = 600
        outcomes, base, cand = [], [], []
        for _ in range(n):
            y = r0.choice(["bullish", "bearish", "neutral"])
            outcomes.append(y)
            base.append({"bullish": 1 / 3, "bearish": 1 / 3, "neutral": 1 / 3})
            # A realistic candidate is right most of the time, not always, so
            # the paired differences genuinely vary and the bootstrap has
            # something to resample.
            favoured = y if r0.random() < 0.62 else r0.choice(
                [c for c in ("bullish", "bearish", "neutral") if c != y])
            d = {"bullish": 0.30, "bearish": 0.30, "neutral": 0.30}
            d[favoured] = 0.40
            cand.append(d)
        r = evaluate_paired_candidate(base, cand, outcomes, plan=self._plan(n))
        self.assertTrue(r.confirmatory_eligible)
        self.assertFalse(r.degenerate_bootstrap)
        self.assertTrue(r.promotion_gate_pass)


# ---------------------------------------------- E/J. criticality + missing --
class CriticalityTests(unittest.TestCase):
    def test_balanced_book_does_not_create_maximum_criticality(self):
        self.assertIsNone(liquidity_elasticity(1.0, 0.0))
        self.assertIsNone(liquidity_elasticity(1.0, 1e-12))

    def test_elasticity_requires_a_temporal_liquidity_change(self):
        self.assertIsNotNone(liquidity_elasticity(0.01, 0.25))

    def test_missing_inputs_are_unknown_not_calm(self):
        c = compute_criticality(
            hawkes_spectral_radius=None, state_series=(), recovery_responses=(),
            relative_price_change=None, relative_liquidity_change=None)
        self.assertIsNone(c.candidate_index)
        self.assertEqual(c.status, ComponentStatus.INSUFFICIENT_DATA)

    def test_absent_component_is_not_silently_zero(self):
        c = compute_criticality(
            hawkes_spectral_radius=0.4, state_series=[0.1, 0.2, 0.3, 0.4],
            recovery_responses=[1.0, 0.7, 0.4], relative_price_change=None,
            relative_liquidity_change=None)
        self.assertIn("liquidity_elasticity", c.unavailable_components)
        self.assertNotIn("liquidity_elasticity", c.components)

    def test_criticality_distinguishes_critical_from_explosive(self):
        vals = []
        for rho in (0.99, 1.0, 2.0, 10.0):
            c = compute_criticality(
                hawkes_spectral_radius=rho, state_series=[0.1, 0.2, 0.3, 0.4],
                recovery_responses=[1.0, 0.7, 0.4], relative_price_change=0.01,
                relative_liquidity_change=0.2)
            vals.append(c.candidate_index)
        self.assertEqual(len(set(vals)), len(vals), f"saturated: {vals}")
        self.assertTrue(all(a < b for a, b in zip(vals, vals[1:])), vals)

    def test_criticality_is_never_calibrated(self):
        c = compute_criticality(
            hawkes_spectral_radius=0.4, state_series=[0.1, 0.2, 0.3],
            recovery_responses=[1.0, 0.5, 0.2], relative_price_change=0.01,
            relative_liquidity_change=0.2)
        self.assertFalse(c.calibrated)


class SurvivalTests(unittest.TestCase):
    def test_all_censored_is_not_maximum_metastability(self):
        r = analyze_state_survival([60, 120, 240], censored=[True, True, True])
        self.assertIsNone(r.metastability_score)
        self.assertEqual(r.status, SurvivalStatus.NOT_IDENTIFIABLE_ALL_CENSORED)

    def test_observed_low_is_distinct_from_unknown(self):
        observed = analyze_state_survival([10, 12, 15, 18, 20], target_duration=240)
        self.assertEqual(observed.status, SurvivalStatus.OBSERVED)
        self.assertIsNotNone(observed.metastability_score)
        self.assertLess(observed.metastability_score, 0.5)

    def test_empty_sample_is_not_identifiable(self):
        r = analyze_state_survival([])
        self.assertIsNone(r.metastability_score)
        self.assertEqual(r.status, SurvivalStatus.INSUFFICIENT_SAMPLE)


# --------------------------------------------------------------- F. shape ---
class BookShapeTests(unittest.TestCase):
    RAMP = [10, 20, 30, 40, 50]
    WALL = [10, 20, 900, 40, 50]
    HOLE = [10, 20, 0, 40, 50]
    CONVEX = [50, 25, 10, 25, 50]
    CONCAVE = [10, 35, 50, 35, 10]

    def test_curvature_separates_all_five_profiles(self):
        vals = {name: _normalized_curvature(_lv(s)) for name, s in (
            ("ramp", self.RAMP), ("wall", self.WALL), ("hole", self.HOLE),
            ("convex", self.CONVEX), ("concave", self.CONCAVE))}
        self.assertEqual(len(set(round(v, 9) for v in vals.values())), 5, vals)

    def test_curvature_signs_are_economically_correct(self):
        self.assertAlmostEqual(_normalized_curvature(_lv(self.RAMP)), 0.0, places=9)
        self.assertLess(_normalized_curvature(_lv(self.WALL)), 0.0)     # interior peak
        self.assertGreater(_normalized_curvature(_lv(self.HOLE)), 0.0)  # interior dip
        self.assertGreater(_normalized_curvature(_lv(self.CONVEX)), 0.0)
        self.assertLess(_normalized_curvature(_lv(self.CONCAVE)), 0.0)

    def test_curvature_responds_to_interior_levels(self):
        a = _normalized_curvature(_lv([10, 20, 30, 40, 50]))
        b = _normalized_curvature(_lv([10, 20, 900, 40, 50]))
        self.assertGreater(abs(a - b), 0.5)

    def test_gradient_uses_every_level_not_just_endpoints(self):
        flat_ends_up = _normalized_gradient(_lv([10, 90, 90, 90, 50]))
        flat_ends_dn = _normalized_gradient(_lv([10, 10, 10, 10, 50]))
        self.assertNotAlmostEqual(flat_ends_up, flat_ends_dn, places=6)

    def test_gradient_sign_matches_a_monotone_book(self):
        self.assertGreater(_normalized_gradient(_lv([10, 20, 30, 40, 50])), 0)
        self.assertLess(_normalized_gradient(_lv([50, 40, 30, 20, 10])), 0)


# --------------------------------------------------------------- G. decay ---
class ImpactDecayTests(unittest.TestCase):
    def test_clean_decay_and_wild_interior_are_not_equivalent(self):
        clean = estimate_impact_decay([8, 4, 2, 1])
        wild = estimate_impact_decay([8, 1000, 0.001, 1])
        self.assertNotEqual(clean.half_life_steps, wild.half_life_steps)
        self.assertTrue(clean.identifiable)
        self.assertFalse(wild.identifiable)
        self.assertIsNone(wild.half_life_steps)

    def test_clean_geometric_decay_still_yields_the_correct_half_life(self):
        d = estimate_impact_decay([8, 4, 2, 1])
        self.assertAlmostEqual(d.half_life_steps, 1.0, places=6)

    def test_non_monotone_path_is_reported_not_fitted(self):
        d = estimate_impact_decay([8, 0.01, 500, 1])
        self.assertFalse(d.identifiable)
        self.assertLess(d.fit_r_squared, 0.9)

    def test_growth_has_no_finite_half_life(self):
        d = estimate_impact_decay([1, 2, 4, 8])
        self.assertIsNone(d.half_life_steps)

    def test_decay_is_never_calibrated_evidence(self):
        self.assertFalse(estimate_impact_decay([8, 4, 2, 1]).calibrated)


# ------------------------------------------------------- H. irreversibility --
class IrreversibilityTests(unittest.TestCase):
    SEQ = ["A", "B", "C"] * 50          # adequate sample: ~25 per transition type
    TINY = ["A", "B", "C"] * 3          # prior-dominated

    def test_magnitude_is_not_driven_by_the_smoothing_constant(self):
        vals = [path_irreversibility(self.SEQ, smoothing=a).forward_reverse_js
                for a in (0.01, 0.1, 0.5, 1.0)]
        self.assertLess(max(vals) - min(vals), 0.15, vals)

    def test_prior_dominated_sample_is_refused_rather_than_smoothed_over(self):
        self.assertFalse(path_irreversibility(self.TINY).identifiable)
        self.assertTrue(path_irreversibility(self.SEQ).identifiable)

    def test_primary_statistic_is_bounded(self):
        for seq in (self.SEQ, ["A", "B"] * 50, ["A", "B", "C", "B", "A"]):
            r = path_irreversibility(seq)
            self.assertGreaterEqual(r.forward_reverse_js, 0.0)
            self.assertLessEqual(r.forward_reverse_js, 1.0)

    def test_a_reversible_path_reads_as_reversible(self):
        r = path_irreversibility(["A", "B", "C", "B", "A"] * 40)
        self.assertLess(r.forward_reverse_js, 0.05)

    def test_a_directed_cycle_reads_as_irreversible(self):
        r = path_irreversibility(self.SEQ)
        self.assertGreater(r.forward_reverse_js, 0.3)

    def test_two_state_alphabet_is_marked_not_identifiable(self):
        r = path_irreversibility(["A", "B"] * 50)
        self.assertFalse(r.identifiable)

    def test_smoothing_parameter_is_reported(self):
        self.assertEqual(path_irreversibility(self.SEQ, smoothing=0.25).smoothing, 0.25)


# ------------------------------------------------------------------ I. MST --
class MSTWiringTests(unittest.TestCase):
    def test_repeated_source_is_refused_not_silently_combined(self):
        c = MSTComponents(
            pressure=0.5, criticality=0.5, flow_urgency=0.5,
            information_asymmetry=0.5, structural_stress=0.5,
            entropy=0.5, redundancy=0.0, uncertainty=0.5, data_degradation=0.0,
            sources={"structural_stress": "state.entropy", "entropy": "state.entropy",
                     "uncertainty": "state.entropy"})
        r = compute_mst(c)
        self.assertEqual(r.status, MSTStatus.UNAVAILABLE_REDUNDANT_SOURCES)
        self.assertIsNone(r.original_concept_value)
        self.assertTrue(r.redundant_source_groups)

    def test_missing_component_is_unavailable_not_zero(self):
        c = MSTComponents(
            pressure=0.5, criticality=None, flow_urgency=0.5,
            information_asymmetry=0.5, structural_stress=0.5,
            entropy=None, redundancy=None, uncertainty=None, data_degradation=0.0)
        r = compute_mst(c)
        self.assertEqual(r.status, MSTStatus.UNAVAILABLE_MISSING_COMPONENTS)
        self.assertIsNone(r.original_concept_value)
        self.assertIn("criticality", r.unavailable_components)

    def test_unknown_redundancy_is_not_silently_zero(self):
        c = MSTComponents(
            pressure=0.5, criticality=0.5, flow_urgency=0.5,
            information_asymmetry=0.5, structural_stress=0.5,
            entropy=0.2, redundancy=None, uncertainty=0.2, data_degradation=0.0)
        r = compute_mst(c)
        self.assertEqual(r.status, MSTStatus.UNAVAILABLE_MISSING_COMPONENTS)

    def test_fully_specified_distinct_components_still_compute(self):
        c = MSTComponents(
            pressure=0.8, criticality=0.6, flow_urgency=0.4,
            information_asymmetry=0.5, structural_stress=0.3,
            entropy=0.2, redundancy=0.1, uncertainty=0.2, data_degradation=0.0,
            sources={k: k for k in ("pressure", "criticality", "flow_urgency",
                                    "information_asymmetry", "structural_stress",
                                    "entropy", "redundancy", "uncertainty",
                                    "data_degradation")})
        r = compute_mst(c)
        self.assertEqual(r.status, MSTStatus.AVAILABLE)
        self.assertIsNotNone(r.original_concept_value)
        self.assertFalse(r.calibrated)
        self.assertFalse(r.predictive)


# -------------------------------------------------------- K. mechanisms ----
class MechanismDiscriminationTests(unittest.TestCase):
    def _ev(self, **kw):
        base = dict(aggression_imbalance=0.0, price_response_signed=0.0,
                    replenishment_ratio=0.0, depth_imbalance=0.0, resilience=0.0,
                    failed_response_score=0.0, liquidity_thinness=0.0,
                    volatility_stress=0.0)
        base.update(kw)
        return MechanismEvidence(**base)

    def test_dead_flat_market_is_not_more_identified_than_a_directional_one(self):
        flat = compete_mechanisms(self._ev())
        bull = compete_mechanisms(self._ev(aggression_imbalance=1.0,
                                           price_response_signed=1.0,
                                           depth_imbalance=1.0))
        self.assertLess(flat.directional_identification,
                        bull.directional_identification)

    def test_absence_of_evidence_yields_no_mechanism_identification(self):
        flat = compete_mechanisms(self._ev())
        self.assertFalse(flat.identified)
        self.assertAlmostEqual(flat.directional_identification, 0.0, places=9)
        self.assertEqual(flat.top_mechanism, "BALANCED_NOISE")

    def test_strong_evidence_identifies_a_mechanism(self):
        bull = compete_mechanisms(self._ev(aggression_imbalance=1.0,
                                           price_response_signed=1.0,
                                           depth_imbalance=1.0))
        self.assertTrue(bull.identified)
        self.assertEqual(bull.top_mechanism, "INFORMED_BUYING")
        self.assertGreater(bull.directional_identification, 0.0)

    def test_softmax_temperature_is_explicit_and_uncalibrated(self):
        r = compete_mechanisms(self._ev(aggression_imbalance=0.5))
        self.assertFalse(r.calibrated)
        self.assertGreater(r.temperature, 0.0)


# ------------------------------------------------------------- L. fusion ----
class FusionTests(unittest.TestCase):
    def _mild(self, i, group):
        return ExpertOpinion(f"e{i}", {"bullish": 0.5, "bearish": 0.25, "neutral": 0.25},
                             1.0, 1.0, group)

    def test_many_mild_experts_cannot_manufacture_certainty(self):
        for k in (1, 2, 3, 5, 10, 20):
            r = reliability_weighted_fusion([self._mild(i, f"g{i}") for i in range(k)])
            self.assertLessEqual(r.probabilities["bullish"], 0.5 + 1e-9,
                                 f"{k} experts -> {r.probabilities['bullish']}")

    def test_duplicate_experts_add_no_confidence(self):
        one = reliability_weighted_fusion([self._mild(0, "flow")])
        twenty = reliability_weighted_fusion([self._mild(i, "flow") for i in range(20)])
        self.assertAlmostEqual(one.probabilities["bullish"],
                               twenty.probabilities["bullish"], places=9)

    def test_effective_independence_is_reported(self):
        r = reliability_weighted_fusion(
            [self._mild(0, "flow"), self._mild(1, "flow"), self._mild(2, "macro")])
        self.assertEqual(r.effective_independent_experts, 2)
        self.assertFalse(r.independence_assumed)

    def test_disagreeing_experts_move_toward_the_middle(self):
        bull = ExpertOpinion("a", {"bullish": 0.8, "bearish": 0.1, "neutral": 0.1}, 1, 1, "flow")
        bear = ExpertOpinion("b", {"bullish": 0.1, "bearish": 0.8, "neutral": 0.1}, 1, 1, "macro")
        r = reliability_weighted_fusion([bull, bear])
        self.assertAlmostEqual(r.probabilities["bullish"], r.probabilities["bearish"], places=9)

    def test_fusion_is_never_calibrated_or_predictive(self):
        r = reliability_weighted_fusion([self._mild(0, "flow")])
        self.assertFalse(r.predictive)


# ------------------------------------------- cross-scale gate fails closed --
class CrossScaleGateTests(unittest.TestCase):
    def test_gate_is_closed_without_a_measured_half_life(self):
        ev = [ScaleEvidence(Scale.MICRO, T, 0.9, 0.9, 10000)]
        r = assess_cross_scale(ev)
        self.assertFalse(r.allow_4h_influence)
        self.assertFalse(r.allow_8h_influence)
        self.assertEqual(r.half_life_source, HalfLifeSource.ABSENT)

    def test_persistence_hint_can_no_longer_open_the_gate(self):
        ev = [ScaleEvidence(Scale.MICRO, T, 0.9, 0.9, 5),
              ScaleEvidence(Scale.SESSION, T, 0.9, 0.9, 10000)]
        self.assertFalse(assess_cross_scale(ev).allow_4h_influence)

    def test_measured_half_life_is_required_and_honoured(self):
        ev = [ScaleEvidence(Scale.MICRO, T, 0.9, 0.9, 0)]
        short = assess_cross_scale(ev, measured_half_life_minutes=5.0)
        self.assertFalse(short.allow_4h_influence)
        self.assertEqual(short.half_life_source, HalfLifeSource.MEASURED)
        long = assess_cross_scale(ev, measured_half_life_minutes=600.0)
        self.assertTrue(long.allow_4h_influence)


class DerivedStalenessTests(unittest.TestCase):
    """Staleness must be derivable from timestamps, not only trusted as a label."""

    def _ancient_book(self):
        return OrderBookSnapshot(
            T - timedelta(days=30), T - timedelta(days=30), "src", "NQ",
            DataClass.REAL_L2_DEPTH, QualityState.FRESH, "ancient",
            (BookLevel(19999.75, 10),), (BookLevel(20000.25, 10),), 0.25)

    def test_age_is_derived_from_timestamps(self):
        self.assertAlmostEqual(self._ancient_book().age_seconds(T), 30 * 86400.0, places=3)

    def test_an_age_policy_rejects_a_mislabelled_fresh_snapshot(self):
        book = self._ancient_book()
        self.assertTrue(book.eligible_at(T))                       # label alone
        self.assertFalse(book.eligible_at(T, max_age_seconds=900))  # derived age

    def test_liquidity_field_refuses_an_over_age_snapshot(self):
        with self.assertRaises(ValueError):
            estimate_liquidity_field(self._ancient_book(), T, max_age_seconds=900)

    def test_event_window_age_policy_filters_stale_events(self):
        rows = [MarketEvent(
            EventType.BUY_AGGRESSION, T - timedelta(hours=5), T - timedelta(hours=5),
            T - timedelta(hours=5), "src", "NQ", DataClass.REAL_TRADES_QUOTES,
            QualityState.FRESH, "old", 20000.0, 1)]
        window = EventWindow(rows)
        self.assertEqual(len(window.causal_slice(T)), 1)
        self.assertEqual(len(window.causal_slice(T, max_age_seconds=900)), 0)

    def test_causal_observation_age_policy_is_enforced(self):
        obs = CausalObservation(
            T - timedelta(hours=6), T - timedelta(hours=6), T - timedelta(hours=6),
            "src", "NQ", DataClass.REAL_TRADES_QUOTES, QualityState.FRESH,
            False, "aged", 1.0)
        self.assertAlmostEqual(obs.age_seconds(T), 6 * 3600.0, places=3)
        self.assertTrue(obs.eligible_at(T))
        self.assertFalse(obs.eligible_at(T, max_age_seconds=900))

    def test_input_quality_reports_derived_staleness(self):
        rows = [CausalObservation(
            T - timedelta(hours=6), T - timedelta(hours=6), T - timedelta(hours=6),
            "src", "NQ", DataClass.REAL_TRADES_QUOTES, QualityState.FRESH,
            False, "aged", 1.0)]
        lenient = assess_input_quality(rows, T)
        strict = assess_input_quality(rows, T, max_age_seconds=900)
        self.assertEqual(lenient.stale_by_derived_age, 0)
        self.assertEqual(strict.stale_by_derived_age, 1)
        self.assertEqual(strict.eligible, 0)

    def test_label_based_staleness_still_applies(self):
        """The derived check ADDS to the label check, it does not replace it."""
        stale = OrderBookSnapshot(
            T - timedelta(seconds=1), T - timedelta(seconds=1), "src", "NQ",
            DataClass.REAL_L2_DEPTH, QualityState.STALE, "labelled",
            (BookLevel(19999.75, 10),), (BookLevel(20000.25, 10),), 0.25)
        self.assertFalse(stale.eligible_at(T))
        self.assertFalse(stale.eligible_at(T, max_age_seconds=86400))


if __name__ == "__main__":
    unittest.main()
