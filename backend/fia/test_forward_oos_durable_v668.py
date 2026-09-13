"""V6.6.8 Forward-OOS durable mirror: exact-byte recovery and safety contract.

This test intentionally checks the CURRENT proof-complete design rather than the
old implementation shape.  The durable store is a copy of the authoritative
append-only file ledger plus the original evidence and head anchor.  Recovery
may fill any MISSING proof, but it must never overwrite or synthesize one.
"""
from __future__ import annotations

import inspect
import json
import os
import stat
import sys
import tempfile
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from fia import forward_oos, forward_oos_durable as dur  # noqa: E402

FAILURES = []


def check(name, cond, detail=""):
    if cond:
        print("  PASS  %s" % name)
    else:
        print("  FAIL  %s   %s" % (name, detail))
        FAILURES.append(name)


print("\n[A] IT NEVER CLAIMS DURABILITY IT DOES NOT HAVE")
st = dur.durability_status(forward_oos.DEFAULT_ROOT)
if not dur._database_url():
    check("[A1] no DATABASE_URL -> EPHEMERAL",
          st["durability"] == "EPHEMERAL" and st["survives_redeploy"] is False,
          str(st))
    check("[A2] the reason is stated", "redeploy" in st["detail"].lower(), st["detail"])
else:
    check("[A1] DATABASE_URL present -> a definite verdict is returned",
          st["durability"] in ("DURABLE", "DEGRADED"), str(st))

print("\n[B] DATABASE STORAGE IS APPEND-ONLY FOR PRODUCTION")
src = Path(dur.__file__).read_text(encoding="utf-8")
upper = src.upper()
check("[B1] no UPDATE statement anywhere", "UPDATE FORWARD_OOS_EVENTS" not in upper)
check("[B2] the only DELETE is guarded by is_test",
      upper.count("DELETE FROM") == 1 and "IS_TEST = TRUE AND FORECAST_ID" in upper,
      "delete count=%d" % upper.count("DELETE FROM"))
check("[B3] event inserts are idempotent, not overwriting",
      "ON CONFLICT (campaign_id, seq) DO NOTHING" in src)
check("[B4] event hash is unique per campaign",
      "idx_foos_event_hash" in src and "UNIQUE" in upper)
check("[B5] event and proof bundle share one connection/transaction",
      "forward_oos_events" in inspect.getsource(dur.mirror_event)
      and "forward_oos_bundles" in inspect.getsource(dur.mirror_event)
      and inspect.getsource(dur.mirror_event).count("conn.commit()") == 1)

print("\n[C] EXACT-BYTE RESTORE CANNOT CLOBBER LOCAL PROOFS")
install_src = inspect.getsource(dur._install_missing)
check("[C1] existing bytes are compared before any write",
      "if path.exists():" in install_src and "path.read_bytes() != blob" in install_src)
check("[C2] missing files use O_EXCL", "O_EXCL" in install_src)
check("[C3] restored files are created read-only", "0o444" in install_src)

with tempfile.TemporaryDirectory(prefix="foos_exact_restore_") as td:
    root = Path(td)
    target = root / "events" / "00000001_forecast-lock_TEST.json"
    original = b'{"exact":"saved-bytes"}\n'
    first = dur._install_missing(target, original)
    before = target.read_bytes()
    mode = stat.S_IMODE(target.stat().st_mode)
    second = dur._install_missing(target, original)
    conflict_raised = False
    try:
        dur._install_missing(target, b'{"different":true}\n')
    except ValueError:
        conflict_raised = True
    check("[C4] missing file is installed exactly once",
          first == 1 and second == 0 and target.read_bytes() == original,
          "first=%r second=%r" % (first, second))
    check("[C5] restored bytes are exact", before == original)
    check("[C6] conflicting bytes are refused and original survives",
          conflict_raised and target.read_bytes() == original)
    check("[C7] restored owner-write bit is absent", not bool(mode & stat.S_IWUSR), oct(mode))

restore_src = inspect.getsource(dur.restore_missing)
archive_src = inspect.getsource(dur._archive)
safe_src = inspect.getsource(dur._safe_path)
check("[C8] restore validates the saved archive before installing",
      "_validate_archive" in restore_src)
check("[C9] restore delegates all proof installation to exact-byte helper",
      "_install_missing" in restore_src)
check("[C10] conflicts are reported, never overwritten",
      "local_file_conflict" in restore_src)
check("[C11] production archive explicitly excludes test rows",
      "is_test = FALSE" in archive_src)
check("[C12] ledger paths are allowlisted by regex",
      "_LEDGER_FILE_RE" in safe_src and "fullmatch" in safe_src)

