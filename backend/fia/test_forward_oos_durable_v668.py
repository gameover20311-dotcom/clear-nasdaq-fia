"""V6.6.8 Forward-OOS durable mirror: contract and safety.

WHY THIS EXISTS
---------------
Observed on 2026-09-07: the 13:00 ET checkpoint fired, the system declined to
call a direction, and recorded its first live abstention observation
(events: 1, forecast_locks: 0). A routine redeploy followed and the ledger came
back events: 0. A genuine scientific record was created and destroyed inside one
session, which makes any 30/50/100 programme impossible at this deploy cadence.

This suite pins the mirror's SAFETY properties. The append-only file ledger and
its hash chain remain authoritative; the mirror is a durable copy.
"""
from __future__ import annotations

import inspect
import json
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from fia import forward_oos, forward_oos_durable as dur              # noqa: E402

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
    check("[A] no DATABASE_URL -> EPHEMERAL",
          st["durability"] == "EPHEMERAL" and st["survives_redeploy"] is False, str(st))
    check("[A] the reason is stated", "redeploy" in st["detail"].lower(), st["detail"])
else:
    check("[A] DATABASE_URL present -> a definite verdict is returned",
          st["durability"] in ("DURABLE", "DEGRADED"), str(st))

print("\n[B] THE MIRROR IS APPEND-ONLY FOR PRODUCTION")
src = Path(dur.__file__).read_text()
upper = src.upper()
check("[B1] no UPDATE statement anywhere", "UPDATE FORWARD_OOS_EVENTS" not in upper)
check("[B2] the only DELETE is guarded by is_test",
      upper.count("DELETE FROM") == 1 and "IS_TEST = TRUE AND FORECAST_ID" in upper,
      "delete count=%d" % upper.count("DELETE FROM"))
check("[B3] inserts are idempotent, not overwriting",
      "ON CONFLICT (campaign_id, seq) DO NOTHING" in src)
check("[B4] the event hash is unique per campaign",
      "idx_foos_event_hash" in src and "UNIQUE" in upper)

print("\n[C] RESTORE CANNOT CLOBBER A LIVE LEDGER")
rsrc = inspect.getsource(dur.restore_missing)
check("[C1] an existing file is skipped, never rewritten",
      "if path.exists():" in rsrc and "continue" in rsrc)
check("[C2] files are created exclusively (O_EXCL)", "O_EXCL" in rsrc)
check("[C3] restored files are read-only", "0o444" in rsrc)
check("[C4] the stored bytes are the canonical event, not a re-render",
      "canonical_json" in rsrc)
fsrc = inspect.getsource(forward_oos._restore_from_durable_if_empty)
check("[C5] restore only runs when local storage is empty",
      "any(events_dir.glob" in fsrc)

print("\n[D] NO BACKFILL, NO MUTATION OF PRODUCTION OBSERVATIONS")
asrc = inspect.getsource(forward_oos._append_event)
check("[D1] the mirror runs AFTER the file write and head update",
      asrc.index("_write_head") < asrc.index("mirror_event"))
check("[D2] a mirror failure never removes or alters the file",
      "except Exception as _exc" in asrc and "path.unlink" not in
      asrc[asrc.index("mirror_event"):])
msrc = inspect.getsource(dur.mirror_event)
check("[D3] the mirror copies the event verbatim; it does not build one",
      "canonical" in msrc and "sha256" not in msrc)
check("[D4] a mirror failure is reported, not swallowed silently",
      "MIRROR_FAILED" in msrc and "print(" in msrc)

print("\n[E] TEST FIXTURES ARE ISOLATED FROM THE SCIENTIFIC RECORD")
wsrc = inspect.getsource(dur.write_test_fixture)
check("[E1] fixtures are flagged is_test TRUE", "TRUE)" in wsrc and "is_test" in wsrc)
check("[E2] fixtures use a distinct event type",
      "TEST_DURABILITY_PROBE" in wsrc)
check("[E3] fixtures take a NEGATIVE seq so they cannot collide with a real one",
      "- 1" in wsrc and "MIN(seq)" in wsrc)
dsrc = inspect.getsource(dur.delete_test_fixture)
check("[E4] delete refuses any row not flagged is_test",
      "is_test = TRUE" in dsrc)
check("[E5] delete reports that it touched no production rows",
      "production_rows_touched" in dsrc)

print("\n[F] NO SECRET CAN ESCAPE")
check("[F1] the DSN is never returned in a status payload",
      "_database_url()" in src and "detail\": \"database unreachable" not in src
      or "type(exc).__name__" in src)
for fn in (dur.durability_status, dur.mirror_event, dur.restore_missing,
           dur.write_test_fixture, dur.read_test_fixture, dur.delete_test_fixture):
    body = inspect.getsource(fn)
    leaks = ("str(exc)" in body) or ("{exc}" in body) or ("% exc" in body)
    check("[F] %-22s never formats the raw exception" % fn.__name__, not leaks)
blob = json.dumps(dur.durability_status(forward_oos.DEFAULT_ROOT))
check("[F2] status payload contains no connection string",
      "postgresql://" not in blob and "@" not in blob.replace("example", ""), blob[:120])

print("\n[G] THE HASH CHAIN IS UNTOUCHED")
check("[G1] append still verifies the ledger before writing",
      "verify_ledger(root)" in asrc and "refusing append" in asrc)
check("[G2] the event hash is still computed over the unsigned event",
      'event["event_hash"] = sha256_bytes(canonical_bytes(unsigned))' in asrc)
check("[G3] duplicate events are still refused",
      "Immutable event already exists" in asrc)
check("[G4] files are still written read-only and exclusively",
      "O_EXCL" in asrc and "0o444" in asrc)

print("\n[H] A TEST FIXTURE MUST NEVER BECOME A LEDGER EVENT")
# Found live on 2026-09-07: restore_missing had no is_test predicate, so a
# durability fixture was written into events/ as TEST_<marker>.json. The
# hash-chain verifier correctly rejected the whole ledger
# (sequence / chain_prev / event_hash / missing_ledger_head_anchor) -- the
# tamper-evidence worked, but the fixture should never have reached the files.
rsrc2 = inspect.getsource(dur.restore_missing)
check("[H1] restore excludes is_test rows",
      "is_test = FALSE" in rsrc2, "the is_test predicate is the primary guard")
check("[H2] a filename allowlist backs it up",
      "_LEDGER_FILE_RE.match(name)" in rsrc2)
for name, allowed in (("00000001_forecast-lock_NQ-FOOS-20260903.json", True),
                      ("00000002_abstention-observation_x.json", True),
                      ("TEST_durability-probe-abc123.json", False),
                      ("../../etc/passwd", False),
                      ("evil.json", False)):
    check("[H3] %-44s allowed=%s" % (name[:44], allowed),
          bool(dur._LEDGER_FILE_RE.match(name)) is allowed)
check("[H4] the fixture writer still uses a non-ledger filename",
      'TEST_%s.json' in inspect.getsource(dur.write_test_fixture),
      "so the allowlist can catch it even if the predicate is bypassed")

print("\n" + "=" * 66)
if FAILURES:
    print("FAILED %d check(s):" % len(FAILURES))
    for f in FAILURES:
        print("   -", f)
    sys.exit(1)
print("ALL V6.6.8 FORWARD-OOS DURABILITY CONTRACT CHECKS PASSED")
