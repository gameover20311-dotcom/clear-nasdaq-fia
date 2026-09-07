"""
FINAL backtest launcher.

This file intentionally does not mutate Phase37 policy or production weights.
It runs existing validated replay/ablation assets if present and prints the
frozen Phase37 candidate so the user can evaluate without another coding phase.
"""
from pathlib import Path
import sys, json, subprocess

_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from fia.phase37_final import final_project_status

def main():
    status = final_project_status()
    print(json.dumps(status, indent=2))
    print("\nPHASE 37 FINAL BACKTEST MODE")
    print("Policy is frozen. No feature/weight changes are performed here.")

    # Prefer the most complete existing replay asset, but do not fail if absent.
    candidates = [
        _BACKEND / "fia_backtest_phase35" / "phase35_one_shot.py",
        _BACKEND / "fia_backtest_phase34" / "phase34_full_replay.py",
    ]
    found = next((p for p in candidates if p.exists()), None)
    if found:
        print(f"\nRunning preserved full replay reference: {found.relative_to(_BACKEND)}")
        subprocess.check_call([sys.executable, str(found)], cwd=str(_BACKEND))
    else:
        print("\nNo preserved replay launcher found. Project remains final; provide a new genuine dataset for validation.")

    print("\nPHASE 37 FINAL BACKTEST WRAPPER COMPLETE")
    print("NO CODING PHASE AFTER 37 — only validation/data updates.")

if __name__ == "__main__":
    main()
