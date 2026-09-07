from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import httpx

from .utils import as_float, parse_dt, stable_hash

ROOT = Path(__file__).resolve().parents[2]
CACHE_DIR = ROOT / "fia_cognitive_data" / "macro_vintages"

SERIES = {
    "CPI": "CPIAUCSL",
    "CORE_CPI": "CPILFESL",
    "PCE": "PCEPI",
    "CORE_PCE": "PCEPILFE",
    "PAYROLLS": "PAYEMS",
    "UNEMPLOYMENT": "UNRATE",
    "GDP_REAL": "GDPC1",
    "FED_FUNDS": "DFF",
    "US10Y": "DGS10",
}


async def fred_vintage_observations(series_id: str, as_of: Any, api_key: Optional[str] = None,
                                    limit: int = 24) -> Dict[str, Any]:
    """Fetch point-in-time FRED/ALFRED observations as they were known on as_of.

    This function deliberately does not fabricate market expectations. Consensus
    expectations must come from a separately provenance-tracked source.
    """
    dt = parse_dt(as_of)
    if dt is None:
        return {"available": False, "reason": "invalid as_of"}
    key = api_key or os.getenv("FRED_API_KEY", "")
    if not key:
        return {"available": False, "reason": "FRED_API_KEY missing", "series_id": series_id}
    date = dt.date().isoformat()
    params = {
        "series_id": series_id,
        "api_key": key,
        "file_type": "json",
        "realtime_start": date,
        "realtime_end": date,
        "sort_order": "desc",
        "limit": int(limit),
    }
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.get("https://api.stlouisfed.org/fred/series/observations", params=params)
            r.raise_for_status()
            payload = r.json()
    except Exception as exc:
        return {"available": False, "reason": f"FRED request failed: {exc}", "series_id": series_id}
    observations = []
    for row in payload.get("observations", []) or []:
        val = as_float(row.get("value"))
        if val is None:
            continue
        observations.append({
            "date": row.get("date"),
            "value": val,
            "realtime_start": row.get("realtime_start"),
            "realtime_end": row.get("realtime_end"),
        })
    return {
        "available": bool(observations),
        "provider": "FRED/ALFRED",
        "series_id": series_id,
        "as_of": dt.isoformat(),
        "observations": observations,
        "consensus_available": False,
        "policy": "Vintage values are point-in-time. A surprise score is withheld unless a timestamped consensus source is supplied.",
    }


async def build_macro_vintage_snapshot(as_of: Any, series: Optional[Iterable[str]] = None) -> Dict[str, Any]:
    names = list(series or SERIES.keys())
    results = {}
    for name in names:
        sid = SERIES.get(name, name)
        results[name] = await fred_vintage_observations(sid, as_of)
    available = [k for k,v in results.items() if v.get("available")]
    return {
        "as_of": str(as_of),
        "available_series": available,
        "missing_series": [k for k in names if k not in available],
        "series": results,
        "surprise_score": None,
        "surprise_status": "WITHHELD_NO_POINT_IN_TIME_CONSENSUS",
    }


def save_macro_snapshot(snapshot: Dict[str, Any]) -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    digest = stable_hash(snapshot)[:18]
    path = CACHE_DIR / f"macro_{digest}.json"
    path.write_text(json.dumps(snapshot, indent=2, default=str), encoding="utf-8")
    return path
