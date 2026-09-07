from pathlib import Path
from typing import Any, Dict

from .csv_io import read_csv, write_csv
from .validation import validate_dataset


def integrate_dataset(
    source,
    destination,
) -> Dict[str, Any]:
    source = Path(source)
    destination = Path(destination)

    records = read_csv(source)
    validation = validate_dataset(records)

    result = {
        "source": str(source),
        "destination": str(destination),
        "records_read": len(records),
        "validation": validation,
        "written": False,
    }

    if validation["valid"] and records:
        write_csv(destination, records)
        result["written"] = True

    return result
