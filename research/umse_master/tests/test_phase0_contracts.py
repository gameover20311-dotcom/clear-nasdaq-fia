from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from umse_master import (  # noqa: E402
    CausalObservation,
    DataClass,
    HorizonEstimate,
    LatentStateVector,
    QualityState,
    ShadowSnapshot,
    ShadowStatus,
    assess_input_quality,
    build_fail_closed_snapshot,
)


UTC = timezone.utc
T = datetime(2026, 9, 12, 15, 0, tzinfo=UTC)


def obs(
    *,
    available_offset_minutes: int = -1,
    data_class: DataClass = DataClass.REAL_TRADES_QUOTES,
    quality: QualityState = QualityState.FRESH,
    is_proxy: bool = False,
    provenance_id: str = "e1",
) -> CausalObservation:
    return CausalObservation(
        event_time_utc=T - timedelta(minutes=2),
        available_time_utc=T + timedelta(minutes=available_offset_minutes),
        ingested_time_utc=T - timedelta(seconds=30),
        source="test",
        instrument="NQ",
        data_class=data_class,
        quality_state=quality,
        is_proxy=is_proxy,
        provenance_id=provenance_id,
        value=1.0,
    )


class CausalContractTests(unittest.TestCase):
    def test_future_available_observation_is_ineligible(self) -> None:
        row = obs(available_offset_minutes=1)
        self.assertFalse(row.eligible_at(T))
        report = assess_input_quality([row], T)
        self.assertEqual(report.future_unavailable, 1)
        self.assertEqual(report.eligible, 0)

    def test_synthetic_cannot_support_predictive_validation(self) -> None:
        row = obs(data_class=DataClass.SYNTHETIC_TEST)
        self.assertTrue(row.eligible_at(T))
        self.assertFalse(row.can_support_predictive_validation)
        report = assess_input_quality([row], T)
        self.assertEqual(report.synthetic, 1)
        self.assertEqual(report.validation_grade, 0)

    def test_proxy_contract_is_fail_closed(self) -> None:
        with self.assertRaises(ValueError):
            obs(data_class=DataClass.PROXY_RESEARCH, is_proxy=False)

    def test_stale_real_observation_is_not_eligible(self) -> None:
        row = obs(quality=QualityState.STALE)
        self.assertFalse(row.eligible_at(T))
        report = assess_input_quality([row], T)
        self.assertEqual(report.stale_or_missing, 1)
        self.assertEqual(report.validation_grade, 0)


class ShadowContractTests(unittest.TestCase):
    def test_empty_input_returns_insufficient_data(self) -> None:
        snap = build_fail_closed_snapshot([], T, T)
        self.assertEqual(snap.status, ShadowStatus.INSUFFICIENT_DATA)
        self.assertEqual(sorted(x.horizon_hours for x in snap.estimates), [4, 8])
        self.assertFalse(snap.production_effect)

    def test_real_input_still_returns_no_edge_in_phase_zero(self) -> None:
        snap = build_fail_closed_snapshot([obs()], T, T)
        self.assertEqual(snap.status, ShadowStatus.NO_UMSE_EDGE)
        self.assertEqual(snap.invalidation_reasons, ("PHASE_0_NO_VALIDATED_PREDICTIVE_MAPPING",))
        for est in snap.estimates:
            self.assertEqual(est.confidence, 0.0)
            self.assertAlmostEqual(
                est.bullish_probability + est.bearish_probability + est.neutral_probability,
                1.0,
            )

    def test_future_only_input_returns_protocol_ineligible(self) -> None:
        snap = build_fail_closed_snapshot([obs(available_offset_minutes=5)], T, T)
        self.assertEqual(snap.status, ShadowStatus.PROTOCOL_INELIGIBLE)

    def test_shadow_snapshot_cannot_gain_production_effect(self) -> None:
        state = LatentStateVector(0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 1.0, 1.0)
        est4 = HorizonEstimate(
            4,
            {"CHAOS_UNCERTAIN": 1.0},
            {"BALANCED_NOISE": 1.0},
            1 / 3,
            1 / 3,
            1 / 3,
            0.0,
            0.0,
            0.0,
        )
        est8 = HorizonEstimate(
            8,
            {"CHAOS_UNCERTAIN": 1.0},
            {"BALANCED_NOISE": 1.0},
            1 / 3,
            1 / 3,
            1 / 3,
            0.0,
            0.0,
            0.0,
        )
        with self.assertRaises(ValueError):
            ShadowSnapshot(
                schema="UMSE_SHADOW_V1",
                generated_at_utc=T,
                decision_time_utc=T,
                status=ShadowStatus.NO_UMSE_EDGE,
                latent_state=state,
                estimates=(est4, est8),
                evidence_ids=(),
                data_classes_present=(),
                production_effect=True,
            )

    def test_provenance_hash_is_deterministic(self) -> None:
        a = build_fail_closed_snapshot([obs()], T, T)
        b = build_fail_closed_snapshot([obs()], T, T)
        self.assertEqual(a.provenance_hash(), b.provenance_hash())


if __name__ == "__main__":
    unittest.main()
