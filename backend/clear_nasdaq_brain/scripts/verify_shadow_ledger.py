#!/usr/bin/env python3
from pathlib import Path
import json, sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from fia_brain.config import load
from fia_brain.ledger import verify
cfg = load(str(ROOT / "config.json") if (ROOT / "config.json").exists() else None)
print(json.dumps(verify(cfg["shadow_ledger"]), indent=2))
