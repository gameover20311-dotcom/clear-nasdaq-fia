from __future__ import annotations
import json
from fia.phase36_ablation import run_ablation
if __name__ == "__main__":
    print(json.dumps(run_ablation(),indent=2))
    print("PHASE 36 ROOT-CAUSE + ABLATION LAB COMPLETE")
