import json
from pathlib import Path
from typing import Any, Dict


class DashboardStorage:
    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def write_json(self, name: str, data: Dict[str, Any]) -> Path:
        path = self.root / f"{name}.json"
        path.write_text(
            json.dumps(data, indent=2),
            encoding="utf-8",
        )
        return path

    def write_text(self, name: str, text: str) -> Path:
        path = self.root / f"{name}.txt"
        path.write_text(text, encoding="utf-8")
        return path
