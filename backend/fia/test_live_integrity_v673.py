"""Storage/recovery regressions. All observations are synthetic TEST ONLY data.

The local SQL adapter uses SQLite to exercise real transactions and exact byte
recovery without a network connection. It is NOT a Postgres integration test.
Run: python -m unittest fia.test_live_integrity_v673 -v (from backend/).
"""
from __future__ import annotations

import asyncio
import copy
import json
import os
import sqlite3
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

from fia import forward_oos as fo, forward_oos_durable as dur, forward_oos_monitor as mon
from fia.premove_watch import _catalyst_risk
from fia import provider_reliability as providers


class Cursor:
    def __init__(self, owner):
        self.owner, self.raw = owner, owner.raw.cursor()

    def __enter__(self): return self
    def __exit__(self, *args): self.raw.close()

    def execute(self, sql, params=()):
        if self.owner.fail_bundle and sql.startswith("INSERT INTO forward_oos_bundles"):
            raise sqlite3.OperationalError("TEST_ONLY simulated bundle storage failure")
        self.raw.execute(sql.replace("%s", "?").replace("NOW()", "CURRENT_TIMESTAMP"), params)
        return self

    def fetchone(self):
        row = self.raw.fetchone()
        return dict(row) if row is not None else None

    def fetchall(self): return [dict(row) for row in self.raw.fetchall()]

    @property
    def rowcount(self): return self.raw.rowcount


class Connection:
    def __init__(self, path, fail_bundle=False):
        self.raw = sqlite3.connect(path)
        self.raw.row_factory = sqlite3.Row
        self.raw.execute("PRAGMA foreign_keys=ON")
        self.fail_bundle = fail_bundle
        with self.cursor() as cur:
            for ddl in dur._SCHEMA: cur.execute(ddl)
        self.commit()

    def cursor(self): return Cursor(self)
    def commit(self): self.raw.commit()
    def __enter__(self): return self

    def __exit__(self, kind, value, tb):
        self.raw.rollback() if kind else self.raw.commit()
        self.raw.close()


