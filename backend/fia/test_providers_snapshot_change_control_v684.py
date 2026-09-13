"""V6.8.4 — explicit change-control wrapper for the immutable v681 baseline.

v681 is the PRE-REPAIR provider/snapshot equivalence baseline.  It must remain
unchanged and is expected to HARD STOP after the deliberate earnings temporal
admission repair.  This wrapper proves two things instead of simply re-recording
that old baseline:

1. Current repaired code produces the separately pinned post-repair digest.
2. Replacing ONLY ProviderHub._snapshot_earnings_calendar with the untouched
   pre-repair ProtocolMixin implementation restores the original v681 digest.

That localizes the behavioural delta to the authorized earnings admission rule.
The semantic rule itself is tested independently by v683.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
V681 = "fia/test_providers_snapshot_equivalence_v681.py"
PRE_REPAIR_DIGEST = "45cdee64ce472a2abed1a48e1d5e2c11847907e51a3b3fdfb574eaaeff92ab57"
POST_REPAIR_DIGEST = "2dc6b740137a665bcf79267e8a16162e4d227d3083e14a2fcf1943fdea59c7d4"
EXPECTED_OBSERVATIONS = 55

FAILURES = []


def check(name, cond, detail=""):
    if cond:
        print("  PASS  %s" % name)
    else:
        print("  FAIL  %s   %s" % (name, detail))
        FAILURES.append(name)


def run(args):
    env = dict(os.environ)
    env["PYTHONPATH"] = str(BACKEND) + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    return subprocess.run(args, cwd=str(BACKEND), env=env, text=True,
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                          timeout=180)


def parsed(output):
    obs = re.search(r"^observations\s*:\s*(\d+)\s*$", output, re.M)
    digest = re.search(r"^digest\s*:\s*([0-9a-f]{64})\s*$", output, re.M)
    return (int(obs.group(1)) if obs else None,
            digest.group(1) if digest else None)


print("\n[A] CURRENT REPAIRED PROVIDER SURFACE")
current = run([sys.executable, V681])
cur_n, cur_digest = parsed(current.stdout)
check("[A1] immutable pre-repair gate hard-stops on changed behaviour", current.returncode == 1,
      "rc=%s" % current.returncode)
check("[A2] observation count is unchanged", cur_n == EXPECTED_OBSERVATIONS,
      "n=%r" % cur_n)
check("[A3] old baseline is still printed as the expected pre-repair digest",
      PRE_REPAIR_DIGEST in current.stdout)
check("[A4] current repaired digest is separately pinned",
      cur_digest == POST_REPAIR_DIGEST, "got=%r" % cur_digest)
check("[A5] v681 still refuses silent re-recording",
      "HARD STOP. Identify the first differing observation; do not re-record." in current.stdout)

print("\n[B] LOCALIZE THE DELTA TO EARNINGS TEMPORAL ADMISSION")
probe = r'''
import runpy
from fia.providers import ProviderHub
from fia.providers_protocol import ProtocolMixin
ProviderHub._snapshot_earnings_calendar = ProtocolMixin._snapshot_earnings_calendar
runpy.run_path("fia/test_providers_snapshot_equivalence_v681.py", run_name="__main__")
'''
legacy = run([sys.executable, "-c", probe])
old_n, old_digest = parsed(legacy.stdout)
check("[B1] restoring only the pre-repair earnings method makes v681 pass",
      legacy.returncode == 0, "rc=%s tail=%r" % (legacy.returncode, legacy.stdout[-300:]))
check("[B2] legacy observation count remains exact", old_n == EXPECTED_OBSERVATIONS,
      "n=%r" % old_n)
check("[B3] legacy method reproduces the original immutable baseline",
      old_digest == PRE_REPAIR_DIGEST, "got=%r" % old_digest)
check("[B4] repaired and legacy digests are intentionally different",
      cur_digest != old_digest)

print("\n" + "=" * 72)
if FAILURES:
    print("FAILED %d check(s):" % len(FAILURES))
    print("CURRENT V681 TAIL:")
    print(current.stdout[-1200:])
    print("LEGACY-PROBE TAIL:")
    print(legacy.stdout[-1200:])
    raise SystemExit(1)
print("PROVIDER SNAPSHOT CHANGE CONTROL: PASS")
print("pre-repair :", PRE_REPAIR_DIGEST)
print("post-repair:", POST_REPAIR_DIGEST)
print("delta surface: ProviderHub._snapshot_earnings_calendar only")
