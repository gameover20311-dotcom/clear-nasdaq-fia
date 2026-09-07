from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import json
from fia.premove_max_validation import validation_report_max

if __name__ == "__main__":
    print(json.dumps(validation_report_max(), indent=2))