class StorageRecovery(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="fia-TEST-storage-")
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.root = self.base / "ledger"
        self.root.mkdir()
        (self.root / "FORWARD_OOS_CAMPAIGN_SEAL.json").write_text('{"campaign_id":"TEST_ONLY"}')
        self.db = self.base / "TEST_ONLY.sqlite"
        self.fail_bundle = False
        for ctx in (patch.object(dur, "_database_url", return_value="TEST_ONLY"),
                    patch.object(dur, "_PG_AVAILABLE", True),
                    patch.object(dur, "_connect", side_effect=lambda: Connection(self.db, self.fail_bundle))):
            ctx.start(); self.addCleanup(ctx.stop)
        self.now = datetime(2026, 9, 9, 17, tzinfo=timezone.utc)

    def observation(self, identifier="TEST-OBS"):
        evidence = fo._write_evidence_once(self.root, identifier, {"TEST_ONLY": True, "sample": [1, 2, 3]})
        return fo._append_event(self.root, "FORECAST_LOCK", identifier,
                                {"evidence": evidence, "locked_at_utc": self.now.isoformat()}, self.now)

    def original_files(self):
        return {str(p.relative_to(self.root)): p.read_bytes() for p in self.root.rglob("*.json")}

    def remove_local(self):
        for p in self.root.rglob("*.json"):
            if p.name != "FORWARD_OOS_CAMPAIGN_SEAL.json": p.unlink()

    def test_complete_redeploy_restores_identical_event_evidence_and_anchor(self):
        self.observation()
        for h in (4, 8):
            fo._append_event(self.root, "RESOLUTION_%sH" % h, "TEST-OBS",
                             {"resolved_at_utc": self.now.isoformat(), "TEST_ONLY": True}, self.now)
        before = self.original_files()
        self.remove_local()
        result = dur.restore_missing(self.root)
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["restored"], 3)
        self.assertEqual(self.original_files(), before)
        self.assertTrue(fo.verify_ledger(self.root)["ok"])
        self.assertEqual(fo.verify_ledger(self.root)["resolution_events"], 2)

    def test_partial_loss_recovers_proofs_when_event_already_exists(self):
        self.observation()
        original = self.original_files()
        (self.root / "evidence/TEST-OBS.json").unlink()
        (self.root / "LEDGER_HEAD.json").unlink()
        self.assertTrue(fo.verify_ledger(self.root)["ok"])
        self.assertEqual(self.original_files(), original)

    def test_legacy_event_only_backup_does_not_invent_missing_proofs(self):
        self.observation()
        with Connection(self.db) as conn:
            conn.raw.execute("DELETE FROM forward_oos_bundles")  # isolated TEST database
        self.remove_local()
        result = dur.restore_missing(self.root)
        self.assertFalse(result["ok"])
        self.assertEqual(result["restored"], 1)
        self.assertFalse((self.root / "evidence/TEST-OBS.json").exists())
        self.assertFalse((self.root / "LEDGER_HEAD.json").exists())
        self.assertFalse(fo.verify_ledger(self.root)["ok"])
        self.assertEqual(dur.durability_status(self.root)["durability"], "DEGRADED")

    def test_local_tampering_is_preserved_and_reported(self):
        self.observation()
        evidence = self.root / "evidence/TEST-OBS.json"
        evidence.chmod(0o644); evidence.write_bytes(b"TEST tampered")
        result = dur.restore_missing(self.root)
        self.assertFalse(result["ok"])
        self.assertEqual(evidence.read_bytes(), b"TEST tampered")
        self.assertFalse(fo.verify_ledger(self.root)["ok"])
        self.assertFalse(dur.durability_status(self.root)["durable"])

    def test_local_anchor_conflict_cannot_report_durable(self):
        self.observation()
        anchor = self.root / "LEDGER_HEAD.json"
        anchor.chmod(0o644)
        anchor.write_bytes(b"TEST corrupt anchor")
        self.assertFalse(fo.verify_ledger(self.root)["ok"])
        self.assertFalse(dur.durability_status(self.root)["durable"])

    def test_corrupt_saved_evidence_is_not_restored(self):
        self.observation()
        with Connection(self.db) as conn:
            conn.raw.execute("UPDATE forward_oos_bundles SET evidence_json=?", (b"TEST tampered",))
        self.remove_local()
        self.assertFalse(dur.restore_missing(self.root)["ok"])
        self.assertFalse((self.root / "evidence/TEST-OBS.json").exists())

    def test_bundle_failure_rolls_back_database_event_and_keeps_local_proof(self):
        self.fail_bundle = True
        self.observation()
        with Connection(self.db) as conn:
            self.assertEqual(conn.raw.execute("SELECT COUNT(*) FROM forward_oos_events").fetchone()[0], 0)
        self.assertTrue((self.root / "evidence/TEST-OBS.json").exists())
        self.assertEqual(dur.durability_status(self.root)["durability"], "DEGRADED")

    def test_failed_tip_mirror_retries_only_original_bytes_after_recovery(self):
        self.observation()
        self.fail_bundle = True
        fo._append_event(self.root, "RESOLUTION_4H", "TEST-OBS", {"TEST_ONLY": True}, self.now)
        before = self.original_files()
        self.fail_bundle = False
        self.assertTrue(fo.verify_ledger(self.root)["ok"])
        self.assertEqual(self.original_files(), before)
        self.assertTrue(dur.durability_status(self.root)["durable"])
        self.remove_local()
        self.assertTrue(fo.verify_ledger(self.root)["ok"])
        self.assertEqual(self.original_files(), before)

    def test_continued_mirror_failure_blocks_another_append(self):
        self.fail_bundle = True
        self.observation()
        before = self.original_files()
        with self.assertRaisesRegex(RuntimeError, "refusing append"):
            fo._append_event(self.root, "RESOLUTION_4H", "TEST-OBS", {"TEST_ONLY": True}, self.now)
        self.assertEqual(self.original_files(), before)

    def test_append_rechecks_durability_inside_writer_lock(self):
        self.observation()
        before = self.original_files()
        with patch.object(dur, "durability_status", return_value={"durable": False}):
            with self.assertRaisesRegex(RuntimeError, "backup incomplete; refusing append"):
                fo._append_event(self.root, "RESOLUTION_4H", "TEST-OBS", {"TEST_ONLY": True}, self.now)
        self.assertEqual(self.original_files(), before)

    def test_original_local_proofs_can_complete_legacy_tip_backup(self):
        self.observation()
        before = self.original_files()
        with Connection(self.db) as conn:
            conn.raw.execute("DELETE FROM forward_oos_bundles")
        self.assertFalse(dur.durability_status(self.root)["durable"])
        self.assertTrue(fo.verify_ledger(self.root)["ok"])
        self.assertTrue(dur.durability_status(self.root)["durable"])
        self.assertEqual(self.original_files(), before)

    def test_missing_campaign_identity_cannot_use_a_shared_unknown_archive(self):
        (self.root / "FORWARD_OOS_CAMPAIGN_SEAL.json").unlink()
        self.assertFalse(dur.restore_missing(self.root)["ok"])
        self.assertFalse(dur.durability_status(self.root)["durable"])
        with self.assertRaisesRegex(RuntimeError, "refusing append"):
            self.observation()

    def test_corrupt_saved_event_or_head_is_rejected(self):
        self.observation()
        with Connection(self.db) as conn:
            conn.raw.execute("UPDATE forward_oos_bundles SET head_json=?", (b"{}",))
        self.remove_local()
        self.assertFalse(dur.restore_missing(self.root)["ok"])
        self.assertFalse((self.root / "LEDGER_HEAD.json").exists())
        self.remove_local()
        with Connection(self.db) as conn:
            conn.raw.execute("UPDATE forward_oos_events SET canonical_json=?", (b"{}",))
        self.assertFalse(dur.restore_missing(self.root)["ok"])
        self.assertEqual(list((self.root / "events").glob("*.json")), [])

    def test_repeated_mirror_is_idempotent_and_conflict_is_not_overwritten(self):
        event = self.observation()
        name = next((self.root / "events").glob("*.json")).name
        blob = fo.canonical_bytes(event) + b"\n"
        self.assertTrue(dur.mirror_event(self.root, event, blob, name)["mirrored"])
        with Connection(self.db) as conn:
            self.assertEqual(conn.raw.execute("SELECT COUNT(*) FROM forward_oos_events").fetchone()[0], 1)
            conn.raw.execute("UPDATE forward_oos_events SET canonical_json=?", (b"TEST corrupt",))
        self.assertFalse(dur.mirror_event(self.root, event, blob, name)["mirrored"])
        with Connection(self.db) as conn:
            self.assertEqual(conn.raw.execute("SELECT canonical_json FROM forward_oos_events").fetchone()[0], b"TEST corrupt")

    def test_abstention_embedded_evidence_and_test_fixture_stay_separate(self):
        fo._append_event(self.root, "ABSTENTION_OBSERVATION", "TEST-ABST", {"TEST_ONLY": True}, self.now)
        self.assertTrue(dur.write_test_fixture(self.root, "TEST-PROBE")["ok"])
        self.remove_local()
        self.assertTrue(fo.verify_ledger(self.root)["ok"])
        self.assertEqual(fo.verify_ledger(self.root)["abstention_observations"], 1)
        self.assertEqual(fo.verify_ledger(self.root)["forecast_locks"], 0)
        self.assertEqual(len(list((self.root / "events").glob("*.json"))), 1)
        self.assertEqual(dur.durability_status(self.root)["mirrored_events"], 1)

    def test_fixture_cleanup_cannot_delete_production_flagged_rows(self):
        self.observation()
        self.assertEqual(dur.delete_test_fixture(self.root, "TEST-OBS")["deleted"], 0)
        self.assertTrue(dur.write_test_fixture(self.root, "TEST-PROBE")["ok"])
        self.assertTrue(dur.read_test_fixture(self.root, "TEST-PROBE")["found"])
        result = dur.delete_test_fixture(self.root, "TEST-PROBE")
        self.assertEqual((result["deleted"], result["production_rows_touched"]), (1, 0))
        self.assertFalse(dur.read_test_fixture(self.root, "TEST-PROBE")["found"])
        self.assertTrue(fo.verify_ledger(self.root)["ok"])

    def test_archive_path_escape_and_symlink_are_rejected(self):
        for name in ("../../secret", "00000001_forecast-lock_../../secret.json"):
            with self.assertRaises(ValueError): dur._safe_path(self.root, name)
        outside = self.base / "outside.json"; outside.write_text("TEST")
        (self.root / "evidence").mkdir()
        (self.root / "evidence/TEST.json").symlink_to(outside)
        with self.assertRaises(ValueError): dur._safe_path(self.root, "evidence/TEST.json", evidence=True)

    def test_database_failure_does_not_claim_empty_healthy_ledger(self):
        with patch.object(dur, "_connect", side_effect=RuntimeError("SECRET_TEST_DSN")):
            result = fo.verify_ledger(self.root)
            self.assertFalse(result["ok"])
            self.assertNotIn("SECRET_TEST_DSN", json.dumps(result))


