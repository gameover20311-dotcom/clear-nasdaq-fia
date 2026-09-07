import csv
import json
from pathlib import Path
from typing import Iterable, Dict, Any


class JsonlStore:
    """Append-only store for reproducible backtest records."""

    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def append(self, name: str, record: Dict[str, Any]):
        path = self.root / f"{name}.jsonl"
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
        return path

    def write_many(self, name: str, records: Iterable[Dict[str, Any]]):
        path = self.root / f"{name}.jsonl"
        with path.open("w", encoding="utf-8") as f:
            for record in records:
                f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
        return path


class CsvStore:
    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def write(self, name: str, rows):
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
