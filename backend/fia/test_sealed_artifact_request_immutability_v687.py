"""V6.8.7 — a real /api/forecast request cannot mutate the sealed Phase14 CSV.

This regression exercises FastAPI routing and the real recorder adapter.  Only
external/provider and unrelated forward-learning side effects are isolated so
the request is deterministic.  The dangerous historical-append env flag is set
on purpose: the sealed target must remain read-only even under that legacy flag.
"""
from __future__ import annotations

import hashlib
import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

BACKEND = Path(__file__).resolve().parent.parent
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

# Disable the background prospective collector before main installs startup
# handlers.  This test is about a normal forecast read, not OOS collection.
os.environ["FIA_FORWARD_OOS_ENABLED"] = "0"
os.environ["DATABASE_URL"] = ""

import main  # noqa: E402
from fia.models import Forecast  # noqa: E402


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fixture_forecast() -> Forecast:
    return Forecast(
        symbol="NQ",
        horizon_hours=8,
        direction="BULLISH",
        bullish_probability=60.0,
        bearish_probability=40.0,
        confidence=55.0,
        regime="TEST_ONLY",
        status="LIVE",
        score=0.20,
        signals=[],
        invalidation=["TEST_ONLY"],
        generated_at="2026-09-13T14:00:00+00:00",
        data_coverage=1.0,
        source_status={},
        thesis="TEST_ONLY",
        bullish_evidence=[],
        bearish_evidence=[],
        intelligence_coverage=1.0,
        consistency={},
    )


def main_test() -> int:
    protected = (
        main.BACKEND_DIR
        / "fia_backtest_phase14"
        / "data"
        / "historical_predictions.csv"
    )
    if not protected.exists():
        print("FAIL protected artifact missing:", protected)
        return 1

    before_bytes = protected.read_bytes()
    before_hash = sha256(protected)
    snapshot = {
        "status": "LIVE",
        "provider": "TEST_ONLY",
        "timestamp": "2026-09-13T14:00:00+00:00",
        "data": {"nq_futures_price": 25000.0},
    }

    # If the removed bypass still existed, this exact request would append to
    # historical_predictions.csv.  Keeping the env flag here prevents a future
    # refactor from quietly re-introducing the same escape hatch.
    with patch.dict(os.environ, {"FIA_ALLOW_PROTECTED_HISTORICAL_APPEND": "1"}), \
         patch.object(main.hub, "snapshot", new=AsyncMock(return_value=snapshot)), \
         patch.object(main, "build_forecast", return_value=fixture_forecast()), \
         patch.object(main, "build_accuracy_assessment", return_value={}), \
         patch.object(main, "record_forward_forecast", return_value={"TEST_ONLY": True}), \
         patch.object(main, "resolve_due_forward_records", new=AsyncMock(return_value={})), \
         TestClient(main.app) as client:
        response = client.get("/api/forecast")

    after_bytes = protected.read_bytes()
    after_hash = sha256(protected)

    checks = {
        "real_forecast_http_200": response.status_code == 200,
        "protected_bytes_identical": after_bytes == before_bytes,
        "protected_sha256_identical": after_hash == before_hash,
        "forecast_route_executed": response.json().get("symbol") == "NQ",
    }
    for name, ok in checks.items():
        print(("PASS" if ok else "FAIL"), name)
    print("before_sha256:", before_hash)
    print("after_sha256 :", after_hash)
    if not all(checks.values()):
        return 1
    print("SEALED ARTIFACT REAL REQUEST IMMUTABILITY: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main_test())
