from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from research.simons_shadow_lab.lab import (  # noqa: E402
    CandidateError,
    IntegrityError,
    audit_source,
    benjamini_hochberg,
    build_snapshot,
    canonical_bytes,
    discover_threshold_candidates,
    freeze_candidate,
    load_snapshot,
    sha256_bytes,
    validate_candidate,
    verify_ledger_readonly,
)


def write_json(path: Path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_bytes(obj) + b"\n")


def sha(path: Path):
    import hashlib
    return hashlib.sha256(path.read_bytes()).hexdigest()


class Fixture:
    def __init__(self, root: Path):
        self.backend = root / "backend"
        self.forward = self.backend / "fia_forward_oos"
        self.lab = self.backend / "simons_lab_data"
        (self.backend / "fia").mkdir(parents=True)
        (self.forward / "events").mkdir(parents=True)
        (self.forward / "evidence").mkdir(parents=True)
        engine = self.backend / "fia" / "engine.py"
        engine.write_text("VALUE=1\n")
        files = {"fia/engine.py": sha(engine)}
        fp = {"algorithm": "sha256", "digest": sha256_bytes(canonical_bytes(files)), "files": files}
        unsigned = {"campaign_id": "TEST", "sealed_at_utc": "2026-09-01T00:00:00+00:00", "model_fingerprint": fp}
        seal = dict(unsigned); seal["seal_hash"] = sha256_bytes(canonical_bytes(unsigned))
        write_json(self.forward / "FORWARD_OOS_CAMPAIGN_SEAL.json", seal)
        self.prev, self.seq = "GENESIS", 0

    def append(self, et, fid, payload, when):
        self.seq += 1
        unsigned = {"schema_version": "TEST", "seq": self.seq, "event_type": et,
                    "forecast_id": fid, "created_at_utc": when.isoformat(),
                    "prev_event_hash": self.prev, "payload": payload}
        event = dict(unsigned); event["event_hash"] = sha256_bytes(canonical_bytes(unsigned))
        write_json(self.forward / "events" / f"{self.seq:08d}_{et.lower()}_{fid}.json", event)
        self.prev = event["event_hash"]
        hu = {"schema_version": "TEST", "events": self.seq, "head_event_hash": self.prev, "updated_at_utc": when.isoformat()}
        head = dict(hu); head["anchor_hash"] = sha256_bytes(canonical_bytes(hu))
        write_json(self.forward / "LEDGER_HEAD.json", head)

    def add_row(self, i, when, bull=62.0, actual="BULLISH"):
        fid = f"F{i:03d}"
        evidence = {"captured_at_utc": when.isoformat(), "provider_snapshot": {"data": {"provider_health": {"ok": True}}}}
        ep = self.forward / "evidence" / f"{fid}.json"; write_json(ep, evidence)
        model = {
            "direction": "BULLISH" if bull >= 50 else "BEARISH", "bullish_probability": bull,
            "bearish_probability": 100-bull, "confidence": 60.0, "regime": "TREND", "status": "LIVE",
            "data_coverage": .9, "intelligence_coverage": .8,
            "generated_at": (when-timedelta(minutes=1)).isoformat(),
            "horizon_probabilities": {
                "4h": {"bullish_probability": bull, "bearish_probability": 100-bull, "direction": "BULLISH" if bull>=50 else "BEARISH", "confidence": 60.0},
                "8h": {"bullish_probability": bull, "bearish_probability": 100-bull, "direction": "BULLISH" if bull>=50 else "BEARISH", "confidence": 60.0},
            },
        }
        lock = {"locked_at_utc": when.isoformat(), "checkpoint_date_et": when.date().isoformat(),
                "entry": {"contract": "NQU6", "price": 25000+i}, "models": {"BASE_FIA": model},
                "model_fingerprint": {"digest": "D"}, "campaign": {"campaign_id": "TEST"},
                "evidence": {"path": f"evidence/{fid}.json", "sha256": sha(ep)}}
        self.append("FORECAST_LOCK", fid, lock, when)
        for hours in (4, 8):
            outcome = (25000+i) * (1.002 if actual == "BULLISH" else .998)
            self.append(f"RESOLUTION_{hours}H", fid,
                        {"horizon_hours": hours, "target_utc": (when+timedelta(hours=hours)).isoformat(),
                         "resolved_at_utc": (when+timedelta(hours=hours, minutes=5)).isoformat(),
                         "entry_price": 25000+i, "outcome_price": outcome, "actual_direction": actual},
                        when+timedelta(hours=hours, minutes=5))
        return fid


