from __future__ import annotations
from typing import Any, Dict
from fastapi import HTTPException
from .forexcom_chart_liquidity import save_payload, load_latest, CHART_SYMBOL

def install_forexcom_chart_liquidity_routes(app: Any) -> None:
    existing = {getattr(r, "path", None) for r in getattr(app, "routes", [])}

    if "/api/liquidity/chart-sync" not in existing:
        @app.post("/api/liquidity/chart-sync")
        async def forexcom_chart_sync(payload: Dict[str, Any]):
            try:
                clean = save_payload(payload)
                return {
                    "ok": True,
                    "symbol": CHART_SYMBOL,
                    "current_price": clean.get("current_price"),
                    "levels_received": len(clean.get("levels") or {}),
                    "source_truth": clean.get("source_truth"),
                }
            except PermissionError as exc:
                raise HTTPException(status_code=401, detail=str(exc))
            except Exception as exc:
                raise HTTPException(status_code=400, detail=str(exc))

    if "/api/liquidity/chart-sync/status" not in existing:
        @app.get("/api/liquidity/chart-sync/status")
        async def forexcom_chart_sync_status():
            return load_latest()
