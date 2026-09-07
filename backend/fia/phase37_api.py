from __future__ import annotations
from typing import Any
from .phase37_final import final_project_status

def install_phase37_routes(app: Any) -> None:
    existing = {getattr(r, "path", None) for r in getattr(app, "routes", [])}
    if "/api/phase37/final/status" not in existing:
        @app.get("/api/phase37/final/status")
        async def phase37_final_status():
            return final_project_status()
