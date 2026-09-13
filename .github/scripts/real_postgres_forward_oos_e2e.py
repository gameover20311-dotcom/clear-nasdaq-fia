#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import importlib
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / 'backend'
sys.path.insert(0, str(BACKEND))

from fia import forward_oos_durable as durable


def write_root(base: Path, campaign: str, *, forecast_id: str = 'F1', seq: int = 1,
               bad_evidence_hash: bool = False, head_hash: str | None = None):
    root = base / campaign
    (root / 'events').mkdir(parents=True)
    (root / 'evidence').mkdir(parents=True)
    (root / 'FORWARD_OOS_CAMPAIGN_SEAL.json').write_text(
        json.dumps({'campaign_id': campaign}, sort_keys=True), encoding='utf-8')
    evidence_blob = json.dumps({'campaign': campaign, 'forecast_id': forecast_id,
                                'locked': True}, sort_keys=True, separators=(',', ':')).encode()
    evidence_rel = f'evidence/{forecast_id}.json'
    (root / evidence_rel).write_bytes(evidence_blob)
    digest = hashlib.sha256(evidence_blob).hexdigest()
    referenced_digest = ('0' * 64) if bad_evidence_hash else digest
    event = {
        'seq': seq,
        'event_type': 'FORECAST_LOCK',
        'forecast_id': forecast_id,
        'created_at_utc': '2026-09-14T00:00:00+00:00',
        'prev_event_hash': '0' * 64,
        'payload': {'evidence': {'path': evidence_rel, 'sha256': referenced_digest}},
    }
    preimage = json.dumps(event, sort_keys=True, separators=(',', ':')).encode()
    event_hash = hashlib.sha256(preimage).hexdigest()
    event['event_hash'] = event_hash
    canonical = json.dumps(event, sort_keys=True, separators=(',', ':')).encode()
    filename = f'20260914_forecast-lock_{forecast_id}.json'
    (root / 'events' / filename).write_bytes(canonical)
    head = {'events': seq, 'head_event_hash': head_hash or event_hash}
    (root / 'LEDGER_HEAD.json').write_text(
        json.dumps(head, sort_keys=True, separators=(',', ':')), encoding='utf-8')
    return root, event, canonical, filename, evidence_blob, digest, event_hash


def scalar(sql: str, params=()):
    with durable._connect() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            row = cur.fetchone()
            if not row:
                return None
            return next(iter(row.values()))


def cleanup_campaign(cid: str):
    with durable._connect() as conn:
        with conn.cursor() as cur:
            # E2E campaigns only. This never targets production campaign IDs.
            cur.execute('DELETE FROM forward_oos_ledger_heads WHERE campaign_id=%s', (cid,))
            cur.execute('DELETE FROM forward_oos_evidence WHERE campaign_id=%s', (cid,))
            cur.execute('DELETE FROM forward_oos_events WHERE campaign_id=%s', (cid,))
        conn.commit()