class TestSimonsShadowLabV1(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.fx = Fixture(Path(self.tmp.name))

    def tearDown(self):
        self.tmp.cleanup()

    def test_source_audit_is_read_only_and_detects_tamper(self):
        t = datetime(2026, 9, 1, 17, tzinfo=timezone.utc); self.fx.add_row(1, t)
        before = {str(p): p.read_bytes() for p in self.fx.forward.rglob("*") if p.is_file()}
        self.assertTrue(audit_source(self.fx.backend, self.fx.forward)["ok"])
        after = {str(p): p.read_bytes() for p in self.fx.forward.rglob("*") if p.is_file()}
        self.assertEqual(before, after)
        (self.fx.forward / "evidence" / "F001.json").write_text("{}\n")
        self.assertFalse(verify_ledger_readonly(self.fx.forward)["ok"])

    def test_snapshot_separates_features_from_outcomes(self):
        t = datetime(2026, 9, 1, 17, tzinfo=timezone.utc); self.fx.add_row(1, t, actual="BEARISH")
        r = build_snapshot(self.fx.backend, self.fx.forward, self.fx.lab); s = load_snapshot(r["data_path"])
        text = json.dumps(s["rows"][0]["features"], sort_keys=True)
        self.assertNotIn("actual_direction", text); self.assertNotIn("outcome_price", text)
        self.assertEqual(s["rows"][0]["outcomes"]["8h"]["actual_direction"], "BEARISH")

    def test_future_evidence_fails_closed(self):
        t = datetime(2026, 9, 1, 17, tzinfo=timezone.utc); self.fx.add_row(1, t)
        ep = self.fx.forward / "evidence" / "F001.json"; obj = json.loads(ep.read_text())
        obj["captured_at_utc"] = (t+timedelta(minutes=1)).isoformat(); write_json(ep, obj)
        with self.assertRaises(IntegrityError):
            build_snapshot(self.fx.backend, self.fx.forward, self.fx.lab)

    def test_small_sample_discovery_fails_closed(self):
        t = datetime(2026, 8, 1, 17, tzinfo=timezone.utc)
        for i in range(1, 6): self.fx.add_row(i, t+timedelta(days=i))
        s = load_snapshot(build_snapshot(self.fx.backend, self.fx.forward, self.fx.lab)["data_path"])
        self.assertEqual(discover_threshold_candidates(s)["status"], "INSUFFICIENT_SAMPLE")

    def test_bh_values_bounded(self):
        q = benjamini_hochberg([.001, .04, .03, .9]); self.assertTrue(all(0 <= x <= 1 for x in q))

    def test_frozen_candidate_cannot_be_retuned_and_uses_future_only(self):
        start = datetime(2026, 7, 1, 17, tzinfo=timezone.utc); ids=[]
        for i in range(1, 31): ids.append(self.fx.add_row(i, start+timedelta(days=i)))
        first = build_snapshot(self.fx.backend, self.fx.forward, self.fx.lab)
        freeze_at = start+timedelta(days=31, hours=1)
        rule = {"horizon": "8h", "direction": "BULLISH", "min_bullish_probability": 55.0,
                "min_confidence": 40.0, "require_horizon_agreement": True}
        c = freeze_candidate(self.fx.lab, candidate_id="C1", rule=rule,
                             discovery_snapshot_id=first["snapshot"]["snapshot_id"],
                             discovery_snapshot_sha256=first["snapshot"]["snapshot_sha256"],
                             discovery_forecast_ids=ids, created_at=freeze_at, minimum_validation_n=3)
        with self.assertRaises(CandidateError):
            freeze_candidate(self.fx.lab, candidate_id="C1", rule={**rule, "min_bullish_probability": 60.0},
                             discovery_snapshot_id=first["snapshot"]["snapshot_id"],
                             discovery_snapshot_sha256=first["snapshot"]["snapshot_sha256"],
                             discovery_forecast_ids=ids, created_at=freeze_at, minimum_validation_n=3)
        for i in range(31, 34): self.fx.add_row(i, freeze_at+timedelta(days=i-30), actual="BEARISH" if i==33 else "BULLISH")
        s2 = load_snapshot(build_snapshot(self.fx.backend, self.fx.forward, self.fx.lab)["data_path"])
        v = validate_candidate(c, s2)
        self.assertEqual(v["eligible_future_rows"], 3); self.assertEqual(v["candidate_metrics"]["fires"], 3)
        self.assertFalse(v["automatic_production_promotion"]); self.assertEqual(v["predictive_edge"], "NOT_PROVEN")

    def test_candidate_tamper_detected(self):
        t = datetime(2026, 9, 1, tzinfo=timezone.utc)
        c = freeze_candidate(self.fx.lab, candidate_id="T", rule={"horizon":"4h","direction":"BULLISH","min_bullish_probability":55},
                             discovery_snapshot_id="S", discovery_snapshot_sha256="X", discovery_forecast_ids=[], created_at=t)
        c = dict(c); c["rule"] = dict(c["rule"]); c["rule"]["min_bullish_probability"] = 51
        with self.assertRaises(CandidateError): validate_candidate(c, {"rows": []})

    def test_lab_has_no_production_fia_import(self):
        source = (BACKEND / "research" / "simons_shadow_lab" / "lab.py").read_text()
        imports = "\n".join(x for x in source.splitlines() if x.lstrip().startswith(("import ", "from ")))
        self.assertNotIn("from fia", imports); self.assertNotIn("import fia", imports)


if __name__ == "__main__":
    unittest.main()