print("\n[D] MIRROR STORES THE ORIGINAL EVENT BYTES; IT DOES NOT REBUILD THEM")
msrc = inspect.getsource(dur.mirror_event)
check("[D1] caller bytes must decode to the supplied event",
      "json.loads(canonical) != event" in msrc)
check("[D2] caller bytes must equal the authoritative local event bytes",
      "read_bytes() != canonical" in msrc)
check("[D3] the exact canonical blob is passed to the event INSERT",
      "file_name, canonical, bool(is_test)" in msrc)
check("[D4] a conflicting immutable DB row is rejected",
      "IMMUTABLE_EVENT_CONFLICT" in msrc)
check("[D5] a conflicting immutable proof bundle is rejected",
      "IMMUTABLE_BUNDLE_CONFLICT" in msrc)
check("[D6] mirror failure is loud and does not format secrets",
      "MIRROR_FAILED" in msrc and "type(exc).__name__" in msrc
      and "str(exc)" not in msrc and "{exc}" not in msrc)

print("\n[E] TEST FIXTURES ARE ISOLATED FROM THE SCIENTIFIC RECORD")
wsrc = inspect.getsource(dur.write_test_fixture)
check("[E1] fixtures are flagged is_test TRUE", "TRUE)" in wsrc and "is_test" in wsrc)
check("[E2] fixtures use a distinct event type", "TEST_DURABILITY_PROBE" in wsrc)
check("[E3] fixtures take a negative seq", "- 1" in wsrc and "MIN(seq)" in wsrc)
dsrc = inspect.getsource(dur.delete_test_fixture)
check("[E4] delete refuses production rows", "is_test = TRUE" in dsrc)
check("[E5] delete reports no production rows touched", "production_rows_touched" in dsrc)

print("\n[F] SECRET MATERIAL DOES NOT ESCAPE STATUS/ERROR PAYLOADS")
for fn in (dur.durability_status, dur.mirror_event, dur.restore_missing,
           dur.write_test_fixture, dur.read_test_fixture, dur.delete_test_fixture):
    body = inspect.getsource(fn)
    leaks = ("str(exc)" in body) or ("{exc}" in body) or ("% exc" in body)
    check("[F] %-22s never formats the raw exception" % fn.__name__, not leaks)
blob = json.dumps(dur.durability_status(forward_oos.DEFAULT_ROOT))
check("[F2] status payload contains no connection string",
      "postgresql://" not in blob, blob[:160])

print("\n[G] FILE LEDGER HASH-CHAIN PROTECTIONS REMAIN IN PLACE")
asrc = inspect.getsource(forward_oos._append_event)
check("[G1] append verifies ledger before writing",
      "verify_ledger(root)" in asrc and "refusing append" in asrc)
check("[G2] event hash is computed over unsigned event",
      'event["event_hash"] = sha256_bytes(canonical_bytes(unsigned))' in asrc)
check("[G3] duplicate events are refused", "Immutable event already exists" in asrc)
check("[G4] event file uses O_EXCL and read-only mode", "O_EXCL" in asrc and "0o444" in asrc)
check("[G5] append is blocked when durable backup is incomplete",
      "Forward OOS backup incomplete; refusing append" in asrc)

print("\n[H] RECOVERY FILLS MISSING PROOFS; IT DOES NOT REQUIRE AN EMPTY ROOT")
wrapper_src = inspect.getsource(forward_oos._restore_from_durable_if_empty)
check("[H1] historical wrapper delegates to restore_missing",
      "restore_missing(root)" in wrapper_src)
check("[H2] wrapper no longer requires an empty events directory",
      "any(events_dir.glob" not in wrapper_src)
check("[H3] saved event filename allowlist rejects a test fixture",
      dur._LEDGER_FILE_RE.fullmatch("00000001_forecast-lock_NQ-FOOS-20260903.json") is not None
      and dur._LEDGER_FILE_RE.fullmatch("TEST_durability-probe-abc123.json") is None)
check("[H4] evidence path has an independent allowlist",
      dur._EVIDENCE_FILE_RE.fullmatch("evidence/NQ-FOOS-20260903.json") is not None
      and dur._EVIDENCE_FILE_RE.fullmatch("../../etc/passwd") is None)

print("\n" + "=" * 66)
if FAILURES:
    print("FAILED %d check(s):" % len(FAILURES))
    for failure in FAILURES:
        print("   -", failure)
    raise SystemExit(1)
print("ALL V6.6.8 FORWARD-OOS DURABILITY CONTRACT CHECKS PASSED")
