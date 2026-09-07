from __future__ import annotations
import asyncio, json
from pathlib import Path
from typing import Any
from .phase34_engine import analyze_phase34
from .phase34_source_registry import audit_sources
ROOT=Path(__file__).resolve().parents[1]
def install_phase34_routes(app:Any,hub:Any,build_forecast:Any)->None:
    existing={getattr(r,'path',None) for r in getattr(app,'routes',[])}
    if '/api/phase34' not in existing:
        @app.get('/api/phase34')
        async def live():
            s=await hub.snapshot(); f=build_forecast(s); return analyze_phase34(f,s,True)
    if '/api/phase34/health' not in existing:
        @app.get('/api/phase34/health')
        async def health(): return {'ok':True,'module':'FIA PHASE34 ALL-POINTS PRE-MOVE','version':'34.0','points':23,'broker_execution':False,'research_only':True}
    if '/api/phase34/sources' not in existing:
        @app.get('/api/phase34/sources')
        async def sources(): return audit_sources(await hub.snapshot())
    if '/api/phase34/backtest' not in existing:
        @app.get('/api/phase34/backtest')
        async def backtest():
            p=ROOT/'fia_backtest_phase34/results/phase34_full_replay_summary.json'
            return json.loads(p.read_text()) if p.exists() else {'ok':False,'status':'RUN_PHASE34_REPLAY_FIRST'}
    if '/api/phase34/copilot' not in existing:
        @app.get('/api/phase34/copilot')
        async def copilot(prompt:str='Explain current pre-move state'):
            s=await hub.snapshot(); f=build_forecast(s); r=analyze_phase34(f,s,False)
            return {'ok':True,'prompt':prompt[:500],'state':r.get('state'),'direction':r.get('direction'),'strength':r.get('decision_strength_0_100'),'alert':r.get('alert'),'missing_sources':[k for k,v in r.get('source_coverage',{}).get('sources',{}).items() if v.get('status')!='AVAILABLE'],'broker_execution':False}
    if '/api/phase34/stream' not in existing:
        @app.websocket('/api/phase34/stream')
        async def stream(ws):
            await ws.accept()
            try:
                while True:
                    s=await hub.snapshot(); f=build_forecast(s); r=analyze_phase34(f,s,False)
                    await ws.send_json({'state':r.get('state'),'direction':r.get('direction'),'strength':r.get('decision_strength_0_100'),'alert':r.get('alert'),'coverage':r.get('source_coverage',{}).get('coverage')})
                    await asyncio.sleep(1.0)
            except Exception:
                try: await ws.close()
                except Exception: pass