class TruthReporting(unittest.TestCase):
    def test_healthy_feed_cannot_hide_failed_campaign_on_dashboard(self):
        # Exercise the actual dashboard handler with an explicitly isolated
        # healthy feed fixture. This is a unit fixture, not live provider E2E.
        from fastapi import FastAPI
        from fia_final_cockpit import api
        app = FastAPI()
        with tempfile.TemporaryDirectory(prefix="fia_TEST_dashboard_") as directory:
            api.install_final_cockpit_routes(app, None, None, backend_root=directory)
            endpoint = next(route.endpoint for route in app.routes
                            if getattr(route, "path", None) == "/api/final/dashboard")
            base = {"live": {"snapshot": {"status": "LIVE"}, "forecast": {"status": "LIVE"}}}
            truth = {"provider_overall": "LIVE", "critical_missing": [], "stale_sources": []}
            for campaign in ({}, {"operational_ok": False, "status": "DEGRADED"},
                             {"operational_ok": True, "status": "READY"}):
                with self.subTest(campaign=campaign), \
                     patch("fia.dashboard_api.build_dashboard_payload", new=AsyncMock(return_value=copy.deepcopy(base))), \
                     patch.object(api, "data_truth_overlay", return_value=truth), \
                     patch.object(api, "whole_system_overlay", return_value={}), \
                     patch.object(api, "phase25_status", return_value={}), \
                     patch.object(api, "brain_status", return_value={}), \
                     patch.object(mon, "build_campaign_status", return_value=campaign):
                    result = asyncio.run(endpoint())
                cockpit = result["final_cockpit"]
                ready = campaign.get("operational_ok") is True
                self.assertEqual(cockpit["truth_ready"], ready)
                self.assertEqual(cockpit["status"], "LIVE" if ready else "DEGRADED")
                self.assertEqual(cockpit["system_status"], "READY" if ready else "DEGRADED")
                self.assertTrue(cockpit["data_truth_ready"])
                self.assertEqual(cockpit["data_status"], "LIVE")
                self.assertEqual(result["live"], base["live"])

    def test_partial_calendar_cannot_report_low(self):
        for macro, earnings, expected in ((None, False, "UNKNOWN"), (False, None, "UNKNOWN"),
                                          (None, None, "UNKNOWN"), (False, False, "LOW"),
                                          (True, None, "HIGH"), (None, True, "HIGH"),
                                          ("false", False, "UNKNOWN")):
            with self.subTest(macro=macro, earnings=earnings):
                result = _catalyst_risk({}, {"data": {"macro_high_impact": macro, "earnings_catalyst_risk": earnings}})
                self.assertEqual(result["level"], expected)
                self.assertEqual(result["known"], expected != "UNKNOWN")

    def test_real_fallback_flags_reach_summary(self):
        async def no_network(symbol): return None
        data = {"provider_quotes_available": 1, "provider_candle_evidence": "available",
                "nq_structure_source": "yahoo_chart_fallback",
                "liquidity_evidence_available": True,
                "liquidity_evidence": {"is_proxy": True, "source_quality": "CONTINUOUS_FALLBACK"},
                "nq_liquidity": {"source": "Yahoo NQ=F fallback", "source_quality": "CONTINUOUS_FALLBACK"}}
        with patch.object(providers, "yahoo_observation", side_effect=no_network):
            result = asyncio.run(providers.enrich_provider_reliability(object(), data))
        self.assertTrue(result["source_health"]["liquidity"]["fallback"])
        self.assertTrue(result["source_health"]["liquidity"]["is_proxy"])
        self.assertEqual(result["source_health"]["candles"]["source"], "yahoo_chart_fallback")
        self.assertTrue({"liquidity", "candles"}.issubset(result["provider_health"]["fallback_active"]))

    def status(self, *, valid=True, count=1, resolved8=True):
        row = {"locked_at_utc": "2026-09-09T17:00:00+00:00",
               "4h": {"resolved_at_utc": "2026-09-09T21:00:00+00:00"},
               "8h": {"resolved_at_utc": "2026-09-10T01:00:00+00:00"} if resolved8 else None}
        with patch.object(mon, "verify_ledger", return_value={"ok": valid, "events": count * 3, "abstention_observations": 2}), \
                patch.object(mon, "forward_report", return_value={"ok": valid, "campaign_seal": {"ok": True}}), \
                patch.object(mon, "records", return_value=[copy.deepcopy(row) for _ in range(count)]), \
                patch.object(mon, "durability_status", return_value={"durable": True}), \
                patch.dict(os.environ, {"FIA_FORWARD_OOS_ENABLED": "1"}):
            return mon.build_campaign_status(Path("TEST_ONLY"))

    def test_campaign_uses_actual_resolution_keys_and_lock_timestamp(self):
        result = self.status()
        self.assertEqual((result["resolved_4h_n"], result["resolved_8h_n"]), (1, 1))
        self.assertEqual(result["last_lock_utc"], "2026-09-09T17:00:00+00:00")
        self.assertEqual(result["last_resolution_utc"], "2026-09-10T01:00:00+00:00")
        self.assertEqual((result["directional_n"], result["abstention_n"], result["forward_oos_n"]), (1, 2, 3))

    def test_invalid_records_never_count_as_verified_evidence(self):
        result = self.status(valid=False, count=30)
        self.assertFalse(result["ok"])
        self.assertFalse(result["operational_ok"])
        self.assertFalse(result["metrics_available"])
        self.assertEqual(result["directional_n"], 30)
        self.assertEqual(result["verified_directional_n"], 0)

    def test_milestone_needs_resolved_observations_in_both_horizons(self):
        self.assertFalse(self.status(count=1)["metrics_available"])
        self.assertFalse(self.status(count=30, resolved8=False)["metrics_available"])
        self.assertTrue(self.status(count=30)["metrics_available"])

    def test_report_uses_requested_seal_and_withholds_metrics_for_invalid_seal_or_versions(self):
        for seal_ok, fingerprints, stage in ((False, ["TEST_A"], "BLOCKED_CAMPAIGN_SEAL"),
                                            (True, ["TEST_A", "TEST_B"], "BLOCKED_MIXED_MODEL_VERSIONS")):
            with self.subTest(stage=stage), \
                    patch.object(fo, "records", return_value=[{"model_fingerprint": {"digest": v}} for v in fingerprints]), \
                    patch.object(fo, "verify_campaign_seal", return_value={"ok": seal_ok}) as seal:
                result = fo.forward_report(Path("TEST_ONLY"), audit={"ok": True})
                seal.assert_called_once_with(Path("TEST_ONLY/FORWARD_OOS_CAMPAIGN_SEAL.json"))
                self.assertFalse(result["ok"])
                self.assertEqual(result["stage"], stage)
                self.assertEqual(result["base_fia"]["4h"]["n"], 0)
                self.assertEqual(result["promotion"]["verdict"], "NO_PROMOTION")


if __name__ == "__main__": unittest.main()
