from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Dict, List


def load_csv(path: str) -> List[Dict[str, Any]]:
    p = Path(path)

    if not p.exists():
        return []

    with p.open("r", newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_json(
    data: Dict[str, Any],
    path: str,
) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)

    p.write_text(
        json.dumps(data, indent=2),
        encoding="utf-8",
    )

    return p
