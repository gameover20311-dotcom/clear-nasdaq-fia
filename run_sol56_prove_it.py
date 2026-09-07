#!/usr/bin/env python3
from pathlib import Path
import runpy
import sys

root = Path(__file__).resolve().parent
target = root / "tools" / "sol56_prove_it" / "SOL56_PROVE_IT_ZERO_COST_EDGE_LAB.py"

if not target.exists():
    raise SystemExit("SOL56 module missing. Run: python3 SOL56_INSTALL_CLEAR_NASDAQ.py")

if "--project-root" not in sys.argv:
    sys.argv.extend(["--project-root", str(root)])

runpy.run_path(str(target), run_name="__main__")
