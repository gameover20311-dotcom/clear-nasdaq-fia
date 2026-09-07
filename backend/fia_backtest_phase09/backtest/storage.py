import csv
from pathlib import Path
from typing import Any, Dict, Iterable


class CSVStorage:
    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def write(self, name: str, rows: Iterable[Dict[str, Any]]) -> Path:
        rows = list(rows)
        path = self.root / f"{name}.csv"

        if not rows:
            path.write_text("", encoding="utf-8")
            return path

        keys = sorted({key for row in rows for key in row.keys()})

        with path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=keys)
            writer.writeheader()
            writer.writerows(rows)

        return path
