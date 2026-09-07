from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import traceback
from pathlib import Path
from typing import Any, Dict, List

from .core import (
    PRIMARY_HORIZON_HOURS, atomic_write_json, brain_fingerprint, build_historical_ledger, case_id,
    discover_historical_rows, existing_case_ids, extract_outcome_direction,
    get_timestamp, historical_source_quality, load_jsonl_safe, load_trace_outcomes,
    make_report, nearest_trace_outcome, run_existing_master, sanitize_pti_evidence,
    sha256_file, summarize_brain_passes, utc_now, append_jsonl, normalize_direction, verify_record_chain,
)

KNOWN_MISSING_HISTORICAL=[
    'L2/L3',
    'VIX/VXN_intraday',
    'US2Y_real_yield_intraday',
    'dealer_gamma',
    'options_skew',
    'ETF_flow',
    'volume_delta',
    'futures_basis',
]


def main() -> int:
    ap=argparse.ArgumentParser(description='CLEAR NASDAQ FINAL WHOLE-SYSTEM 1Y BACKTEST')
    ap.add_argument('--project-root',required=True)
    ap.add_argument('--brain-root',required=True)
    ap.add_argument('--skip-existing-master',action='store_true')
    args=ap.parse_args()
    project=Path(args.project_root).expanduser().resolve()
    backend=project/'backend'; brain=Path(args.brain_root).expanduser().resolve()
    if not backend.is_dir(): raise SystemExit(f'backend not found: {backend}')
    if not (brain/'fia_brain').is_dir(): raise SystemExit(f'V6.6 brain not found: {brain}')
    python=Path(sys.executable)
    result_dir=backend/'fia_whole_system_backtest/results';result_dir.mkdir(parents=True,exist_ok=True)
    brain_fp=brain_fingerprint(brain)
    records=result_dir/f"v6_6_historical_8h_{brain_fp['digest'][:12]}.jsonl"
    report_path=result_dir/'whole_system_backtest_report.json'
    progress_path=result_dir/'progress.json'
    master_log=result_dir/'existing_master_1y.log'

    chain=verify_record_chain(records)
    if not chain.get('ok'):
        raise SystemExit('Existing checkpoint hash-chain failed integrity: '+json.dumps(chain))

    # Run existing Phase33-37 master first. Its failures/blocked institutional inputs are recorded,
    # never silently converted into a pass.
    master={'status':'SKIPPED_BY_FLAG'} if args.skip_existing_master else run_existing_master(backend,python,master_log)

    history_path,rows,history_mode=discover_historical_rows(backend)
    trace=load_trace_outcomes(backend)
    cases=[]
    for row in rows:
        ts=get_timestamp(row)
        if not ts: continue
        out,src=extract_outcome_direction(row,PRIMARY_HORIZON_HOURS)
        if out not in {'BULLISH','BEARISH'}:
            out,src=nearest_trace_outcome(ts,trace,PRIMARY_HORIZON_HOURS)
        cid=case_id(ts,row,brain_fp['digest'])
        cases.append((cid,ts,row,out,src))
    # Deterministic de-duplication by evidence-bound case id.
    uniq=[];seen=set()
    for c in sorted(cases,key=lambda x:x[1]):
        if c[0] in seen: continue
        seen.add(c[0]);uniq.append(c)
    cases=uniq
    if not cases: raise SystemExit('No historical cases with timestamps discovered')

    # Import the ACTUAL installed V6.6 brain. Nothing is copied or reimplemented here.
    sys.path.insert(0,str(brain))
    from fia_brain.config import load as load_brain_config
    from fia_brain.orchestrator import FIABrain
    cfg=load_brain_config(str(brain/'config.json') if (brain/'config.json').exists() else None)
    model=str(cfg.get('model'))
    if model!='gpt-oss:20b': raise SystemExit(f'Unexpected brain model: {model}')
    brain_engine=FIABrain(cfg)
    health=brain_engine.client.health()
    if not health.get('ok') or not health.get('model_present',True):
        raise SystemExit('Ollama gpt-oss:20b health check failed: '+json.dumps(health))

    done=existing_case_ids(records)
    total=len(cases)
    initial_report=make_report(backend,brain,history_path,records,master,'RUNNING',total,len(done),brain_fp)
    initial_report['history_mode']=history_mode
    atomic_write_json(report_path,initial_report)

    print('='*78)
    print('CLEAR NASDAQ — FINAL WHOLE-SYSTEM 1Y TIME-TRAVEL BACKTEST')
    print('='*78)
    print('Historical rows:',history_path)
    print('Eligible timestamp cases:',total)
    print('Already completed/resumable:',len(done))
    print('Brain:',model,'from',brain,'fingerprint=',brain_fp['digest'])
    print('Truth policy: PTI only; no future leakage; missing is not faked')
    print()

    for idx,(cid,ts,row,outcome,outcome_src) in enumerate(cases,1):
        if cid in done:
            continue
        print(f'[{idx}/{total}] {ts} | case={cid} | outcome={outcome or "UNRESOLVED"}',flush=True)
        item:Dict[str,Any]={
            'case_id':cid,'timestamp':ts,'horizon_hours':PRIMARY_HORIZON_HOURS,
            'outcome_direction':outcome,'outcome_source':outcome_src,
            'historical_evidence_sha256':None,'brain_fingerprint':brain_fp['digest'],
        }
        if outcome not in {'BULLISH','BEARISH'}:
            item.update({'brain_status':'NOT_RUN_UNRESOLVED','direction':'NO_EDGE','error':'No genuine 8H outcome available'})
            append_jsonl(records,item);done.add(cid)
        else:
            try:
                safe=sanitize_pti_evidence(row)
                import hashlib
                item['historical_evidence_sha256']=hashlib.sha256(json.dumps(safe,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()
                ledger=build_historical_ledger(brain,row,ts,KNOWN_MISSING_HISTORICAL)
                cov,quality=historical_source_quality(row,KNOWN_MISSING_HISTORICAL)
                result=brain_engine.analyze_ledger(ledger,source_coverage=cov,source_quality=quality,write_shadow=False,case_id=cid,as_of_utc=ts)
                final=result.get('final') if isinstance(result.get('final'),dict) else {}
                item.update({
                    'brain_status':result.get('status'),
                    'direction':normalize_direction(final.get('direction')),
                    'bullish_probability':final.get('bullish_probability'),
                    'bearish_probability':final.get('bearish_probability'),
                    'confidence':final.get('confidence'),
                    'thesis':final.get('thesis'),
                    'brain_result_sha256':result.get('result_sha256'),
                    'ledger_sha256':ledger.get('ledger_sha256'),
                    'brain_passes':summarize_brain_passes(result),
                    'runtime_events':result.get('runtime_events') or [],
                    'error':result.get('error'),
                    'source_quality':quality,
                })
            except Exception as e:
                item.update({'brain_status':'FAIL_CLOSED','direction':'NO_EDGE','error':type(e).__name__+': '+str(e)[:1000]})
            append_jsonl(records,item);done.add(cid)
        report=make_report(backend,brain,history_path,records,master,'RUNNING',total,len(done),brain_fp)
        report['history_mode']=history_mode
        atomic_write_json(report_path,report)
        atomic_write_json(progress_path,{'state':'RUNNING','completed':len(done),'total':total,'last_case_id':cid,'updated_at_utc':utc_now()})

    final_report=make_report(backend,brain,history_path,records,master,'COMPLETE',total,len(done),brain_fp)
    final_report['history_mode']=history_mode
    final_report['brain_version']=getattr(__import__('fia_brain'),'__version__','unknown')
    atomic_write_json(report_path,final_report)
    atomic_write_json(progress_path,{'state':final_report.get('state'),'final':bool(final_report.get('final')),'completed':len(done),'total':total,'updated_at_utc':utc_now(),'report_sha256':final_report['report_sha256'],'brain_fingerprint':brain_fp['digest']})
    print()
    print('='*78)
    print('✅ FINAL WHOLE-SYSTEM BACKTEST COMPLETE')
    s=final_report['historical_1y_whole_system']
    print('WIN RATE =',s.get('win_rate'))
    print('WINS =',s.get('wins'),'LOSSES =',s.get('losses'))
    print('NO_EDGE =',s.get('no_edge'),'FAIL_CLOSED =',s.get('fail_closed'),'UNRESOLVED =',s.get('unresolved'))
    print('DIRECTIONAL COVERAGE =',s.get('directional_coverage_pct'))
    print('BRIER =',s.get('brier'),'N =',s.get('brier_n'))
    print('REPORT =',report_path)
    print('REPORT SHA256 =',final_report['report_sha256'])
    print('='*78)
    return 0 if final_report.get('final') else 3

if __name__=='__main__':
    raise SystemExit(main())