def main():
    assert os.getenv('DATABASE_URL'), 'DATABASE_URL required'
    assert durable.enabled(), 'durable Postgres adapter not enabled'
    campaigns = ['E2E-COMMIT', 'E2E-ROLLBACK', 'E2E-PARTIAL', 'E2E-BAD-EVIDENCE', 'E2E-HEAD']
    for cid in campaigns:
        cleanup_campaign(cid)

    with tempfile.TemporaryDirectory() as td:
        base = Path(td)

        # 1) Real project transaction commit + exact event/evidence/head bundle.
        root, event, canonical, filename, evidence_blob, digest, event_hash = write_root(base, 'E2E-COMMIT')
        result = durable.mirror_event(root, event, canonical, filename)
        assert result.get('mirrored') is True, result
        assert scalar('SELECT count(*) AS n FROM forward_oos_events WHERE campaign_id=%s AND is_test=FALSE', ('E2E-COMMIT',)) == 1
        assert scalar('SELECT count(*) AS n FROM forward_oos_evidence WHERE campaign_id=%s', ('E2E-COMMIT',)) == 1
        assert scalar('SELECT count(*) AS n FROM forward_oos_ledger_heads WHERE campaign_id=%s', ('E2E-COMMIT',)) == 1
        print('PASS commit_exact_bundle')

        # 2) Real rollback.
        with durable._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("INSERT INTO forward_oos_events (campaign_id,seq,event_type,forecast_id,created_at_utc,prev_event_hash,event_hash,file_name,canonical_json,is_test) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,TRUE)",
                            ('E2E-ROLLBACK', -1, 'TEST_ROLLBACK', 'RB', '', ' ', 'RB', 'TEST_RB.json', b'rollback'))
            conn.rollback()
        assert scalar('SELECT count(*) AS n FROM forward_oos_events WHERE campaign_id=%s', ('E2E-ROLLBACK',)) == 0
        print('PASS rollback')

        # 3) Duplicate sequence with different immutable bytes MUST fail closed.
        altered = dict(event)
        altered['event_hash'] = 'f' * 64
        altered['created_at_utc'] = '2026-09-14T00:00:01+00:00'
        altered_canonical = json.dumps(altered, sort_keys=True, separators=(',', ':')).encode()
        (root / 'LEDGER_HEAD.json').write_text(json.dumps({'events': 1, 'head_event_hash': altered['event_hash']}, sort_keys=True, separators=(',', ':')))
        conflict = durable.mirror_event(root, altered, altered_canonical, filename)
        assert conflict.get('mirrored') is False and conflict.get('error_type') == 'RuntimeError', conflict
        with durable._connect() as conn:
            with conn.cursor() as cur:
                cur.execute('SELECT canonical_json,event_hash FROM forward_oos_events WHERE campaign_id=%s AND seq=1', ('E2E-COMMIT',))
                row = cur.fetchone()
        assert bytes(row['canonical_json']) == canonical and row['event_hash'] == event_hash
        print('PASS duplicate_conflict_fail_closed')

        # Restore original head for later recovery.
        (root / 'LEDGER_HEAD.json').write_text(json.dumps({'events': 1, 'head_event_hash': event_hash}, sort_keys=True, separators=(',', ':')))

        # 4) Simulated interrupted/partial bundle: DB trigger aborts head insert.
        partial_root, partial_event, partial_canonical, partial_filename, *_ = write_root(base, 'E2E-PARTIAL')
        with durable._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("CREATE OR REPLACE FUNCTION e2e_abort_head() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN IF NEW.campaign_id='E2E-PARTIAL' THEN RAISE EXCEPTION 'E2E forced partial failure'; END IF; RETURN NEW; END $$")
                cur.execute('DROP TRIGGER IF EXISTS e2e_abort_head_trigger ON forward_oos_ledger_heads')
                cur.execute('CREATE TRIGGER e2e_abort_head_trigger BEFORE INSERT ON forward_oos_ledger_heads FOR EACH ROW EXECUTE FUNCTION e2e_abort_head()')
            conn.commit()
        partial = durable.mirror_event(partial_root, partial_event, partial_canonical, partial_filename)
        assert partial.get('mirrored') is False, partial
        assert scalar('SELECT count(*) AS n FROM forward_oos_events WHERE campaign_id=%s', ('E2E-PARTIAL',)) == 0
        assert scalar('SELECT count(*) AS n FROM forward_oos_evidence WHERE campaign_id=%s', ('E2E-PARTIAL',)) == 0
        with durable._connect() as conn:
            with conn.cursor() as cur:
                cur.execute('DROP TRIGGER IF EXISTS e2e_abort_head_trigger ON forward_oos_ledger_heads')
                cur.execute('DROP FUNCTION IF EXISTS e2e_abort_head()')
            conn.commit()
        print('PASS partial_failure_atomic_rollback')

        # 5) Exact recovery after local proof deletion.
        event_path = root / 'events' / filename
        evidence_path = root / f'evidence/{event["forecast_id"]}.json'
        head_path = root / 'LEDGER_HEAD.json'
        expected_head = head_path.read_bytes()
        event_path.unlink(); evidence_path.unlink(); head_path.unlink()
        restored = durable.restore_missing(root)
        assert restored.get('events_restored') == 1 and restored.get('evidence_restored') == 1 and restored.get('ledger_head_restored') == 1, restored
        assert event_path.read_bytes() == canonical
        assert evidence_path.read_bytes() == evidence_blob
        assert head_path.read_bytes() == expected_head
        print('PASS recovery_after_local_proof_deletion')

        # 6) Recovery after process/module restart.
        event_path.chmod(0o644); evidence_path.chmod(0o644); head_path.chmod(0o644)
        event_path.unlink(); evidence_path.unlink(); head_path.unlink()
        reloaded = importlib.reload(durable)
        assert reloaded.enabled()
        restarted = reloaded.restore_missing(root)
        assert restarted.get('restored') == 3, restarted
        assert event_path.read_bytes() == canonical and evidence_path.read_bytes() == evidence_blob
        print('PASS recovery_after_restart')

        # 7) Evidence/hash mismatch refused and no DB row leaks through.
        bad_root, bad_event, bad_canonical, bad_filename, *_ = write_root(base, 'E2E-BAD-EVIDENCE', bad_evidence_hash=True)
        bad = reloaded.mirror_event(bad_root, bad_event, bad_canonical, bad_filename)
        assert bad.get('mirrored') is False, bad
        assert scalar('SELECT count(*) AS n FROM forward_oos_events WHERE campaign_id=%s', ('E2E-BAD-EVIDENCE',)) == 0
        print('PASS evidence_hash_mismatch_refused')

        # 8) Existing head anchor at same count cannot be silently replaced.
        head_root, head_event, head_canonical, head_filename, *_ = write_root(base, 'E2E-HEAD')
        good = reloaded.mirror_event(head_root, head_event, head_canonical, head_filename)
        assert good.get('mirrored') is True, good
        (head_root / 'LEDGER_HEAD.json').chmod(0o644)
        (head_root / 'LEDGER_HEAD.json').write_text(json.dumps({'events': 1, 'head_event_hash': 'a' * 64}, sort_keys=True, separators=(',', ':')))
        head_conflict = reloaded.mirror_event(head_root, head_event, head_canonical, head_filename)
        assert head_conflict.get('mirrored') is False, head_conflict
        print('PASS ledger_head_mismatch_refused')

        # 9) Application delete path cannot delete a production observation.
        deleted = reloaded.delete_test_fixture(root, event['forecast_id'])
        assert deleted.get('deleted') == 0 and deleted.get('production_rows_touched') == 0, deleted
        assert scalar('SELECT count(*) AS n FROM forward_oos_events WHERE campaign_id=%s AND is_test=FALSE', ('E2E-COMMIT',)) == 1
        print('PASS production_row_delete_refused')

        # 10) A test fixture can be committed/read/deleted, proving intended test-only delete path.
        fixture = reloaded.write_test_fixture(root, 'E2E-TEST-FIXTURE')
        assert fixture.get('ok') is True, fixture
        assert reloaded.read_test_fixture(root, 'E2E-TEST-FIXTURE').get('found') is True
        removed = reloaded.delete_test_fixture(root, 'E2E-TEST-FIXTURE')
        assert removed.get('deleted') == 1 and removed.get('production_rows_touched') == 0, removed
        print('PASS test_fixture_lifecycle')

    for cid in campaigns:
        cleanup_campaign(cid)
    print('REAL_POSTGRES_FORWARD_OOS_E2E=PASS')


if __name__ == '__main__':
    main()
