import csv
from pathlib import Path
from typing import Dict, List


def read_csv(path) -> List[Dict[str, str]]:
    path = Path(path)

    if not path.exists():
        return []

    with path.open("r", newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_csv(
    path,
    rows: List[Dict[str, object]],
) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    if not rows:
        path.write_text("", encoding="utf-8")
        return path

    keys = sorted({
        key
        for row in rows
        for key in row.keys()
    })

    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=keys)
        writer.writeheader()
        writer.writerows(rows)

    return path
