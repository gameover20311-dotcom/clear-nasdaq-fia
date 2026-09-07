import csv
from pathlib import Path


def load_historical_predictions(csv_path):
    path = Path(csv_path)

    if not path.exists():
        raise FileNotFoundError(
            f"Historical dataset not found: {path}"
        )

    with path.open("r", newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


if __name__ == "__main__":
    print("FIA Phase 15 Historical Loader: READY")
