from __future__ import annotations
import subprocess,sys,pathlib
ROOT=pathlib.Path(__file__).resolve().parents[1]
for script in ["phase33_integrity_test.py","phase33_full_replay.py"]:
    p=pathlib.Path(__file__).resolve().parent/script
    rc=subprocess.call([sys.executable,str(p)],cwd=str(ROOT))
    if rc: raise SystemExit(rc)
print("PHASE 33 FULL TEST + REPLAY COMPLETE")
