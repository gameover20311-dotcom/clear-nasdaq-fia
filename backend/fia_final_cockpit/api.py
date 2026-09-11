from __future__ import annotations

import asyncio
import hashlib
import json
import re
import urllib.request
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import Body, HTTPException, Header


def _read_json(path: Path) -> Dict[str, Any]:
    try:
        obj=json.loads(path.read_text(encoding="utf-8"))
        return obj if isinstance(obj,dict) else {}
    except Exception:
        return {}


def _find_brain_root() -> Path | None:
    home=Path.home()
    candidates=[
        Path(__file__).resolve().parents[1] / 'clear_nasdaq_brain',
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
        return {'status':'LIVE','model_present':any(n=='gpt-oss:20b' for n in names),'models':names}
    except Exception as e:
        return {'status':'UNAVAILABLE','model_present':False,'error':type(e).__name__+': '+str(e)[:200]}


def _shadow_sha256_obj(obj: Any) -> str:
    raw=json.dumps(obj,sort_keys=True,separators=(",",":"),ensure_ascii=False,allow_nan=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()

def _verify_shadow_file(path: Path) -> Dict[str,Any]:
    if not path.exists(): return {'ok':True,'rows':0,'head_hash':'0'*64}
    try:
        rows=[]
        for n,line in enumerate(path.read_text(encoding='utf-8').splitlines(),1):
            if not line.strip(): continue
            obj=json.loads(line)
            if not isinstance(obj,dict): return {'ok':False,'reason':f'row_{n}_not_object'}
            rows.append(obj)
        prev='0'*64; seen=set()
        for i,row in enumerate(rows):
            rh=str(row.get('record_hash') or '')
            if len(rh)!=64 or rh in seen: return {'ok':False,'rows':len(rows),'reason':'invalid_or_duplicate_record_hash','bad_index':i}
            if str(row.get('prev_hash') or '')!=prev: return {'ok':False,'rows':len(rows),'reason':'prev_hash_mismatch','bad_index':i}
            body={k:v for k,v in row.items() if k!='record_hash'}
            if rh!=_shadow_sha256_obj(body): return {'ok':False,'rows':len(rows),'reason':'record_hash_mismatch','bad_index':i}
            seen.add(rh); prev=rh
        anchor=path.with_suffix(path.suffix+'.head.json')
        if rows and not anchor.exists(): return {'ok':False,'rows':len(rows),'reason':'ledger_head_anchor_missing'}
        if anchor.exists():
            a=json.loads(anchor.read_text(encoding='utf-8'))
            ah=str(a.get('anchor_sha256') or ''); body={k:v for k,v in a.items() if k!='anchor_sha256'}
            if ah!=_shadow_sha256_obj(body): return {'ok':False,'rows':len(rows),'reason':'ledger_head_anchor_checksum_mismatch'}
            if int(a.get('rows',-1))!=len(rows) or str(a.get('head_hash') or '')!=prev:
                return {'ok':False,'rows':len(rows),'reason':'ledger_head_anchor_mismatch'}
        return {'ok':True,'rows':len(rows),'head_hash':prev}
    except Exception as e:
        return {'ok':False,'rows':0,'reason':type(e).__name__+': '+str(e)[:200]}

def _latest_shadow(root: Path | None) -> Dict[str,Any] | None:
    if root is None: return None
    # V6.6 production truth must never silently fall back to a different ledger generation.
    p=root/'data/shadow/brain_v6.jsonl'
    if not p.exists(): return None
    integrity=_verify_shadow_file(p)
    if not integrity.get('ok'):
        return {'status':'INTEGRITY_ERROR','_ledger_integrity_ok':False,'_ledger_integrity':integrity}
    try:
        lines=[x for x in p.read_text(encoding='utf-8').splitlines() if x.strip()]
        if not lines: return None
        r=json.loads(lines[-1]); payload=r.get('payload') if isinstance(r,dict) and isinstance(r.get('payload'),dict) else r
        if not isinstance(payload,dict): return None
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
            '_ledger_integrity_ok':True,'_ledger_integrity':integrity,
        }
    except Exception as e:
        return {'status':'INTEGRITY_ERROR','_ledger_integrity_ok':False,'_ledger_integrity':{'ok':False,'reason':type(e).__name__+': '+str(e)[:200]}}


def _shadow_age_seconds(shadow: Optional[Dict[str,Any]]) -> Optional[float]:
    if not isinstance(shadow,dict): return None
    raw=shadow.get('generated_at_utc')
    if not isinstance(raw,str) or not raw.strip(): return None
    try:
        x=raw.strip()
        if x.endswith('Z'): x=x[:-1]+'+00:00'
        dt=datetime.fromisoformat(x)
        if dt.tzinfo is None: dt=dt.replace(tzinfo=timezone.utc)
        return max(0.0,(datetime.now(timezone.utc)-dt.astimezone(timezone.utc)).total_seconds())
    except Exception:
        return None

def brain_status() -> Dict[str,Any]:
    st=dict(_brain_static()); root=Path(st['root']) if st.get('root') else None
    st['ollama']=_ollama_health(); st['latest_shadow']=_latest_shadow(root)
    installed=bool(st.get('installed')); model_present=bool(st['ollama'].get('model_present'))
    shadow=st.get('latest_shadow') if isinstance(st.get('latest_shadow'),dict) else None
    shadow_status=str((shadow or {}).get('status') or '').upper(); age=_shadow_age_seconds(shadow)
    shadow_integrity_ok=bool((shadow or {}).get('_ledger_integrity_ok',True))
    fresh_success=bool(shadow_integrity_ok and shadow_status=='OK' and age is not None and age<=900)
    st['runtime_ready']=bool(installed and model_present)
    st['successful_inference_proven']=bool(shadow_integrity_ok and shadow_status=='OK')
    st['shadow_integrity_ok']=shadow_integrity_ok
    st['latest_shadow_age_seconds']=round(age,2) if age is not None else None
    st['fresh_successful_inference']=fresh_success
    if not installed: st['status']='UNAVAILABLE'
    elif not model_present: st['status']='DEGRADED'
    elif not shadow_integrity_ok: st['status']='READY_SHADOW_INTEGRITY_ERROR'
    elif fresh_success: st['status']='LIVE'
    elif shadow is None: st['status']='READY_NO_INFERENCE'
    elif shadow_status!='OK': st['status']='READY_FAIL_CLOSED'
    else: st['status']='READY_STALE_INFERENCE'
    st['truth_note']='LIVE requires a fresh successful V6.6.1 inference. Installed Ollama/model readiness alone is not LIVE and is not a win-rate or Sol-parity claim.'
    return st


def _atomic_write_json(path: Path, payload: Dict[str,Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp=path.with_suffix(path.suffix+'.tmp')
    tmp.write_text(json.dumps(payload,ensure_ascii=False,sort_keys=True,indent=2)+'\n',encoding='utf-8')
    tmp.replace(path)

def _phase25_cache_path(backend_root: Path) -> Path:
    return backend_root/'fia_final_cockpit/state/latest_phase25.json'

def _phase25_compact(raw: Dict[str,Any], source: str, records=None, pending=None, validation=None) -> Dict[str,Any]:
    def pct(v):
        try:
            x=float(v); return round(100*x,1) if abs(x)<=1 else round(x,1)
        except Exception:return None
    grade=str(raw.get('phase25_grade') or raw.get('setup_grade') or raw.get('latest_grade') or '').upper()
    if not grade or grade in {'UNKNOWN','UNLABELED','—'}: grade=None
    alert_raw=raw.get('alert_level') or raw.get('research_alert') or raw.get('research_alert_level') or 'NONE'
    if isinstance(alert_raw,dict):
        alert_level=str(alert_raw.get('level') or alert_raw.get('status') or 'NONE')
        alert_detail=alert_raw
    else:
        alert_level=str(alert_raw or 'NONE')
        alert_detail=None
    return {
        'status':'AVAILABLE' if grade else 'AWAITING_CHART','latest_grade':grade,
        'confluence_score':raw.get('confluence_score'),
        'alignment_pct':pct(raw.get('confluence_alignment') if raw.get('confluence_alignment') is not None else raw.get('alignment_pct')),
        'completeness_pct':pct(raw.get('confluence_completeness') if raw.get('confluence_completeness') is not None else raw.get('completeness_pct')),
        'research_alert':alert_level,'research_alert_detail':alert_detail,
        'prediction_id':raw.get('prediction_id') or raw.get('phase26_prediction_id'),
        'phase26_attached':raw.get('phase26_attached'),'recorded_at_utc':raw.get('recorded_at_utc'),
        'source':source,'records':records,'pending':pending,'validation':validation,
        'note':'Latest real chart assessment. Durable chart cache is preferred; otherwise the newest forward record with a real Phase 25 grade is used. No placeholder score is promoted to a result.',
    }

def phase25_status(backend_root: Path) -> Dict[str,Any]:
    cache=_read_json(_phase25_cache_path(backend_root))
    if cache:
        out=_phase25_compact(cache,'LIVE_CHART_CACHE')
        if out.get('latest_grade'): return out
    try:
        from fia.learning_engine import build_learning_status
        s=build_learning_status(); fpath=Path(str(s.get('forward_file') or '')); rows=[]
        if fpath.exists():
            try:
                import csv
                with fpath.open(newline='',encoding='utf-8') as fh: rows=list(csv.DictReader(fh))
            except Exception: rows=[]
        latest={}
        for row in reversed(rows):
            grade=str(row.get('phase25_grade') or '').upper()
            if grade and grade not in {'UNKNOWN','UNLABELED'}: latest=row; break
        if latest: return _phase25_compact(latest,'PHASE26_LATEST_VALID',s.get('records'),s.get('pending'),s.get('validation'))
        return _phase25_compact({},'NONE',s.get('records'),s.get('pending'),s.get('validation'))
    except Exception as e:
        return {'status':'UNAVAILABLE','latest_grade':None,'confluence_score':None,'alignment_pct':None,'completeness_pct':None,'research_alert':'NONE','error':type(e).__name__+': '+str(e)[:300]}

def data_truth_overlay(base: Dict[str,Any]) -> Dict[str,Any]:
    live=base.get('live') if isinstance(base.get('live'),dict) else {}
    snap=live.get('snapshot') if isinstance(live.get('snapshot'),dict) else {}
    data=snap.get('data') if isinstance(snap.get('data'),dict) else snap
    data=data if isinstance(data,dict) else {}
    ph=data.get('provider_health') if isinstance(data.get('provider_health'),dict) else {}
    def ls(k): return ph.get(k) if isinstance(ph.get(k),list) else []
    checks={
        'nq_structure':data.get('nq_structure') is not None,'spx_confirmation':data.get('spx_confirmation') is not None,
        'dxy':data.get('dxy_value') is not None,'us10y':data.get('us10y_value') is not None,
        'semiconductors':data.get('semis') is not None,'breadth':data.get('breadth') is not None,
        'mega_cap_leadership':bool(data.get('mega_cap_details')),
        'earnings_calendar':bool(data.get('earnings_calendar_available')) or int(data.get('earnings_events') or 0)>0,
        'earnings_directional_surprise':data.get('earnings') is not None,
        'liquidity':bool(live.get('liquidity_groups')) or bool(live.get('liquidity')),
    }
    return {
        'provider_overall':ph.get('overall') or 'UNKNOWN','provider_score':ph.get('score'),
        'available_sources':ls('available_sources'),'missing_sources':ls('missing_sources'),'critical_missing':ls('critical_missing'),
        'stale_sources':ls('stale_sources'),'fallback_active':ls('fallback_active'),
        'dashboard_field_presence':checks,'dashboard_fields_absent':[k for k,v in checks.items() if not v],
        'truth':'Missing/stale/absent stays explicit. REGISTERED route status is not treated as proof that a data feed is live.',
    }

def _cockpit_truth_status(base: Dict[str,Any], truth: Dict[str,Any]) -> Dict[str,Any]:
    live=base.get('live') if isinstance(base.get('live'),dict) else {}
    snap=live.get('snapshot') if isinstance(live.get('snapshot'),dict) else {}
    fc=live.get('forecast') if isinstance(live.get('forecast'),dict) else {}
    provider_overall=str(truth.get('provider_overall') or 'UNKNOWN').upper()
    snapshot_status=str(snap.get('status') or 'UNKNOWN').upper()
    forecast_status=str(fc.get('status') or 'UNKNOWN').upper()
    good={'LIVE','OK','HEALTHY'}; bad={'ERROR','DOWN','FAILED','FAIL','DEAD','UNHEALTHY','STALE','MISSING','UNAVAILABLE'}
    critical=list(truth.get('critical_missing') or []); stale=list(truth.get('stale_sources') or [])
    ready=(forecast_status in good and snapshot_status in good and provider_overall in good and not critical and not stale)
    if ready: status='LIVE'
    elif provider_overall in bad or forecast_status in bad or snapshot_status in bad: status='UNAVAILABLE'
    else: status='DEGRADED'
    return {'status':status,'truth_ready':ready,'provider_overall':provider_overall,'snapshot_status':snapshot_status,'forecast_status':forecast_status,'critical_missing':critical,'stale_sources':stale}

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
        base['phase25']=phase25_status(root)
        base['brain_v66']=brain_status()
        base['backend_registry']=_route_registry(app)
        truth=data_truth_overlay(base); base['data_truth']=truth
        cockpit_truth=_cockpit_truth_status(base,truth)
        from fia.forward_oos_monitor import build_campaign_status
        campaign = build_campaign_status(root / 'fia_forward_oos')
        base['forward_oos_campaign'] = campaign
        base['final_cockpit']={
            **cockpit_truth,'research_only':True,'broker_execution':False,
            'system_status': ('READY' if cockpit_truth['truth_ready'] and
                              campaign.get('operational_ok') is True else 'DEGRADED'),
            'forward_oos_status': campaign.get('status', 'UNAVAILABLE'),
            'no_mock_performance':True,'historical_and_forward_oos_separate':True,
            'dashboard_contract':'ATOMIC_LIVE_BASE_PLUS_TRUTH_LABELED_LOCAL_VALIDATION_OVERLAYS',
        }
        return base


    # CLOUD THREE-BRAIN SHADOW ENDPOINT
    _cloud_brain_lock = asyncio.Lock()
    _cloud_brain_instance = None

    @app.post('/api/final/brain/analyze')
    async def final_brain_analyze(authorization: Optional[str] = Header(default=None)):
        nonlocal _cloud_brain_instance

        try:
            from fia.auth_api import _bearer, decode_session_token
            decode_session_token(_bearer(authorization))
        except Exception as exc:
            raise HTTPException(status_code=401, detail='AUTH_REQUIRED') from exc

        if _cloud_brain_lock.locked():
            raise HTTPException(status_code=409, detail='BRAIN_BUSY')

        async with _cloud_brain_lock:
            try:
                import os, sys

                brain_root = root / 'clear_nasdaq_brain'
                if not brain_root.exists():
                    raise RuntimeError('CLOUD_BRAIN_ROOT_MISSING')

                brain_root_s = str(brain_root)
                if brain_root_s not in sys.path:
                    sys.path.insert(0, brain_root_s)

                # Render exposes its runtime port through PORT.
                # Keep the FIA evidence capture loopback-only.
                port = str(os.environ.get('PORT') or '').strip()
                if port:
                    os.environ['FIA_BASE_URL'] = f'http://127.0.0.1:{port}'

                os.environ.setdefault('FIA_INFERENCE_PROVIDER', 'groq')
                os.environ['FIA_LOCAL_MODEL_DIGEST'] = ''

                from fia_brain.config import load
                from fia_brain.orchestrator import FIABrain

                if _cloud_brain_instance is None:
                    cfg = load(str(brain_root / 'config.json'))
                    _cloud_brain_instance = FIABrain(cfg)

                result = await asyncio.to_thread(
                    _cloud_brain_instance.analyze,
                    False,  # NEVER write old/local shadow ledger from this web endpoint.
                )

                if not isinstance(result, dict):
                    raise RuntimeError('INVALID_BRAIN_RESULT')

                result['cloud_endpoint'] = True
                result['base_fia_modified'] = False
                result['forward_oos_modified'] = False
                return result

            except HTTPException:
                raise
            except Exception as exc:
                raise HTTPException(
                    status_code=503,
                    detail=type(exc).__name__ + ': ' + str(exc)[:400],
                ) from exc


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
            _alert=phase25.get('research_alert') or 'NONE'
            _alert_level=str((_alert.get('level') if isinstance(_alert,dict) else _alert) or 'NONE')
            cache={'recorded_at_utc':datetime.now(timezone.utc).isoformat(),'setup_grade':phase25.get('setup_grade'),'confluence_score':phase25.get('confluence_score'),'confluence_alignment':phase25.get('confluence_alignment'),'confluence_completeness':phase25.get('confluence_completeness'),'research_alert':_alert,'research_alert_level':_alert_level,'phase26_prediction_id':result.get('phase26_prediction_id'),'phase26_attached':bool(result.get('phase26_attached')),'research_eligible':phase25.get('research_eligible')}
            _atomic_write_json(_phase25_cache_path(root),cache)
            result['dashboard_phase25_persisted']=True
            return result
        except Exception as exc:
            raise HTTPException(status_code=500,detail=str(exc)) from exc
