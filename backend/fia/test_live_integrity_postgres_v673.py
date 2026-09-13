"""Native Postgres integration. Requires a disposable loopback fia_test* DB.

No SQLite adapter, mocked database connection, production DSN or production
writes. Every test creates and removes its own schema in the disposable DB.
"""
from __future__ import annotations

import asyncio
import json
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


def isolated_dsn():
    value = os.getenv("FIA_TEST_POSTGRES_DSN", "")
    if not value:
        raise RuntimeError("NOT TESTED: FIA_TEST_POSTGRES_DSN is required")
    info = conninfo_to_dict(value)
    if info.get("host") not in {"127.0.0.1", "localhost"} or not info.get("dbname", "").startswith("fia_test"):
        raise RuntimeError("Refusing non-disposable/non-loopback database")
    return value


class NativePostgres(unittest.TestCase):
    def setUp(self):
        self.base_dsn = isolated_dsn()
        self.schema = "fia_pr6_test_" + uuid.uuid4().hex
        with psycopg.connect(self.base_dsn, autocommit=True) as conn:
            conn.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(self.schema)))
        self.addCleanup(self.drop_schema)
        self.dsn = make_conninfo(self.base_dsn, options="-c search_path=" + self.schema)
        env = patch.dict(os.environ, {"DATABASE_URL": self.dsn})
        env.start(); self.addCleanup(env.stop)
        tmp = tempfile.TemporaryDirectory(prefix="fia_TEST_native_")
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        (self.root / "FORWARD_OOS_CAMPAIGN_SEAL.json").write_text('{"campaign_id":"TEST_ONLY_NATIVE"}')
        self.now = datetime(2026, 9, 11, 0, 0, tzinfo=timezone.utc)
        with dur._connect():
            pass

    def drop_schema(self):
        with psycopg.connect(self.base_dsn, autocommit=True) as conn:
            conn.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(self.schema)))

    def query(self, statement, params=()):
        with psycopg.connect(self.dsn) as conn:
            cursor = conn.execute(statement, params)
            return cursor.fetchall() if cursor.description else []

    def observation(self):
        meta = fo._write_evidence_once(self.root, "TEST_NATIVE", {"TEST_ONLY": True, "sample": [1, 2]})
        return fo._append_event(self.root, "FORECAST_LOCK", "TEST_NATIVE", {"evidence": meta}, self.now)

    def files(self):
        return {str(p.relative_to(self.root)): p.read_bytes() for p in self.root.rglob("*.json")}

    def erase_local_copy(self):
        for p in self.root.rglob("*.json"):
            if p.name != "FORWARD_OOS_CAMPAIGN_SEAL.json":
                p.unlink()

    def test_schema_compatibility_and_idempotent_initialization(self):
        with dur._connect():
            pass
        columns = self.query("SELECT column_name,data_type FROM information_schema.columns WHERE table_schema=%s AND table_name='forward_oos_events' ORDER BY ordinal_position", (self.schema,))
        expected = [("campaign_id", "text"), ("seq", "bigint"), ("event_type", "text"),
                    ("forecast_id", "text"), ("created_at_utc", "text"), ("prev_event_hash", "text"),
                    ("event_hash", "text"), ("file_name", "text"), ("canonical_json", "bytea"),
                    ("is_test", "boolean"), ("mirrored_at", "timestamp with time zone")]
        self.assertEqual(columns, expected)
        self.assertTrue(self.query("SHOW server_version")[0][0].startswith("18."))

    def test_atomic_bundle_and_exact_byte_restoration(self):
        self.observation()
        fo._append_event(self.root, "RESOLUTION_4H", "TEST_NATIVE", {"TEST_ONLY": True}, self.now)
        self.assertEqual(self.query("SELECT count(*) FROM forward_oos_events")[0][0], 2)
        self.assertEqual(self.query("SELECT count(*) FROM forward_oos_bundles")[0][0], 2)
        before = self.files()
        self.erase_local_copy()
        self.assertTrue(fo.verify_ledger(self.root)["ok"])
        self.assertEqual(self.files(), before)
        self.assertTrue(dur.durability_status(self.root)["durable"])

    def test_actual_constraint_failure_rolls_back_blocks_append_and_retries(self):
        self.observation()
        self.query("ALTER TABLE forward_oos_bundles ADD CONSTRAINT test_interruption CHECK (seq <> 2)")
        fo._append_event(self.root, "RESOLUTION_4H", "TEST_NATIVE", {"TEST_ONLY": True}, self.now)
        before = self.files()
        self.assertEqual(self.query("SELECT count(*) FROM forward_oos_events")[0][0], 1)
        self.assertEqual(self.query("SELECT count(*) FROM forward_oos_bundles")[0][0], 1)
        self.assertFalse(dur.durability_status(self.root)["durable"])
        with self.assertRaisesRegex(RuntimeError, "refusing append"):
            fo._append_event(self.root, "RESOLUTION_8H", "TEST_NATIVE", {"TEST_ONLY": True}, self.now)
        self.assertEqual(self.files(), before)
        self.query("ALTER TABLE forward_oos_bundles DROP CONSTRAINT test_interruption")
        self.assertTrue(fo.verify_ledger(self.root)["ok"])
        self.assertEqual(self.files(), before)
        self.assertEqual(self.query("SELECT count(*) FROM forward_oos_events")[0][0], 2)

    def test_legacy_event_only_backup_never_invents_proofs(self):
        self.observation()
        self.query("DELETE FROM forward_oos_bundles")
        self.erase_local_copy()
        self.assertFalse(fo.verify_ledger(self.root)["ok"])
        self.assertFalse((self.root / "evidence/TEST_NATIVE.json").exists())
        self.assertFalse((self.root / "LEDGER_HEAD.json").exists())
        self.assertFalse(dur.durability_status(self.root)["durable"])

    def test_corrupt_saved_evidence_is_rejected(self):
        self.observation()
        self.query("UPDATE forward_oos_bundles SET evidence_json=%s", (b"TEST corrupt",))
        self.erase_local_copy()
        self.assertFalse(fo.verify_ledger(self.root)["ok"])
        self.assertFalse((self.root / "evidence/TEST_NATIVE.json").exists())

    def test_corrupt_saved_anchor_is_rejected(self):
        self.observation()
        self.query("UPDATE forward_oos_bundles SET head_json=%s", (b"{}",))
        self.erase_local_copy()
        self.assertFalse(fo.verify_ledger(self.root)["ok"])
        self.assertFalse((self.root / "LEDGER_HEAD.json").exists())

    def test_corrupt_saved_event_is_rejected(self):
        self.observation()
        self.query("UPDATE forward_oos_events SET canonical_json=%s", (b"{}",))
        self.erase_local_copy()
        self.assertFalse(fo.verify_ledger(self.root)["ok"])
        self.assertEqual(list((self.root / "events").glob("*.json")), [])

    def test_local_corruption_cannot_report_durable(self):
        self.observation()
        p = self.root / "evidence/TEST_NATIVE.json"
        p.chmod(0o644); p.write_bytes(b"TEST corrupt")
        self.assertFalse(fo.verify_ledger(self.root)["ok"])
        self.assertFalse(dur.durability_status(self.root)["durable"])
        self.assertEqual(p.read_bytes(), b"TEST corrupt")

    def test_no_duplicate_mutation_and_fixture_isolation(self):
        event = self.observation()
        path = next((self.root / "events").glob("*.json"))
        before = path.read_bytes()
        self.assertTrue(dur.mirror_event(self.root, event, before, path.name)["mirrored"])
        self.assertEqual(self.query("SELECT count(*) FROM forward_oos_events")[0][0], 1)
        self.assertEqual(dur.delete_test_fixture(self.root, "TEST_NATIVE")["deleted"], 0)
        self.assertTrue(dur.write_test_fixture(self.root, "TEST_PROBE")["ok"])
        self.assertEqual(dur.durability_status(self.root)["mirrored_events"], 1)
        self.erase_local_copy()
        self.assertTrue(fo.verify_ledger(self.root)["ok"])
        self.assertEqual(len(list((self.root / "events").glob("*.json"))), 1)
        self.assertEqual(dur.delete_test_fixture(self.root, "TEST_PROBE")["deleted"], 1)
        self.query("UPDATE forward_oos_events SET canonical_json=%s", (b"TEST conflicting row",))
        self.assertFalse(dur.mirror_event(self.root, event, before, path.name)["mirrored"])
        self.assertEqual(bytes(self.query("SELECT canonical_json FROM forward_oos_events")[0][0]), b"TEST conflicting row")

    def test_checkpoint_request_does_not_backfill_history(self):
        before = self.query("SELECT count(*) FROM forward_oos_events")[0][0]
        result = asyncio.run(fo.lock_live_forecast({}, {}, self.root, now=self.now))
        self.assertFalse(result.get("created", False))
        self.assertFalse(fo.checkpoint_state(self.now)["missed_backfill_allowed"])
        self.assertEqual(self.query("SELECT count(*) FROM forward_oos_events")[0][0], before)


if __name__ == "__main__":
    unittest.main()
