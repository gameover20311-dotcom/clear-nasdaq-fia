from __future__ import annotations

import asyncio
import json
import re
import urllib.request
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict

from fastapi import Body, HTTPException


def _read_json(path: Path) -> Dict[str, Any]:
    try:
        obj=json.loads(path.read_text(encoding="utf-8"))
        return obj if isinstance(obj,dict) else {}
    except Exception:
        return {}


def _find_brain_root() -> Path | None:
    home=Path.home()
    candidates=[
        home/'Downloads/CLEAR_NASDAQ_FIA_BRAIN_V6_CAUSAL_TWIN',
        home/'ClearNasdaq/CLEAR_NASDAQ_FIA_BRAIN_V6_CAUSAL_TWIN',
    ]
    for p in candidates:
        if (p/'fia_brain/orchestrator.py').exists() and (p/'config.json').exists():
            return p
    return None


@lru_cache(maxsize=1)
def _brain_static() -> Dict[str,Any]:
    root=_find_brain_root()
    if root is None:
        return {'installed':False,'status':'UNAVAILABLE','model':'gpt-oss:20b','reason':'V6.6 Brain folder not found'}
    cfg=_read_json(root/'config.json')
    ver='unknown'
    try:
        text=(root/'fia_brain/__init__.py').read_text(encoding='utf-8')
        m=re.search(r'__version__\s*=\s*["\']([^"\']+)',text)
        if m: ver=m.group(1)
    except Exception: pass
    return {'installed':True,'root':str(root),'model':cfg.get('model') or 'gpt-oss:20b','version':ver}


def _ollama_health() -> Dict[str,Any]:
    try:
        req=urllib.request.Request('http://127.0.0.1:11434/api/tags',headers={'Accept':'application/json'})
        with urllib.request.urlopen(req,timeout=1.5) as r:
            obj=json.loads(r.read(2_000_000).decode('utf-8'))
        names=[str(x.get('name') or x.get('model') or '') for x in (obj.get('models') or []) if isinstance(x,dict)]
        return {'status':'LIVE','model_present':any(n.startswith('gpt-oss:20b') for n in names),'models':names}
    except Exception as e:
        return {'status':'UNAVAILABLE','model_present':False,'error':type(e).__name__+': '+str(e)[:200]}


def _latest_shadow(root: Path | None) -> Dict[str,Any] | None:
    if root is None: return None
    candidates=[root/'data/shadow/brain_v6.jsonl',root/'data/shadow/brain_v5.jsonl']
    for p in candidates:
        if not p.exists(): continue
        try:
            lines=[x for x in p.read_text(encoding='utf-8').splitlines() if x.strip()]
            if not lines: continue
            r=json.loads(lines[-1]); payload=r.get('payload') if isinstance(r,dict) and isinstance(r.get('payload'),dict) else r
            if not isinstance(payload,dict): continue
            final=payload.get('final') if isinstance(payload.get('final'),dict) else {}
            return {
                'generated_at_utc':payload.get('generated_at_utc'),
                'status':payload.get('status'),
                'direction':final.get('direction'),
                'bullish_probability':final.get('bullish_probability'),
                'bearish_probability':final.get('bearish_probability'),
                'confidence':final.get('confidence'),
                'error':payload.get('error'),
                'result_sha256':payload.get('result_sha256'),
            }
        except Exception:
            continue
    return None


def brain_status() -> Dict[str,Any]:
    st=dict(_brain_static()); root=Path(st['root']) if st.get('root') else None
    st['ollama']=_ollama_health(); st['latest_shadow']=_latest_shadow(root)
    st['status']='LIVE' if st.get('installed') and st['ollama'].get('model_present') else ('DEGRADED' if st.get('installed') else 'UNAVAILABLE')
    st['truth_note']='This is runtime/install health only. It is not a win-rate or a Sol-parity claim.'
    return st


def phase25_status() -> Dict[str,Any]:
    try:
        from fia.learning_engine import build_learning_status
        s=build_learning_status(); last=s.get('last_record') if isinstance(s.get('last_record'),dict) else {}
        grade=str(last.get('phase25_grade') or '').upper()
        if not grade or grade in {'UNKNOWN','UNLABELED'}:
            status='AWAITING_CHART'; grade=None
        else: status='AVAILABLE'
        def pct(v):
            try:
                x=float(v); return round(100*x,1) if abs(x)<=1 else round(x,1)
            except Exception:return None
        return {
            'status':status,'latest_grade':grade,'confluence_score':last.get('confluence_score'),
            'alignment_pct':pct(last.get('confluence_alignment')),'completeness_pct':pct(last.get('confluence_completeness')),
            'research_alert':last.get('alert_level') or 'NONE','prediction_id':last.get('prediction_id'),
            'records':s.get('records'),'pending':s.get('pending'),'validation':s.get('validation'),
            'note':'Phase 25 updates only after a real chart passes through the final confluence endpoint. No placeholder score is promoted to a result.',
        }
    except Exception as e:
        return {'status':'UNAVAILABLE','latest_grade':None,'confluence_score':None,'alignment_pct':None,'completeness_pct':None,'research_alert':'NONE','error':type(e).__name__+': '+str(e)[:300]}


