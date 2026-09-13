# FastAPI routes for CLEAR NASDAQ — FIA PRE-MOVE MAX RIGOR
from __future__ import annotations
from typing import Any
from fastapi import Request
from .auth_api import scientific_operation_authorized

from .premove_max_engine import analyze_premove_max
from .premove_max_validation import validation_report_max


def install_premove_max_routes(app: Any, hub: Any, build_forecast: Any) -> None:
    existing = {getattr(r, "path", None) for r in getattr(app, "routes", [])}

    if "/api/premove/max" not in existing:
        @app.get("/api/premove/max")
        async def fia_premove_max(request: Request):
            snapshot = await hub.snapshot()
            forecast = build_forecast(snapshot)
            record = scientific_operation_authorized(request, required=False)
            return analyze_premove_max(forecast, snapshot, record=record)

    if "/api/premove/max/validation" not in existing:
        @app.get("/api/premove/max/validation")
        async def fia_premove_max_validation():
            return validation_report_max()

    if "/api/premove/max/health" not in existing:
        @app.get("/api/premove/max/health")
        async def fia_premove_max_health():
            return {
                "ok": True,
                "module": "FIA PRE-MOVE MAX RIGOR",
                "version": "32.0",
                "core_forecast_overwritten": False,
                "core_probability_overwritten": False,
                "broker_execution": False,
                "research_only": True,
            }
