#!/usr/bin/env python3
from pathlib import Path
import json, sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from fia_brain.config import load
from fia_brain.orchestrator import FIABrain

if __name__ == "__main__":
    cfg = load(str(ROOT / "config.json") if (ROOT / "config.json").exists() else None)
    out = FIABrain(cfg).analyze(write_shadow=True)
    print(json.dumps(out, indent=2, ensure_ascii=False))
