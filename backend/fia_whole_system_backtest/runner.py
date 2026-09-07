from __future__ import annotations
import argparse, hashlib, json, sys
from pathlib import Path
from typing import Any, Dict
from .core import (
    atomic_write_json, append_jsonl, brain_fingerprint, build_historical_ledger, case_id,
    discover_historical_rows, extract_outcome_direction, get_timestamp, historical_source_quality,
    load_jsonl_safe, load_trace_outcomes, make_dual_report, nearest_trace_outcome, normalize_direction,
    run_existing_master, sanitize_pti_evidence, summarize_brain_passes, utc_now, verify_record_chain,
    MARKET_OUTCOMES, EVALUATOR_POLICY_VERSION, sha256_obj, brain_runtime_identity,
)

KNOWN_MISSING_HISTORICAL=['L2/L3','VIX/VXN_intraday','US2Y_real_yield_intraday','dealer_gamma','options_skew','ETF_flow','volume_delta','futures_basis']


def _brain_record_from_result(cid,ts,row,brain_fp,ledger,quality,result):
    final=result.get('final') if isinstance(result.get('final'),dict) else {}
    safe=sanitize_pti_evidence(row)
    return {
        'case_id':cid,'timestamp':ts,'horizon_hours':8,
        'historical_evidence_sha256':hashlib.sha256(json.dumps(safe,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest(),
        'brain_fingerprint':brain_fp['digest'],'brain_status':result.get('status'),
        'direction':normalize_direction(final.get('direction')),
        'bullish_probability':final.get('bullish_probability'),'bearish_probability':final.get('bearish_probability'),
        'confidence':final.get('confidence'),'thesis':final.get('thesis'),'brain_result_sha256':result.get('result_sha256'),
        'ledger_sha256':ledger.get('ledger_sha256'),'brain_passes':summarize_brain_passes(result),
        'runtime_events':result.get('runtime_events') or [],'error':result.get('error'),'source_quality':quality,
    }


def main()->int:
    ap=argparse.ArgumentParser(description='CLEAR NASDAQ FINAL FUSION 4H + 8H WHOLE-SYSTEM 1Y BACKTEST')
    ap.add_argument('--project-root',required=True);ap.add_argument('--brain-root',required=True);ap.add_argument('--skip-existing-master',action='store_true')
    a=ap.parse_args(); project=Path(a.project_root).expanduser().resolve(); backend=project/'backend'; brain=Path(a.brain_root).expanduser().resolve()
    if not backend.is_dir(): raise SystemExit(f'backend not found: {backend}')
    if not (brain/'fia_brain').is_dir(): raise SystemExit(f'V6.6 brain not found: {brain}')
    result_dir=backend/'fia_whole_system_backtest/results'; result_dir.mkdir(parents=True,exist_ok=True)
    fp=brain_fingerprint(brain)
    # Resolve the actual local model identity before creating any cache/case IDs.
    sys.path.insert(0,str(brain)); from fia_brain.config import load as load_brain_config; from fia_brain.orchestrator import FIABrain
    cfg=load_brain_config(str(brain/'config.json') if (brain/'config.json').exists() else None)
    if str(cfg.get('model'))!='gpt-oss:20b': raise SystemExit('Unexpected brain model: '+str(cfg.get('model')))
    engine=FIABrain(cfg); health=engine.client.health()
    if not health.get('ok') or not health.get('model_present',True): raise SystemExit('Ollama gpt-oss:20b health failed: '+json.dumps(health))
    runtime_identity=brain_runtime_identity(cfg,health)
    if not runtime_identity.get('model_digest'):
        raise SystemExit('Ollama model digest unavailable; benchmark cache identity cannot be proven')
    runtime_fingerprint=sha256_obj(runtime_identity)
    evaluator_fingerprint=sha256_obj({'brain_fingerprint':fp['digest'],'runtime_fingerprint':runtime_fingerprint,'evaluator_policy':EVALUATOR_POLICY_VERSION})
    tag=evaluator_fingerprint[:12]
    # Evaluator/scoring policy is part of checkpoint identity. Old contaminated
    # dual-horizon checkpoints can never be silently reused after a truth-policy change.
    brain_records=result_dir/f'v6_6_historical_8h_{tag}.jsonl'
    dual_records=result_dir/f'v6_6_dual_resolution_4h_8h_{tag}.jsonl'
    report_path=result_dir/'whole_system_backtest_report.json'; progress_path=result_dir/'progress.json'; master_log=result_dir/'existing_master_1y.log'
    for p,label in ((brain_records,'brain'),(dual_records,'dual-resolution')):
        audit=verify_record_chain(p)
        if not audit.get('ok'): raise SystemExit(f'Existing {label} checkpoint hash-chain failed integrity: '+json.dumps(audit))
    master={'status':'SKIPPED_BY_FLAG'} if a.skip_existing_master else run_existing_master(backend,Path(sys.executable),master_log)
    history_path,rows,history_mode=discover_historical_rows(backend); trace=load_trace_outcomes(backend)
    cases=[]
    for row in rows:
        ts=get_timestamp(row)
        if not ts: continue
        cid=case_id(ts,row,evaluator_fingerprint)
        outcomes={}
        for h in (4,8):
            out,src=extract_outcome_direction(row,h)
            if out not in MARKET_OUTCOMES: out,src=nearest_trace_outcome(ts,trace,h)
            outcomes[f'{h}h']={'direction':out if out in MARKET_OUTCOMES else None,'source':src}
        cases.append((cid,ts,row,outcomes))
    uniq=[];seen=set()
    for c in sorted(cases,key=lambda x:x[1]):
        if c[0] in seen: continue
        seen.add(c[0]);uniq.append(c)
    cases=uniq
    if not cases: raise SystemExit('No historical timestamp cases discovered')

    brain_cache={str(r.get('case_id')):r for r in load_jsonl_safe(brain_records) if r.get('case_id')}
    scored_done={str(r.get('case_id')) for r in load_jsonl_safe(dual_records) if r.get('case_id')}
    reused=0; new_runs=0; total=len(cases)
    report=make_dual_report(backend,brain,history_path,brain_records,dual_records,master,'RUNNING',total,len(scored_done),fp,reused,new_runs); report['history_mode']=history_mode; atomic_write_json(report_path,report)

    print('='*82);print('CLEAR NASDAQ — FINAL FUSION WHOLE-SYSTEM 1Y TIME-TRAVEL BACKTEST');print('='*82)
    print('Historical rows:',history_path);print('Eligible timestamp cases:',total);print('Already dual-scored/resumable:',len(scored_done));print('Existing V6.6 brain-cache records:',len(brain_cache));print('Brain code fingerprint:',fp['digest']);print('Ollama model digest:',runtime_identity.get('model_digest'));print('Runtime fingerprint:',runtime_fingerprint);print('Evaluator policy:',EVALUATOR_POLICY_VERSION);print('Evaluator fingerprint:',evaluator_fingerprint);print('Truth: one locked V6.6 forecast; genuine 4H + 8H market resolutions; strict horizon isolation; no future leakage; missing is not faked');print()

    for idx,(cid,ts,row,outcomes) in enumerate(cases,1):
        if cid in scored_done: continue
        print(f'[{idx}/{total}] {ts} | case={cid} | 4H={outcomes["4h"]["direction"] or "UNRESOLVED"} | 8H={outcomes["8h"]["direction"] or "UNRESOLVED"}',flush=True)
        safe=sanitize_pti_evidence(row); evhash=hashlib.sha256(json.dumps(safe,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()
        cached=brain_cache.get(cid)
        if cached is not None:
            oldhash=cached.get('historical_evidence_sha256')
            if oldhash and oldhash!=evhash: raise SystemExit(f'Cached evidence hash mismatch for {cid}')
            brain_row=cached; reused+=1
        elif not any(outcomes[k]['direction'] in MARKET_OUTCOMES for k in ('4h','8h')):
            brain_row={'case_id':cid,'timestamp':ts,'horizon_hours':8,'historical_evidence_sha256':evhash,'brain_fingerprint':fp['digest'],'brain_status':'NOT_RUN_UNRESOLVED','direction':'NO_EDGE','error':'No genuine 4H or 8H outcome available'}
            _rh=append_jsonl(brain_records,brain_row); brain_row=dict(brain_row); brain_row['record_hash']=_rh; brain_cache[cid]=brain_row
        else:
            try:
                ledger=build_historical_ledger(brain,row,ts,KNOWN_MISSING_HISTORICAL); cov,quality=historical_source_quality(row,KNOWN_MISSING_HISTORICAL)
                result=engine.analyze_ledger(ledger,source_coverage=cov,source_quality=quality,write_shadow=False,case_id=cid,as_of_utc=ts)
                brain_row=_brain_record_from_result(cid,ts,row,fp,ledger,quality,result)
            except Exception as e:
                brain_row={'case_id':cid,'timestamp':ts,'horizon_hours':8,'historical_evidence_sha256':evhash,'brain_fingerprint':fp['digest'],'brain_status':'FAIL_CLOSED','direction':'NO_EDGE','error':type(e).__name__+': '+str(e)[:1000]}
            _rh=append_jsonl(brain_records,brain_row); brain_row=dict(brain_row); brain_row['record_hash']=_rh; brain_cache[cid]=brain_row; new_runs+=1

        dual={
            'case_id':cid,'timestamp':ts,'brain_fingerprint':fp['digest'],'brain_record_hash':brain_row.get('record_hash'),
            'historical_evidence_sha256':evhash,'brain_status':brain_row.get('brain_status'),'direction':brain_row.get('direction'),
            'bullish_probability':brain_row.get('bullish_probability'),'bearish_probability':brain_row.get('bearish_probability'),'confidence':brain_row.get('confidence'),
            'brain_result_sha256':brain_row.get('brain_result_sha256'),'brain_passes':brain_row.get('brain_passes') or {},'runtime_events':brain_row.get('runtime_events') or [],
            'error':brain_row.get('error'),'outcomes':outcomes,
            'forecast_semantics':'ONE_LOCKED_V6_6_WHOLE_SYSTEM_FORECAST__DUAL_GENUINE_RESOLUTION_4H_8H',
        }
        append_jsonl(dual_records,dual); scored_done.add(cid)
        report=make_dual_report(backend,brain,history_path,brain_records,dual_records,master,'RUNNING',total,len(scored_done),fp,reused,new_runs); report['history_mode']=history_mode; report['evaluator_policy_version']=EVALUATOR_POLICY_VERSION; report['evaluator_fingerprint']=evaluator_fingerprint; report['runtime_fingerprint']=runtime_fingerprint; report['runtime_identity']=runtime_identity; atomic_write_json(report_path,report)
        atomic_write_json(progress_path,{'state':'RUNNING','completed':len(scored_done),'total':total,'reused_brain_records':reused,'new_brain_runs':new_runs,'last_case_id':cid,'updated_at_utc':utc_now()})

    final=make_dual_report(backend,brain,history_path,brain_records,dual_records,master,'COMPLETE',total,len(scored_done),fp,reused,new_runs); final['history_mode']=history_mode; final['evaluator_policy_version']=EVALUATOR_POLICY_VERSION; final['evaluator_fingerprint']=evaluator_fingerprint; final['runtime_fingerprint']=runtime_fingerprint; final['runtime_identity']=runtime_identity; final['brain_version']=getattr(__import__('fia_brain'),'__version__','unknown'); atomic_write_json(report_path,final)
    atomic_write_json(progress_path,{'state':final.get('state'),'final':bool(final.get('final')),'completed':len(scored_done),'total':total,'reused_brain_records':reused,'new_brain_runs':new_runs,'updated_at_utc':utc_now(),'report_sha256':final['report_sha256'],'brain_fingerprint':fp['digest'],'runtime_fingerprint':runtime_fingerprint,'evaluator_fingerprint':evaluator_fingerprint})
    print();print('='*82);print('FINAL WHOLE-SYSTEM DUAL-HORIZON BACKTEST COMPLETE')
    for h in ('4h','8h'):
        s=final['horizons'][h];print(f'{h.upper()} WIN RATE = {s.get("win_rate")} | W={s.get("wins")} L={s.get("losses")} NO_EDGE={s.get("no_edge")} FAIL_CLOSED={s.get("fail_closed")} COVERAGE={s.get("directional_coverage_pct")} BRIER={s.get("brier")}')
    print('REUSED BRAIN RECORDS =',reused,'| NEW BRAIN RUNS =',new_runs);print('REPORT =',report_path);print('REPORT SHA256 =',final['report_sha256']);print('='*82)
    return 0 if final.get('final') else 3

if __name__=='__main__': raise SystemExit(main())
