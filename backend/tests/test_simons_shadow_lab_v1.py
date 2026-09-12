import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from simons_shadow_lab_v1.lab import (  # noqa: E402
    CandidateSpec,
    ShadowLab,
    canonical_bytes,
    sha256_bytes,
    sha256_file,
    verify_source_read_only,
)


def write_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_bytes(payload) + b"\n")


def make_event(seq, event_type, fid, payload, prev):
    unsigned = {
        "schema_version": "SOL56_FORWARD_OOS_V4_AUDITED",
        "seq": seq,
        "event_type": event_type,
        "forecast_id": fid,
        "created_at_utc": payload.get("locked_at_utc") or payload.get("resolved_at_utc") or datetime.now(timezone.utc).isoformat(),
        "prev_event_hash": prev,
        "payload": payload,
    }
    return {**unsigned, "event_hash": sha256_bytes(canonical_bytes(unsigned))}


def add_lock(root, seq, fid, locked_at, prev, bull=65.0, confidence=55.0, direction="BULLISH"):
    evidence = {
        "forecast_id": fid,
        "captured_at_utc": locked_at,
        "provider_snapshot": {"causal": True},
    }
    ep = root / "evidence" / (fid + ".json")
    write_json(ep, evidence)
    payload = {
        "locked_at_utc": locked_at,
        "checkpoint_date_et": locked_at[:10],
        "entry": {"contract": "NQZ6", "price": 20000.0},
        "targets": {},
        "models": {
            "BASE_FIA": {
                "direction": direction,
                "bullish_probability": bull,
                "bearish_probability": 100.0 - bull,
                "confidence": confidence,
                "regime": "TREND",
                "status": "READY",
                "data_coverage": 0.9,
                "intelligence_coverage": 0.8,
                "horizon_probabilities": {
                    "4h": {"bullish_probability": bull, "bearish_probability": 100.0-bull, "direction": direction, "confidence": confidence, "actionable": True},
                    "8h": {"bullish_probability": bull, "bearish_probability": 100.0-bull, "direction": direction, "confidence": confidence, "actionable": True},
                },
            }
        },
        "campaign": {"campaign_id": "TEST", "model_fingerprint_digest": "abc"},
        "evidence": {"path": "evidence/%s.json" % fid, "sha256": sha256_file(ep)},
        "eligibility": {"genuinely_new_forward": True},
    }
    event = make_event(seq, "FORECAST_LOCK", fid, payload, prev)
    write_json(root / "events" / ("%08d_forecast-lock_%s.json" % (seq, fid)), event)
    return event


def add_resolution(root, seq, fid, hours, actual, prev, resolved_at):
    payload = {
        "horizon_hours": hours,
        "resolved_at_utc": resolved_at,
        "target_utc": resolved_at,
        "entry_price": 20000.0,
        "outcome_price": 20100.0 if actual == "BULLISH" else 19900.0,
        "actual_direction": actual,
        "resolution_only": True,
    }
    event = make_event(seq, "RESOLUTION_%sH" % hours, fid, payload, prev)
    write_json(root / "events" / ("%08d_resolution-%sh_%s.json" % (seq, hours, fid)), event)
    return event


def write_head(root, events, head_hash, at):
    unsigned = {"schema_version": "SOL56_FORWARD_OOS_V4_AUDITED", "events": events, "head_event_hash": head_hash, "updated_at_utc": at}
    write_json(root / "LEDGER_HEAD.json", {**unsigned, "anchor_hash": sha256_bytes(canonical_bytes(unsigned))})


def write_seal(root):
    unsigned = {"schema_version": "SOL56_FORWARD_OOS_V4_AUDITED", "campaign_id": "TEST-CAMPAIGN", "model_fingerprint": {"digest": "prod-digest"}}
    write_json(root / "FORWARD_OOS_CAMPAIGN_SEAL.json", {**unsigned, "seal_hash": sha256_bytes(canonical_bytes(unsigned))})


class ShadowLabTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.source = self.base / "source"
        self.labroot = self.base / "lab"
        (self.source / "events").mkdir(parents=True)
        (self.source / "evidence").mkdir(parents=True)
        write_seal(self.source)
        t0 = datetime(2026, 9, 1, 17, tzinfo=timezone.utc)
        e1 = add_lock(self.source, 1, "F1", t0.isoformat(), "GENESIS", bull=65, confidence=55)
        e2 = add_resolution(self.source, 2, "F1", 4, "BULLISH", e1["event_hash"], (t0+timedelta(hours=4)).isoformat())
        e3 = add_resolution(self.source, 3, "F1", 8, "BULLISH", e2["event_hash"], (t0+timedelta(hours=8)).isoformat())
        write_head(self.source, 3, e3["event_hash"], (t0+timedelta(hours=8)).isoformat())

    def tearDown(self):
        self.tmp.cleanup()

    def test_source_audit_is_read_only(self):
        before = {str(p.relative_to(self.source)): sha256_file(p) for p in self.source.rglob("*") if p.is_file()}
        audit = verify_source_read_only(self.source)
        after = {str(p.relative_to(self.source)): sha256_file(p) for p in self.source.rglob("*") if p.is_file()}
        self.assertTrue(audit["ok"], audit["issues"])
        self.assertEqual(before, after)
        self.assertFalse(audit["source_modified"])

    def test_snapshot_does_not_touch_source(self):
        before = {str(p.relative_to(self.source)): sha256_file(p) for p in self.source.rglob("*") if p.is_file()}
        lab = ShadowLab(self.source, self.labroot)
        snap = lab.create_snapshot(now=datetime(2026, 9, 2, tzinfo=timezone.utc))
        after = {str(p.relative_to(self.source)): sha256_file(p) for p in self.source.rglob("*") if p.is_file()}
        self.assertEqual(before, after)
        self.assertEqual(snap["row_count"], 1)
        self.assertEqual(snap["completed_4h"], 1)
        self.assertEqual(snap["completed_8h"], 1)

    def test_candidate_cannot_use_old_row_as_forward_validation(self):
        lab = ShadowLab(self.source, self.labroot)
        snap = lab.create_snapshot(now=datetime(2026, 9, 2, tzinfo=timezone.utc))
        cand = lab.freeze_candidate(CandidateSpec(
            name="bull65",
            horizon_hours=4,
            conditions=[{"field": "bullish_probability", "op": "gte", "value": 60.0}],
            predicted_direction="BULLISH",
            discovery_snapshot_id=snap["snapshot_id"],
            discovery_forecast_ids=["F1"],
            tests_run_before_selection=8,
        ), now=datetime(2026, 9, 2, 1, tzinfo=timezone.utc))
        with self.assertRaises(ValueError):
            lab.lock_candidate_decision(cand["candidate_id"], "F1", now=datetime(2026, 9, 2, 2, tzinfo=timezone.utc))

    def test_new_row_can_be_locked_then_resolved_without_rewriting_decision(self):
        lab = ShadowLab(self.source, self.labroot)
        snap = lab.create_snapshot(now=datetime(2026, 9, 2, tzinfo=timezone.utc))
        cand = lab.freeze_candidate(CandidateSpec(
            name="bull60-follow",
            horizon_hours=4,
            conditions=[{"field": "bullish_probability", "op": "gte", "value": 60.0}, {"field": "confidence", "op": "gte", "value": 40.0}],
            predicted_direction="FOLLOW_FIA",
            discovery_snapshot_id=snap["snapshot_id"],
            discovery_forecast_ids=["F1"],
            tests_run_before_selection=16,
        ), now=datetime(2026, 9, 2, 1, tzinfo=timezone.utc))

        old_head = json.loads((self.source / "LEDGER_HEAD.json").read_text())
        t1 = datetime(2026, 9, 3, 17, tzinfo=timezone.utc)
        e4 = add_lock(self.source, 4, "F2", t1.isoformat(), old_head["head_event_hash"], bull=68, confidence=60)
        write_head(self.source, 4, e4["event_hash"], t1.isoformat())

        decision = lab.lock_candidate_decision(cand["candidate_id"], "F2", now=t1+timedelta(minutes=1))
        decision_path = next((self.labroot / "validation" / cand["candidate_id"] / "events").glob("*decision_lock*"))
        decision_hash_before = sha256_file(decision_path)
        self.assertEqual(decision["payload"]["decision"], "FIRE")
        self.assertFalse(decision["payload"]["outcome_information_read"])

        e5 = add_resolution(self.source, 5, "F2", 4, "BULLISH", e4["event_hash"], (t1+timedelta(hours=4)).isoformat())
        write_head(self.source, 5, e5["event_hash"], (t1+timedelta(hours=4)).isoformat())
        resolution = lab.resolve_candidate_decision(cand["candidate_id"], "F2", now=t1+timedelta(hours=4, minutes=1))
        self.assertTrue(resolution["payload"]["correct"])
        self.assertEqual(decision_hash_before, sha256_file(decision_path))

    def test_tampering_is_detected(self):
        event_path = next((self.source / "events").glob("*forecast-lock*"))
        data = json.loads(event_path.read_text())
        data["payload"]["models"]["BASE_FIA"]["confidence"] = 99
        write_json(event_path, data)
        audit = verify_source_read_only(self.source)
        self.assertFalse(audit["ok"])
        self.assertTrue(any(x.startswith("event_hash:") for x in audit["issues"]))

    def test_no_auto_production_promotion(self):
        lab = ShadowLab(self.source, self.labroot)
        snap = lab.create_snapshot(now=datetime(2026, 9, 2, tzinfo=timezone.utc))
        cand = lab.freeze_candidate(CandidateSpec(
            name="test",
            horizon_hours=8,
            conditions=[{"field": "confidence", "op": "gte", "value": 0}],
            predicted_direction="FOLLOW_FIA",
            discovery_snapshot_id=snap["snapshot_id"],
            discovery_forecast_ids=["F1"],
            tests_run_before_selection=1,
        ), now=datetime(2026, 9, 2, 1, tzinfo=timezone.utc))
        report = lab.candidate_report(cand["candidate_id"])
        self.assertFalse(report["automatic_production_promotion"])
        self.assertFalse(report["predictive_edge_proven"])
        self.assertIn("NOT_PROVEN", report["candidate_status"])


if __name__ == "__main__":
    unittest.main()
