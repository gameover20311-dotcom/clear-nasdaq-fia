from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict


def write_report(
    report: Dict[str, Any],
    output_path: str,
) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    path.write_text(
        json.dumps(report, indent=2),
        encoding="utf-8",
    )

    return path