def whole_system_overlay(backend_root:Path)->Dict[str,Any]:
    try:
        from fia_whole_system_backtest.core import rolling_forward_metrics_dual
    except Exception as e:
        return {'state':'UNAVAILABLE','final':False,'error':type(e).__name__+': '+str(e)[:300]}
    report_path=backend_root/'fia_whole_system_backtest/results/whole_system_backtest_report.json'
    if report_path.exists():
        obj=_read_json(report_path)
        if not obj: return {'state':'UNREADABLE','final':False,'live_forward_oos':rolling_forward_metrics_dual(backend_root)}
    else:
        obj={'state':'NOT_RUN','final':False,'progress':{'completed_cases':0,'total_cases':0,'pct':0.0},'horizons':{'4h':None,'8h':None}}
    obj['live_forward_oos']=rolling_forward_metrics_dual(backend_root)
    return obj


def _route_registry(app)->list[dict[str,Any]]:
    rows=[]
    for route in getattr(app,'routes',[]):
        path=str(getattr(route,'path',''))
        if not path.startswith('/api/'): continue
        methods=sorted(m for m in (getattr(route,'methods',None) or []) if m not in {'HEAD','OPTIONS'})
        rows.append({'path':path,'methods':methods,'status':'REGISTERED'})
    rows.sort(key=lambda x:(x['path'],','.join(x['methods'])))
    return rows


def install_final_cockpit_routes(app, hub, build_forecast, backend_root=None):
    root=Path(backend_root or Path(__file__).resolve().parents[1])

    @app.get('/api/final/dashboard')
    async def final_dashboard():
        from fia.dashboard_api import build_dashboard_payload
        base=await build_dashboard_payload(hub,build_forecast)
        # Every overlay is truth-labelled. If one fails, the field says UNAVAILABLE; live market data is never replaced with a confident default.
        base['whole_system_backtest']=whole_system_overlay(root)
        base['phase25']=phase25_status()
        base['brain_v66']=brain_status()
        base['backend_registry']=_route_registry(app)
        base['final_cockpit']={
            'status':'LIVE','research_only':True,'broker_execution':False,
            'no_mock_performance':True,'historical_and_forward_oos_separate':True,
            'dashboard_contract':'ATOMIC_LIVE_BASE_PLUS_TRUTH_LABELED_LOCAL_VALIDATION_OVERLAYS',
        }
        return base

    @app.post('/api/final/confluence/three-way')
    async def final_three_way_confluence(request: Dict[str,Any]=Body(...)):
        try:
            from fia.accuracy_engine import build_accuracy_assessment
            from fia.confluence_engine import build_confluence_assessment
            from fia.three_way_confluence import build_three_way_confluence
            from fia.learning_engine import record_forward_forecast, attach_confluence, build_research_alert, resolve_due_forward_records
            user_analysis=request.get('user_analysis') if isinstance(request.get('user_analysis'),dict) else {}
            vision_analysis=request.get('vision_analysis') if isinstance(request.get('vision_analysis'),dict) else {}
            snapshot_data=await hub.snapshot(); fia_forecast=build_forecast(snapshot_data); accuracy=build_accuracy_assessment(fia_forecast,snapshot_data)
            phase25=build_confluence_assessment(fia_forecast,accuracy,vision_analysis,snapshot_data)
            result=build_three_way_confluence(fia_forecast,user_analysis,vision_analysis,phase25); result['phase25']=phase25
            try:
                rec=record_forward_forecast(fia_forecast,snapshot_data,accuracy)
                if rec.get('ok') and rec.get('prediction_id'):
                    linked=attach_confluence(rec['prediction_id'],phase25,accuracy)
                    phase25['research_alert']=linked.get('alert') or build_research_alert(accuracy,phase25)
                    result['phase26_prediction_id']=rec['prediction_id']; result['phase26_attached']=bool(linked.get('ok'))
                else:
                    phase25['research_alert']=build_research_alert(accuracy,phase25); result['phase26_attached']=False
                asyncio.create_task(resolve_due_forward_records())
            except Exception as exc:
                phase25['research_alert']=build_research_alert(accuracy,phase25); result['phase26_attached']=False; result['phase26_warning']=type(exc).__name__+': '+str(exc)[:300]
            return result
        except Exception as exc:
            raise HTTPException(status_code=500,detail=str(exc)) from exc
