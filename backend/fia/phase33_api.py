from __future__ import annotations
import asyncio, json, os
from pathlib import Path
from typing import Any
from .phase33_engine import analyze_phase33
from .phase33_llm import llm_evidence_review


def _summary_path()->Path: return Path(__file__).resolve().parents[1]/"fia_backtest_phase33"/"results"/"phase33_full_replay_1y_summary.json"

def install_phase33_routes(app:Any,hub:Any,build_forecast:Any)->None:
    existing={getattr(r,"path",None) for r in getattr(app,"routes",[])}
    if "/api/phase33" not in existing:
        @app.get("/api/phase33")
        async def phase33_live():
            snap=await hub.snapshot(); fc=build_forecast(snap); return analyze_phase33(fc,snap,record=True)
    if "/api/phase33/health" not in existing:
        @app.get("/api/phase33/health")
        async def phase33_health(): return {"ok":True,"module":"FIA PHASE33 INSTITUTIONAL PRE-MOVE","version":"33.0","research_only":True,"broker_execution":False,"features_declared":23}
    if "/api/phase33/backtest" not in existing:
        @app.get("/api/phase33/backtest")
        async def phase33_backtest_summary():
            p=_summary_path()
            return json.loads(p.read_text()) if p.exists() else {"ok":False,"status":"RUN_PHASE33_REPLAY_FIRST","path":str(p)}
    if "/api/phase33/copilot" not in existing:
        @app.get("/api/phase33/copilot")
        async def phase33_copilot(prompt:str="Summarize current pre-move evidence"):
            snap=await hub.snapshot(); fc=build_forecast(snap); r=analyze_phase33(fc,snap,record=False)
            # Structured evidence copilot by default. LLM use can be enabled separately without making it a trading executor.
            return {"ok":True,"prompt":prompt[:500],"answer":{"state":r.get("state"),"direction":r.get("direction"),"strength":r.get("decision_strength_0_100"),"alert":r.get("alert"),"top_votes":r.get("ensemble",{}).get("votes",[])[:6]},"llm_review":llm_evidence_review(r,prompt),"broker_execution":False}
    if "/api/phase33/stream" not in existing:
        @app.websocket("/api/phase33/stream")
        async def phase33_stream(ws):
            await ws.accept()
            try:
                while True:
                    snap=await hub.snapshot(); fc=build_forecast(snap); r=analyze_phase33(fc,snap,record=False)
                    await ws.send_json({"generated_at":r.get("generated_at"),"state":r.get("state"),"direction":r.get("direction"),"strength":r.get("decision_strength_0_100"),"alert":r.get("alert"),"ensemble":r.get("ensemble")})
                    await asyncio.sleep(2.0)
            except Exception:
                try: await ws.close()
                except Exception: pass
