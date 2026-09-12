import copy
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from simons_shadow_lab_v1.causal_candidate import CausalCandidateLab, CausalCandidateSpec
from simons_shadow_lab_v1.causal_discovery import discover_causal_grid
from simons_shadow_lab_v1.causal_features import extract_lock_time_features, state_signature
from simons_shadow_lab_v1.durable_reader import verify_event_chain
from simons_shadow_lab_v1.experiment_registry import ExperimentRegistry
from simons_shadow_lab_v1.lab import _write_new_json, canonical_bytes, sha256_bytes


def row(fid="F1", locked="2026-09-10T13:00:00+00:00", outcome="BULLISH"):
    return {
        "forecast_id": fid,
        "lock_event_hash": "lockhash-" + fid,
        "locked_at_utc": locked,
        "base": {
            "direction": "BULLISH", "confidence": 62.0, "regime": "TREND", "status": "LIVE",
            "data_coverage": 0.9, "intelligence_coverage": 0.8,
            "h4": {"bullish_probability": 68.0, "bearish_probability": 32.0, "direction": "BULLISH", "confidence": 55.0, "state": "WATCH", "actionable": True},
            "h8": {"bullish_probability": 64.0, "bearish_probability": 36.0, "direction": "BULLISH", "confidence": 50.0, "state": "WATCH", "actionable": True},
            "signals": [
                {"name": "NQ structure", "score": 0.4, "freshness": "recent"},
                {"name": "DXY", "score": 0.2, "freshness": "live"},
                {"name": "US10Y", "score": -0.2, "freshness": "live"},
                {"name": "Mega-cap leadership", "score": 0.3, "freshness": "recent"},
                {"name": "Semiconductors", "score": 0.2, "freshness": "recent"},
            ],
            "source_status": {"macro": "FRED | missing", "dxy": "Yahoo | live"},
        },
        "outcomes": {"4h": {"actual_direction": outcome, "entry_price": 100.0, "outcome_price": 103.0, "resolution_event_hash": "rh"}},
    }


def make_snapshot(root: Path, sid: str, rows):
    core = {"schema_version": "SIMONS_SHADOW_LAB_V1", "snapshot_id": sid, "rows_sha256": sha256_bytes(canonical_bytes(rows)), "row_count": len(rows), "scientific_status": "DISCOVERY_ONLY_NOT_PROVEN"}
    manifest = dict(core); manifest["manifest_sha256"] = sha256_bytes(canonical_bytes(core))
    base = root / "snapshots" / sid
    _write_new_json(base / "manifest.json", manifest)
    _write_new_json(base / "rows.json", {"rows": rows, "rows_sha256": core["rows_sha256"]})


def event(seq, et, fid, prev, payload):
    unsigned = {"schema_version": "X", "seq": seq, "event_type": et, "forecast_id": fid, "created_at_utc": "2026-09-10T13:00:00+00:00", "prev_event_hash": prev, "payload": payload}
    return {**unsigned, "event_hash": sha256_bytes(canonical_bytes(unsigned))}


class ShadowLabCausalTests(unittest.TestCase):
    def test_lock_time_features_ignore_outcomes_completely(self):
        a = row(outcome="BULLISH"); b = copy.deepcopy(a)
        b["outcomes"]["4h"]["actual_direction"] = "BEARISH"; b["outcomes"]["4h"]["outcome_price"] = 1_000_000
        self.assertEqual(extract_lock_time_features(a, 4), extract_lock_time_features(b, 4))
        self.assertFalse(extract_lock_time_features(a, 4)["component_alignment_is_independent_evidence"])

    def test_state_signature_is_deterministic(self):
        features = extract_lock_time_features(row(), 4)
        self.assertEqual(state_signature(features), state_signature(copy.deepcopy(features)))

    def test_causal_grid_small_n_never_auto_selects(self):
        result = discover_causal_grid([row()], min_n=12)
        self.assertFalse(result["automatic_candidate_selection"])
        self.assertEqual(result["scientific_status"], "DISCOVERY_ONLY_NOT_PROVEN")
        self.assertTrue(all(not item["eligible_min_n"] for item in result["results"]))

    def test_durable_chain_detects_tampering(self):
        first = event(1, "FORECAST_LOCK", "F1", "GENESIS", {"models": {}})
        second = event(2, "RESOLUTION_4H", "F1", first["event_hash"], {"actual_direction": "BULLISH"})
        self.assertTrue(verify_event_chain([first, second])["ok"])
        bad = copy.deepcopy(second); bad["payload"]["actual_direction"] = "BEARISH"
        audit = verify_event_chain([first, bad])
        self.assertFalse(audit["ok"])
        self.assertTrue(any("event_hash" in issue for issue in audit["issues"]))

    def test_experiment_registry_is_hash_chained(self):
        with tempfile.TemporaryDirectory() as td:
            reg = ExperimentRegistry(Path(td))
            a = reg.append("GRID", "S1", {"x": [1, 2]}, {"tests": 2})
            b = reg.append("GRID", "S1", {"x": [3]}, {"tests": 1})
            self.assertEqual(b["prev_event_hash"], a["event_hash"])
            self.assertEqual(reg.audit()["experiments_registered"], 2)

    def test_causal_candidate_lifecycle_and_discovery_exclusion(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); lab_root = root / "lab"; source_root = root / "source"
            freeze_time = datetime(2026, 9, 10, 12, 0, tzinfo=timezone.utc)
            discovery = row("D1", "2026-09-10T11:00:00+00:00")
            make_snapshot(lab_root, "S1", [discovery])
            engine = CausalCandidateLab(source_root, lab_root)
            candidate = engine.freeze(CausalCandidateSpec(name="test", horizon_hours=4, conditions=[{"field": "bullish_probability", "op": "gte", "value": 60.0}], predicted_direction="FOLLOW_FIA", discovery_snapshot_id="S1", discovery_forecast_ids=["D1"], tests_run_before_selection=100), now=freeze_time)
            with self.assertRaises(ValueError): engine.lock_from_row(candidate["candidate_id"], discovery)
            future = row("V1", "2026-09-10T13:00:00+00:00", "BULLISH")
            locked = engine.lock_from_row(candidate["candidate_id"], future, now=freeze_time + timedelta(hours=1, minutes=1))
            self.assertEqual(locked["payload"]["decision"], "FIRE")
            self.assertFalse(locked["payload"]["outcome_information_read"])
            resolved = engine.resolve_from_row(candidate["candidate_id"], future, now=freeze_time + timedelta(hours=6))
            self.assertTrue(resolved["payload"]["correct"])
            report = engine.report(candidate["candidate_id"], 1.0)
            self.assertEqual(report["candidate_status"], "INSUFFICIENT_SAMPLE_NOT_PROVEN")
            self.assertFalse(report["predictive_edge_proven"])
            self.assertFalse(report["automatic_production_promotion"])


if __name__ == "__main__":
    unittest.main()
