# FastAPI helper routes for CLEAR NASDAQ — FIA Pre-Move Intelligence
from __future__ import annotations
from typing import Any

from .premove_engine import analyze_premove, premove_history
from .premove_calibration import validation_report


def install_premove_routes(app: Any, hub: Any, build_forecast: Any) -> None:
    # === FIA PREMOVE MAX PHASE32 ROUTE HOOK ===
    from .premove_max_api import install_premove_max_routes
    install_premove_max_routes(app, hub, build_forecast)
    existing = {getattr(r, "path", None) for r in getattr(app, "routes", [])}

    if "/api/premove" not in existing:
        @app.get("/api/premove")
        async def fia_premove():
            snapshot = await hub.snapshot()
            forecast = build_forecast(snapshot)
            return analyze_premove(forecast, snapshot, record=True)

    if "/api/premove/history" not in existing:
        @app.get("/api/premove/history")
        async def fia_premove_history(limit: int = 100):
            return premove_history(limit=limit)

    if "/api/premove/validation" not in existing:
        @app.get("/api/premove/validation")
        async def fia_premove_validation():
            return validation_report()

    if "/api/premove/health" not in existing:
        @app.get("/api/premove/health")
        async def fia_premove_health():
            return {
                "ok": True,
                "module": "FIA PRE-MOVE INTELLIGENCE",
                "core_forecast_overwritten": False,
                "broker_execution": False,
                "research_only": True,
            }
