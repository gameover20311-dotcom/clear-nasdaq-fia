"""V6.8.6 — real disposable Postgres integration for Forward-OOS durability.

This is NOT part of the ordinary offline regression discovery. CI invokes it
explicitly with FIA_TEST_POSTGRES_DSN pointing at a loopback fia_test* database.
It never accepts a production/non-loopback database and every test uses a fresh
schema that is dropped afterwards.
"""
from __future__ import annotations

import asyncio
import os
import tempfile
import unittest
import uuid
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo

from fia import forward_oos as fo, forward_oos_durable as dur


def isolated_dsn() -> str:
    value = str(os.getenv("FIA_TEST_POSTGRES_DSN") or "").strip()
    if not value:
        raise RuntimeError("NOT_TESTED:FIA_TEST_POSTGRES_DSN_REQUIRED")
    info = conninfo_to_dict(value)
    if info.get("host") not in {"127.0.0.1", "localhost"}:
        raise RuntimeError("REFUSING_NON_LOOPBACK_POSTGRES")
    if not str(info.get("dbname") or "").startswith("fia_test"):
        raise RuntimeError("REFUSING_NON_DISPOSABLE_POSTGRES")
    return value


class RealForwardOosPostgres(unittest.TestCase):
    def setUp(self):
        self.base_dsn = isolated_dsn()
        self.schema = "fia_v686_" + uuid.uuid4().hex
        with psycopg.connect(self.base_dsn, autocommit=True) as conn:
            conn.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(self.schema)))
        self.addCleanup(self._drop_schema)

        self.dsn = make_conninfo(self.base_dsn, options="-c search_path=" + self.schema)
        env = patch.dict(os.environ, {"DATABASE_URL": self.dsn})
        env.start()
        self.addCleanup(env.stop)

        temp = tempfile.TemporaryDirectory(prefix="fia_TEST_v686_pg_")
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        (self.root / "FORWARD_OOS_CAMPAIGN_SEAL.json").write_text(
            '{"campaign_id":"TEST_ONLY_V686_POSTGRES"}', encoding="utf-8"
        )
        self.now = datetime(2026, 9, 11, 0, 0, tzinfo=timezone.utc)
        with dur._connect():
            pass

    def _drop_schema(self):
        with psycopg.connect(self.base_dsn, autocommit=True) as conn:
            conn.execute(sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(self.schema)))

    def query(self, statement, params=()):
        with psycopg.connect(self.dsn) as conn:
            cursor = conn.execute(statement, params)
            return cursor.fetchall() if cursor.description else []

    def observation(self):
        meta = fo._write_evidence_once(
            self.root, "TEST_V686_NATIVE", {"TEST_ONLY": True, "sample": [1, 2, 3]}
        )
        return fo._append_event(
            self.root, "FORECAST_LOCK", "TEST_V686_NATIVE", {"evidence": meta}, self.now
        )

    def files(self):
        return {
            str(path.relative_to(self.root)): path.read_bytes()
            for path in self.root.rglob("*.json")
        }

    def erase_local_proofs(self):
        for path in self.root.rglob("*.json"):
            if path.name != "FORWARD_OOS_CAMPAIGN_SEAL.json":
                path.unlink()

    def test_01_schema_initializes_idempotently(self):
        with dur._connect():
            pass
        tables = {row[0] for row in self.query(
            "SELECT table_name FROM information_schema.tables WHERE table_schema=%s",
            (self.schema,),
        )}
        self.assertIn("forward_oos_events", tables)
        self.assertIn("forward_oos_bundles", tables)
        event_cols = dict(self.query(
            "SELECT column_name,data_type FROM information_schema.columns "
            "WHERE table_schema=%s AND table_name='forward_oos_events'",
            (self.schema,),
        ))
        self.assertEqual(event_cols.get("canonical_json"), "bytea")
        self.assertEqual(event_cols.get("is_test"), "boolean")

    def test_02_atomic_bundle_and_exact_byte_restoration(self):
        self.observation()
        fo._append_event(
            self.root, "RESOLUTION_4H", "TEST_V686_NATIVE", {"TEST_ONLY": True}, self.now
        )
        self.assertEqual(self.query("SELECT count(*) FROM forward_oos_events")[0][0], 2)
        self.assertEqual(self.query("SELECT count(*) FROM forward_oos_bundles")[0][0], 2)
        before = self.files()
        self.erase_local_proofs()
        audit = fo.verify_ledger(self.root)
        self.assertTrue(audit["ok"], audit)
        self.assertEqual(self.files(), before)
        status = dur.durability_status(self.root)
        self.assertTrue(status["durable"], status)

    def test_03_real_transaction_failure_rolls_back_and_blocks_next_append(self):
        self.observation()
        self.query(
            "ALTER TABLE forward_oos_bundles ADD CONSTRAINT test_v686_interrupt CHECK (seq <> 2)"
        )
        fo._append_event(
            self.root, "RESOLUTION_4H", "TEST_V686_NATIVE", {"TEST_ONLY": True}, self.now
        )
        local_after_failed_mirror = self.files()
        self.assertEqual(self.query("SELECT count(*) FROM forward_oos_events")[0][0], 1)
        self.assertEqual(self.query("SELECT count(*) FROM forward_oos_bundles")[0][0], 1)
        self.assertFalse(dur.durability_status(self.root)["durable"])
        with self.assertRaisesRegex(RuntimeError, "refusing append"):
            fo._append_event(
                self.root, "RESOLUTION_8H", "TEST_V686_NATIVE", {"TEST_ONLY": True}, self.now
            )
        self.assertEqual(self.files(), local_after_failed_mirror)

        self.query("ALTER TABLE forward_oos_bundles DROP CONSTRAINT test_v686_interrupt")
        audit = fo.verify_ledger(self.root)
        self.assertTrue(audit["ok"], audit)
        self.assertEqual(self.files(), local_after_failed_mirror)
        self.assertEqual(self.query("SELECT count(*) FROM forward_oos_events")[0][0], 2)
        self.assertEqual(self.query("SELECT count(*) FROM forward_oos_bundles")[0][0], 2)

    def test_04_event_only_backup_never_invents_missing_proofs(self):
        self.observation()
        self.query("DELETE FROM forward_oos_bundles")
        self.erase_local_proofs()
        audit = fo.verify_ledger(self.root)
        self.assertFalse(audit["ok"])
        self.assertFalse((self.root / "evidence/TEST_V686_NATIVE.json").exists())
        self.assertFalse((self.root / "LEDGER_HEAD.json").exists())
        self.assertFalse(dur.durability_status(self.root)["durable"])

    def test_05_corrupt_saved_evidence_is_rejected(self):
        self.observation()
        self.query("UPDATE forward_oos_bundles SET evidence_json=%s", (b"TEST corrupt",))
        self.erase_local_proofs()
        self.assertFalse(fo.verify_ledger(self.root)["ok"])
        self.assertFalse((self.root / "evidence/TEST_V686_NATIVE.json").exists())

    def test_06_corrupt_saved_anchor_is_rejected(self):
        self.observation()
        self.query("UPDATE forward_oos_bundles SET head_json=%s", (b"{}",))
        self.erase_local_proofs()
        self.assertFalse(fo.verify_ledger(self.root)["ok"])
        self.assertFalse((self.root / "LEDGER_HEAD.json").exists())

    def test_07_corrupt_saved_event_is_rejected(self):
        self.observation()
        self.query("UPDATE forward_oos_events SET canonical_json=%s", (b"{}",))
        self.erase_local_proofs()
        self.assertFalse(fo.verify_ledger(self.root)["ok"])
        self.assertEqual(list((self.root / "events").glob("*.json")), [])

    def test_08_local_corruption_cannot_report_durable_or_be_overwritten(self):
        self.observation()
        evidence = self.root / "evidence/TEST_V686_NATIVE.json"
        evidence.chmod(0o644)
        evidence.write_bytes(b"TEST local conflict")
        self.assertFalse(fo.verify_ledger(self.root)["ok"])
        self.assertFalse(dur.durability_status(self.root)["durable"])
        self.assertEqual(evidence.read_bytes(), b"TEST local conflict")

    def test_09_test_fixture_isolation_cannot_delete_production_event(self):
        event = self.observation()
        event_path = next((self.root / "events").glob("*.json"))
        before = event_path.read_bytes()
        self.assertTrue(dur.mirror_event(self.root, event, before, event_path.name)["mirrored"])
        self.assertEqual(self.query("SELECT count(*) FROM forward_oos_events WHERE is_test=FALSE")[0][0], 1)

        marker = "TEST_V686_PROBE"
        created = dur.write_test_fixture(self.root, marker)
        self.assertTrue(created["ok"], created)
        self.assertTrue(dur.read_test_fixture(self.root, marker)["found"])
        deleted = dur.delete_test_fixture(self.root, marker)
        self.assertEqual(deleted["deleted"], 1)
        self.assertEqual(deleted["production_rows_touched"], 0)
        self.assertEqual(self.query("SELECT count(*) FROM forward_oos_events WHERE is_test=FALSE")[0][0], 1)
        self.assertEqual(event_path.read_bytes(), before)

    def test_10_checkpoint_call_never_backfills_missed_history(self):
        before = self.query("SELECT count(*) FROM forward_oos_events")[0][0]
        result = asyncio.run(fo.lock_live_forecast({}, {}, self.root, now=self.now))
        self.assertFalse(result.get("created", False), result)
        self.assertFalse(fo.checkpoint_state(self.now)["missed_backfill_allowed"])
        self.assertEqual(self.query("SELECT count(*) FROM forward_oos_events")[0][0], before)


if __name__ == "__main__":
    unittest.main(verbosity=2)
