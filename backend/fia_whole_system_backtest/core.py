from __future__ import annotations

import csv
import hashlib
import json
import math
import os
import re
import statistics
import subprocess
import sys
import time
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

SCHEMA_VERSION = "CLEAR_NASDAQ_WHOLE_SYSTEM_BACKTEST_V2_DUAL_4H_8H"
PRIMARY_HORIZON_HOURS = 8
DIRECTIONAL = {"BULLISH", "BEARISH"}
MARKET_OUTCOMES = {"BULLISH", "BEARISH", "NEUTRAL"}
ABSTAIN = {"NEUTRAL", "NO_EDGE", "NO-EDGE", "NONE", ""}
EVALUATOR_POLICY_VERSION = "CLEAR_NASDAQ_EVALUATOR_TRUTH_V3_STRICT_HORIZON_NEUTRAL"

# Evaluator/future semantics that are always forbidden inside historical model evidence.
ALWAYS_LEAK_TOKENS = {
    "future", "outcome", "correct", "resolved", "resolution", "pnl", "mfe", "mae",
    "ground_truth", "truth_direction", "future_price", "forward_return", "next_price", "next_return",
}

OUTCOME_TOKENS = ("outcome", "actual", "future", "resolved", "truth", "label")
TS_KEYS = (
    "timestamp", "forecast_timestamp", "created_at", "generated_at", "time", "datetime", "as_of_utc",
)
BASE_DIRECTION_KEYS = (
    "direction", "forecast_direction", "prediction_direction", "predicted_direction", "prediction",
)
ENTRY_PRICE_KEYS = ("entry_price", "price", "nq_price", "close")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    h=hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024), b''):
            h.update(chunk)
    return h.hexdigest()


def canonical(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def sha256_obj(obj: Any) -> str:
    return sha256_bytes(canonical(obj).encode('utf-8'))


def parse_dt(value: Any) -> Optional[datetime]:
    if value is None: return None
    s=str(value).strip()
    if not s: return None
    if s.endswith('Z'): s=s[:-1]+'+00:00'
    try:
        d=datetime.fromisoformat(s)
    except Exception:
        return None
    if d.tzinfo is None: d=d.replace(tzinfo=timezone.utc)
    return d.astimezone(timezone.utc)


def normalize_direction(value: Any) -> str:
    s=str(value or '').strip().upper().replace('LONG','BULLISH').replace('SHORT','BEARISH')
    aliases={
        'UP':'BULLISH','BUY':'BULLISH','BULL':'BULLISH','POSITIVE':'BULLISH',
        'DOWN':'BEARISH','SELL':'BEARISH','BEAR':'BEARISH','NEGATIVE':'BEARISH',
        'NO EDGE':'NO_EDGE','NO-EDGE':'NO_EDGE','FLAT':'NEUTRAL',
    }
    return aliases.get(s,s)


def safe_float(v: Any) -> Optional[float]:
    try:
        if v is None or isinstance(v,bool): return None
        x=float(v)
        return x if math.isfinite(x) else None
    except Exception:
        return None


def flatten(obj: Any, prefix: str='') -> Iterable[Tuple[str,Any]]:
    if isinstance(obj, Mapping):
        for k,v in obj.items():
            p=f'{prefix}.{k}' if prefix else str(k)
            yield from flatten(v,p)
    elif isinstance(obj,list):
        for i,v in enumerate(obj):
            p=f'{prefix}[{i}]'
            yield from flatten(v,p)
    else:
        yield prefix,obj


def path_tokens(path: str) -> List[str]:
    return [x for x in re.split(r'[^a-z0-9]+', path.lower()) if x]


def _contains_horizon_semantics(toks: set, path: str) -> bool:
    if any(t in toks for t in ("4h", "8h", "h4", "h8", "horizon")):
        return True
    return bool(re.search(r"(?:^|[^0-9])(4|8)h(?:[^a-z0-9]|$)", path.lower()))


def is_leak_path(path: str) -> bool:
    """Block evaluator/future labels without deleting legitimate contemporaneous facts.

    Preserved examples: macro.cpi.actual, fed.target_rate, realized_volatility.
    Blocked examples: actual_direction_8h, target_8h, future_price, correct_8h.
    """
    p=path.lower(); toks=set(path_tokens(p)); compact=p.replace("-","_")
    if any(x in compact for x in ("forward_return","future_price","ground_truth","truth_direction","next_price","next_return")):
        return True
    if toks & ALWAYS_LEAK_TOKENS:
        return True
    if "actual" in toks and (any(x in toks for x in ("direction","price","close","return","outcome","label")) or _contains_horizon_semantics(toks,p)):
        return True
    if "target" in toks and (any(x in toks for x in ("direction","outcome","label","future","return")) or _contains_horizon_semantics(toks,p)):
        return True
    if "realized" in toks and (any(x in toks for x in ("return","outcome","direction","future","pnl")) or _contains_horizon_semantics(toks,p)):
        return True
    if "result" in toks and any(x in toks for x in ("outcome","correct","direction","pnl","future")):
        return True
    return False


def sanitize_pti_evidence(row: Mapping[str,Any]) -> Dict[str,Any]:
    """Recursively remove evaluator-only/future fields. Never imputes missing values."""
    def rec(x: Any, prefix: str='') -> Any:
        if isinstance(x, Mapping):
            out={}
            for k,v in x.items():
                p=f'{prefix}.{k}' if prefix else str(k)
                if is_leak_path(p):
                    continue
                out[str(k)]=rec(v,p)
            return out
        if isinstance(x,list):
            return [rec(v,f'{prefix}[{i}]') for i,v in enumerate(x)]
        if isinstance(x,(str,int,float,bool)) or x is None:
            if isinstance(x,float) and not math.isfinite(x): return None
            return x
        return str(x)
    return rec(row)


def assert_no_leak_payload(payload: Mapping[str,Any]) -> None:
    bad=[]
    for p,_ in flatten(payload):
        if is_leak_path(p): bad.append(p)
    if bad:
        raise RuntimeError('historical evidence leakage guard failed: '+', '.join(bad[:8]))


def get_timestamp(row: Mapping[str,Any]) -> Optional[str]:
    flat=list(flatten(row))
    scored=[]
    for p,v in flat:
        pl=p.lower()
        score=0
        if pl in TS_KEYS: score+=20
        if any(pl.endswith('.'+k) or pl==k for k in TS_KEYS): score+=12
        if 'forecast' in pl: score+=5
        d=parse_dt(v)
        if d is not None and score>0: scored.append((score,d,p))
    if not scored:
        for p,v in flat:
            d=parse_dt(v)
            if d is not None and ('time' in p.lower() or 'date' in p.lower()): scored.append((1,d,p))
    if not scored: return None
    scored.sort(key=lambda x:(-x[0],x[1]))
    return scored[0][1].isoformat()


def _horizon_match(path: str,hours: int) -> int:
    p=path.lower().replace('_','').replace('-','')
    tags=(f'{hours}h',f'{hours}hour',f'horizon{hours}')
    return 1 if any(t in p for t in tags) else 0


def extract_outcome_direction(row: Mapping[str,Any], hours: int=8) -> Tuple[Optional[str],str]:
    """Extract the requested horizon outcome without cross-horizon substitution.

    A 4H evaluator may never consume an 8H label (and vice versa). Explicit
    NEUTRAL outcomes are preserved as real market outcomes instead of silently
    disappearing from the denominator.
    """
    flat=list(flatten(row))
    candidates=[]
    for p,v in flat:
        pl=p.lower()
        # If a path carries explicit 4H/8H semantics, it MUST match the requested horizon.
        has_horizon=bool(re.search(r'(?:^|[^0-9])(4|8)h(?:[^a-z0-9]|$)',pl)) or any(t in set(path_tokens(pl)) for t in {'4h','8h','h4','h8'})
        if has_horizon and not _horizon_match(pl,hours):
            continue
        d=normalize_direction(v)
        if d not in MARKET_OUTCOMES: continue
        score=0
        if _horizon_match(pl,hours): score+=40
        if any(t in pl for t in OUTCOME_TOKENS): score+=25
        if 'direction' in pl: score+=10
        if 'prediction' in pl or 'forecast' in pl: score-=30
        # Horizon-specific evaluation requires explicit outcome semantics.
        if score>=25: candidates.append((score,d,p))
    if candidates:
        candidates.sort(key=lambda x:(-x[0],x[2]))
        return candidates[0][1],candidates[0][2]

    # Price-based evaluator fallback if explicit outcome direction is absent.
    entry=None; future=None; entry_path=''; future_path=''
    for p,v in flat:
        x=safe_float(v)
        if x is None: continue
        pl=p.lower()
        if entry is None and any(pl.endswith(k) or pl.endswith('.'+k) for k in ENTRY_PRICE_KEYS) and not is_leak_path(pl):
            entry=x; entry_path=p
        if _horizon_match(pl,hours) and ('future' in pl or 'actual' in pl or 'resolved' in pl) and ('price' in pl or 'close' in pl):
            future=x; future_path=p
    if entry is not None and future is not None:
        if future>entry: return 'BULLISH', f'{entry_path} -> {future_path}'
        if future<entry: return 'BEARISH', f'{entry_path} -> {future_path}'
        return 'NEUTRAL', f'{entry_path} -> {future_path}'

    # Last-resort reconstruction from contemporaneous base direction + correctness flag.
    # This can reconstruct only a binary opposite. It never invents NEUTRAL.
    base=None; correct=None; correct_path=''
    for p,v in flat:
        pl=p.lower(); d=normalize_direction(v)
        if base is None and d in DIRECTIONAL and any(k in pl for k in BASE_DIRECTION_KEYS) and not any(t in pl for t in OUTCOME_TOKENS):
            base=d
        if _horizon_match(pl,hours) and 'correct' in pl:
            if isinstance(v,bool): correct=v; correct_path=p
            elif str(v).strip().lower() in {'true','1','yes'}: correct=True; correct_path=p
            elif str(v).strip().lower() in {'false','0','no'}: correct=False; correct_path=p
    if base and correct is not None:
        if correct: return base, f'reconstructed:{correct_path}'
        return ('BEARISH' if base=='BULLISH' else 'BULLISH'), f'reconstructed:{correct_path}'
    return None,''


def load_jsonl(path: Path) -> List[Dict[str,Any]]:
    out=[]
    for line in path.read_text(encoding='utf-8').splitlines():
        line=line.strip()
        if not line: continue
        obj=json.loads(line)
        if isinstance(obj,dict): out.append(obj)
    return out


def load_csv(path: Path) -> List[Dict[str,Any]]:
    with path.open(newline='',encoding='utf-8-sig') as f: return list(csv.DictReader(f))


def discover_historical_rows(backend: Path) -> Tuple[Path,List[Dict[str,Any]],str]:
    candidates=[
        backend/'fia_phase35/data/enriched_pti.jsonl',
        backend/'fia_backtest_phase33/results/phase33_full_replay_1y.csv',
        backend/'fia_backtest_phase35/results/phase35_full_replay_trace.csv',
    ]
    for p in candidates:
        if not p.exists(): continue
        try:
            rows=load_jsonl(p) if p.suffix=='.jsonl' else load_csv(p)
        except Exception:
            continue
        if rows:
            return p,rows,('PHASE35_PTI' if 'enriched_pti' in p.name else 'FALLBACK_ROW_HISTORY')
    raise FileNotFoundError('No row-level historical PTI dataset found. Expected Phase35 enriched_pti.jsonl or Phase33/35 replay CSV.')


def load_trace_outcomes(backend: Path) -> List[Dict[str,Any]]:
    for p in [backend/'fia_backtest_phase35/results/phase35_full_replay_trace.csv',backend/'fia_backtest_phase33/results/phase33_full_replay_1y.csv']:
        if p.exists():
            try:return load_csv(p)
            except Exception:pass
    return []


def nearest_trace_outcome(ts: str, trace: Sequence[Mapping[str,Any]], hours: int=8) -> Tuple[Optional[str],str]:
    target=parse_dt(ts)
    if target is None:return None,''
    best=None
    for row in trace:
        rts=get_timestamp(row)
        rd=parse_dt(rts)
        if rd is None:continue
        delta=abs((rd-target).total_seconds())
        if delta>300:continue
        # honor horizon column when present
        horiz=' '.join(str(v) for k,v in row.items() if 'horizon' in k.lower()).lower()
        if horiz and str(hours) not in horiz: continue
        d,src=extract_outcome_direction(row,hours)
        if d in MARKET_OUTCOMES and (best is None or delta<best[0]): best=(delta,d,'trace:'+src)
    return (best[1],best[2]) if best else (None,'')


def build_historical_ledger(brain_root: Path, row: Mapping[str,Any], ts: str, known_missing: Sequence[str]) -> Dict[str,Any]:
    sys.path.insert(0,str(brain_root)) if str(brain_root) not in sys.path else None
    from fia_brain.evidence import build_ledger, validate_ledger_integrity
    try:
        from fia_brain.util import sha256_obj as brain_sha256_obj
    except Exception:
        brain_sha256_obj=sha256_obj
    safe=sanitize_pti_evidence(row)
    assert_no_leak_payload(safe)
    payload={
        'historical_time_travel': {
            'as_of_utc': ts,
            'horizon_hours': PRIMARY_HORIZON_HOURS,
            'mode': 'POINT_IN_TIME_ONLY',
            'missing_data_policy': 'MISSING_NOT_FAKED',
            'known_unavailable_historical_inputs': list(known_missing),
        },
        'phase35_point_in_time_evidence': safe,
    }
    snapshot={
        'captured_at_utc':ts,
        'capture_started_at_utc':ts,
        'capture_elapsed_ms':0.0,
        'base_url':'historical://phase35-point-in-time',
        'atomic_evidence_endpoint':'historical://whole-system',
        'endpoint_health':{'historical://whole-system':{'ok':True,'status':200,'error':None,'elapsed_ms':0.0}},
        'payloads':{'historical://whole-system':payload},
        'health_payloads':{},
    }
    snapshot['snapshot_sha256']=brain_sha256_obj(snapshot)
    ledger=build_ledger(snapshot,max_records=360,max_chars=64000)
    ok,errs=validate_ledger_integrity(ledger)
    if not ok: raise RuntimeError('historical ledger integrity failed: '+';'.join(errs))
    # Strong independent guarantee: no forbidden evaluator field survived into a ledger path.
    bad=[r.get('path','') for r in ledger.get('records',[]) if is_leak_path(str(r.get('path','')))]
    if bad: raise RuntimeError('leak path reached V6 ledger: '+', '.join(bad[:5]))
    return ledger


def extract_feature_coverage(row: Mapping[str,Any]) -> Optional[float]:
    for p,v in flatten(row):
        pl=p.lower()
        if 'coverage' in pl and ('feature' in pl or 'predictive' in pl):
            x=safe_float(v)
            if x is not None:
                if x>1:x/=100.0
                if 0<=x<=1:return x
    return None


def historical_source_quality(row: Mapping[str,Any], known_missing: Sequence[str]) -> Tuple[Dict[str,Any],Dict[str,Any]]:
    cov=extract_feature_coverage(row)
    if cov is None:
        scalars=[v for p,v in flatten(sanitize_pti_evidence(row)) if not isinstance(v,(dict,list))]
        if scalars: cov=sum(v not in (None,'','N/A','NA') for v in scalars)/len(scalars)
    cov=float(cov if cov is not None else 0.0)
    # Confidence cap mirrors current system's degraded cap only as a conservative historical emulation.
    # It changes confidence, not the direction scoring denominator.
    degraded=bool(known_missing) or cov<0.95
    cap=45.0 if degraded else 100.0
    quality={
        'ok':True,
        'historical_emulation':True,
        'historical_pti_feature_coverage':round(cov,6),
        'missing_sources':list(known_missing),
        'warnings':(['historical_optional_inputs_unavailable'] if known_missing else []),
        'confidence_cap':cap,
        'status':'DEGRADED' if degraded else 'LIVE_EQUIVALENT_COMPLETE',
        'missing_data_policy':'MISSING_NOT_FAKED',
    }
    coverage={'historical_locked_case':True,'coverage':round(cov,6),'point_in_time_only':True}
    return coverage,quality


def brier(p_bull: float,outcome: str) -> float:
    y=1.0 if outcome=='BULLISH' else 0.0
    p=max(0.0,min(1.0,p_bull/100.0))
    return (p-y)**2


def wilson(k:int,n:int,z:float=1.959963984540054) -> Optional[List[float]]:
    if n<=0:return None
    p=k/n; den=1+z*z/n
    center=(p+z*z/(2*n))/den
    half=z*math.sqrt((p*(1-p)+z*z/(4*n))/n)/den
    return [round(100*max(0,center-half),2),round(100*min(1,center+half),2)]


def score_records(records: Sequence[Mapping[str,Any]]) -> Dict[str,Any]:
    wins=losses=no_edge=fail_closed=unresolved=neutral_outcomes=0
    briers=[]; directional=[]; all_eligible=0; neutral_brier_excluded=0
    calibration=defaultdict(lambda:{'n':0,'p_sum':0.0,'y_sum':0.0})
    by_week=defaultdict(lambda:{'wins':0,'losses':0,'no_edge':0,'fail_closed':0,'eligible':0,'neutral_outcomes':0})
    by_month=defaultdict(lambda:{'wins':0,'losses':0,'no_edge':0,'fail_closed':0,'eligible':0,'neutral_outcomes':0})
    max_loss_streak=loss_streak=0
    for r in records:
        out=normalize_direction(r.get('outcome_direction'))
        if out not in MARKET_OUTCOMES:
            unresolved+=1; continue
        all_eligible+=1
        ts=parse_dt(r.get('timestamp'))
        week=(f'{ts.isocalendar().year}-W{ts.isocalendar().week:02d}' if ts else 'UNKNOWN')
        month=(ts.strftime('%Y-%m') if ts else 'UNKNOWN')
        by_week[week]['eligible']+=1; by_month[month]['eligible']+=1
        if out=='NEUTRAL':
            neutral_outcomes+=1; by_week[week]['neutral_outcomes']+=1; by_month[month]['neutral_outcomes']+=1
        status=str(r.get('brain_status') or '').upper()
        d=normalize_direction(r.get('direction'))
        directional_call=False
        call_loss=False
        if status!='OK':
            fail_closed+=1; by_week[week]['fail_closed']+=1; by_month[month]['fail_closed']+=1
        elif d not in DIRECTIONAL:
            no_edge+=1; by_week[week]['no_edge']+=1; by_month[month]['no_edge']+=1
        else:
            directional_call=True; directional.append(r)
            if d==out and out in DIRECTIONAL:
                wins+=1; by_week[week]['wins']+=1; by_month[month]['wins']+=1
            else:
                # A directional call into a genuinely neutral market outcome is a loss,
                # not an unresolved sample silently removed from the denominator.
                losses+=1; call_loss=True; by_week[week]['losses']+=1; by_month[month]['losses']+=1
        if directional_call:
            loss_streak = loss_streak + 1 if call_loss else 0
            max_loss_streak=max(max_loss_streak,loss_streak)
        pb=safe_float(r.get('bullish_probability'))
        if status=='OK' and pb is not None:
            if out in DIRECTIONAL:
                br=brier(pb,out); briers.append(br)
                bucket=min(9,max(0,int(min(pb,99.999)//10)))
                c=calibration[f'{bucket*10:02d}-{bucket*10+10:02d}']
                c['n']+=1;c['p_sum']+=pb/100;c['y_sum']+=(1 if out=='BULLISH' else 0)
            else:
                neutral_brier_excluded+=1
    n_dir=wins+losses
    win_rate=round(100*wins/n_dir,2) if n_dir else None
    coverage=round(100*n_dir/all_eligible,2) if all_eligible else None
    effective=round(100*wins/all_eligible,2) if all_eligible else None
    def finish_groups(src):
        out=[]
        for key in sorted(src):
            x=dict(src[key]); n=x['wins']+x['losses']
            x.update({'period':key,'directional_n':n,'win_rate':round(100*x['wins']/n,2) if n else None})
            out.append(x)
        return out
    cal=[]
    for key in sorted(calibration):
        c=calibration[key]
        cal.append({'bucket':key,'n':c['n'],'mean_predicted_bullish':round(100*c['p_sum']/c['n'],2),'observed_bullish':round(100*c['y_sum']/c['n'],2)})
    return {
        'eligible_outcomes':all_eligible,
        'directional_resolved_calls':n_dir,
        'wins':wins,'losses':losses,'no_edge':no_edge,'fail_closed':fail_closed,'unresolved':unresolved,
        'neutral_market_outcomes':neutral_outcomes,
        'win_rate':win_rate,
        'win_rate_denominator':n_dir,
        'directional_coverage_pct':coverage,
        'effective_wins_over_all_eligible_pct':effective,
        'wilson95_win_rate':wilson(wins,n_dir),
        'brier':round(statistics.fmean(briers),6) if briers else None,
        'brier_n':len(briers),
        'neutral_outcomes_excluded_from_binary_brier':neutral_brier_excluded,
        'calibration':cal,
        'max_consecutive_directional_losses':max_loss_streak,
        'financial_mdd_pct':None,
        'financial_mdd_status':'UNAVAILABLE_NO_LOCKED_EXECUTION_AND_POSITION_SIZING_POLICY',
        'weekly':finish_groups(by_week),
        'monthly':finish_groups(by_month),
        'truth_note':'Win rate = wins / (wins + losses) for resolved directional calls. A directional call into a genuine NEUTRAL market outcome is a loss. NO_EDGE and FAIL_CLOSED remain separate. Binary Brier/calibration exclude NEUTRAL outcomes rather than treating them as bearish. Financial MDD is withheld until a locked execution/position-sizing policy exists.',
    }


def atomic_write_json(path: Path,obj: Any) -> None:
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix(path.suffix+'.tmp')
    tmp.write_text(json.dumps(obj,indent=2,ensure_ascii=False,allow_nan=False)+'\n',encoding='utf-8')
    os.replace(tmp,path)


ZERO_HASH = "0" * 64

def repair_incomplete_tail(path: Path) -> bool:
    """Repair only an interrupted final JSONL write; never middle corruption."""
    if not path.exists() or path.stat().st_size == 0: return False
    data=path.read_bytes()
    if data.endswith(b"\n"): return False
    pos=data.rfind(b"\n")
    if pos < 0: raise RuntimeError("checkpoint has no complete JSONL record; manual audit required")
    tail=data[pos+1:]
    try: json.loads(tail.decode("utf-8"))
    except Exception:
        path.write_bytes(data[:pos+1]); return True
    path.write_bytes(data+b"\n"); return True

def verify_record_chain(path: Path) -> Dict[str,Any]:
    if not path.exists(): return {"ok":True,"records":0,"head":ZERO_HASH,"tail_repaired":False}
    repaired=repair_incomplete_tail(path); prev=ZERO_HASH; n=0
    for line_no,line in enumerate(path.read_text(encoding="utf-8").splitlines(),1):
        if not line.strip(): continue
        try: obj=json.loads(line)
        except Exception as e: return {"ok":False,"records":n,"line":line_no,"reason":"INVALID_JSON","error":repr(e)}
        if not isinstance(obj,dict): return {"ok":False,"records":n,"line":line_no,"reason":"NON_OBJECT_RECORD"}
        recorded=str(obj.get("record_hash") or ""); recorded_prev=str(obj.get("prev_record_hash") or "")
        if recorded_prev != prev: return {"ok":False,"records":n,"line":line_no,"reason":"PREV_HASH_MISMATCH","expected":prev,"found":recorded_prev}
        body=dict(obj); body.pop("record_hash",None); calc=sha256_obj(body)
        if calc != recorded: return {"ok":False,"records":n,"line":line_no,"reason":"RECORD_HASH_MISMATCH","expected":calc,"found":recorded}
        prev=recorded; n+=1
    return {"ok":True,"records":n,"head":prev,"tail_repaired":repaired}

def append_jsonl(path: Path,obj: Any) -> str:
    path.parent.mkdir(parents=True,exist_ok=True)
    audit=verify_record_chain(path)
    if not audit.get("ok"): raise RuntimeError("checkpoint integrity failure before append: "+canonical(audit))
    body=dict(obj); body["prev_record_hash"]=audit.get("head") or ZERO_HASH; body.pop("record_hash",None); body["record_hash"]=sha256_obj(body)
    with path.open("a",encoding="utf-8") as f:
        f.write(canonical(body)+"\n"); f.flush(); os.fsync(f.fileno())
    return body["record_hash"]

def load_jsonl_safe(path: Path) -> List[Dict[str,Any]]:
    if not path.exists(): return []
    audit=verify_record_chain(path)
    if not audit.get("ok"): raise RuntimeError("checkpoint integrity failure: "+canonical(audit))
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]

def existing_case_ids(path: Path) -> set:
    return {str(r.get("case_id")) for r in load_jsonl_safe(path) if r.get("case_id")}

def brain_fingerprint(brain_root: Path) -> Dict[str,Any]:
    files=[]
    for q in sorted((brain_root/"fia_brain").rglob("*.py")):
        if "__pycache__" in q.parts: continue
        files.append({"path":str(q.relative_to(brain_root)),"sha256":sha256_file(q)})
    cfg=brain_root/"config.json"
    if cfg.exists(): files.append({"path":"config.json","sha256":sha256_file(cfg)})
    return {"algorithm":"sha256","digest":sha256_obj(files),"files":files}


def brain_runtime_identity(config: Mapping[str,Any], health: Mapping[str,Any]) -> Dict[str,Any]:
    """Identity of the actual local inference runtime used by the benchmark.

    Code/config fingerprint alone is insufficient: a different Ollama model digest
    or context/output policy must never silently reuse the same historical cache.
    """
    details=health.get('model_details') if isinstance(health.get('model_details'),dict) else {}
    return {
        'model':str(config.get('model') or ''),
        'model_digest':health.get('model_digest'),
        'model_size':health.get('model_size'),
        'model_details':details,
        'num_ctx':config.get('num_ctx'),
        'num_predict':config.get('num_predict'),
        'reasoning_effort':config.get('reasoning_effort'),
        'specialist_timeout_seconds':config.get('specialist_timeout_seconds'),
        'core_timeout_seconds':config.get('core_timeout_seconds'),
    }

def case_id(ts: str,row: Mapping[str,Any],brain_digest: str="") -> str:
    safe=sanitize_pti_evidence(row)
    return "HIST8H-"+sha256_obj({"timestamp":ts,"evidence":safe,"brain_fingerprint":brain_digest})[:24]


def summarize_brain_passes(result: Mapping[str,Any]) -> Dict[str,Any]:
    p=result.get('passes') if isinstance(result.get('passes'),dict) else {}
    return {
        'has_specialists':bool(p.get('specialists')),
        'has_causal_graph':bool(p.get('causal_graph')),
        'has_market_twin':bool(p.get('market_twin')),
        'has_interventions':bool(p.get('interventions')),
        'has_hypotheses':bool(p.get('hypotheses')),
        'has_scenarios':bool(p.get('scenarios')),
        'has_judges':bool(p.get('judges')),
        'has_tribunal':bool(p.get('tribunal')),
        'runtime_retry_events':len(result.get('runtime_events') or []),
    }


def run_existing_master(backend: Path, python: Path, log_path: Path) -> Dict[str,Any]:
    script=backend/'run_clear_nasdaq_master_1y_backtest.py'
    if not script.exists():return {'status':'NOT_FOUND','path':str(script)}
    log_path.parent.mkdir(parents=True,exist_ok=True)
    with log_path.open('w',encoding='utf-8') as log:
        p=subprocess.run([str(python),str(script)],cwd=str(backend),stdout=log,stderr=subprocess.STDOUT)
    return {'status':'PASS' if p.returncode==0 else 'FAILED','returncode':p.returncode,'path':str(script),'log':str(log_path),'log_sha256':sha256_file(log_path)}


def load_phase36_importance(backend: Path) -> Dict[str,Any]:
    summary=backend/'fia_backtest_phase36/results/phase36_ablation_summary.json'
    diagnosis=backend/'fia_backtest_phase36/results/phase36_group_diagnosis.csv'
    out={'status':'NOT_AVAILABLE','claim_scope':'Historical deterministic Phase36 factor ablation only; it is not mislabeled as causal importance of GPT-OSS reasoning layers.'}
    diag_rows=[]
    if summary.exists():
        try:
            obj=json.loads(summary.read_text(encoding='utf-8'));out['summary']=obj;out['status']='AVAILABLE'
            raw=obj.get('diagnosis') if isinstance(obj,dict) else None
            if isinstance(raw,list): diag_rows=[x for x in raw if isinstance(x,dict)]
        except Exception as e:out['summary_error']=repr(e)
    if diagnosis.exists():
        try:
            csv_rows=load_csv(diagnosis);out['group_diagnosis']=csv_rows;out['status']='AVAILABLE'
            if not diag_rows: diag_rows=csv_rows
        except Exception as e:out['diagnosis_error']=repr(e)
    ranked=[]
    for row in diag_rows:
        group=str(row.get('group') or row.get('evidence_group') or '').strip()
        if not group: continue
        add=safe_float(row.get('mean_add_accuracy_pp'))
        remove=safe_float(row.get('mean_remove_accuracy_pp'))
        add_b=safe_float(row.get('mean_add_brier_delta'))
        remove_b=safe_float(row.get('mean_remove_brier_delta'))
        # This is an interpretable diagnostic ranking, not a causal claim. Positive accuracy
        # gains and Brier improvements (negative delta) increase the diagnostic score.
        score=(add or 0.0) - (remove or 0.0) - 100.0*(add_b or 0.0) + 100.0*(remove_b or 0.0)
        ranked.append({
            'group':group,
            'label':row.get('label'),
            'diagnostic_score':round(score,4),
            'mean_add_accuracy_pp':add,
            'mean_remove_accuracy_pp':remove,
            'mean_add_brier_delta':add_b,
            'mean_remove_brier_delta':remove_b,
            'claim_scope':'DEVELOPMENT_ONLY_ABLATION_DIAGNOSTIC_NOT_CAUSAL_PROOF',
        })
    ranked.sort(key=lambda x:(x['diagnostic_score'],x['group']),reverse=True)
    out['ranked_groups']=ranked
    out['ranking_note']='Ranking summarizes the existing Phase36 development-only ablation. It must not be interpreted as live causal importance or as a reason to hide losing factors.'
    return out


def _pick_forward_model(models: Mapping[str,Any]) -> Tuple[str,Optional[Mapping[str,Any]]]:
    for name in ("V6_6_BRAIN","GPT_OSS_20B","SHADOW_CANDIDATE","BASE_FIA"):
        x=models.get(name)
        if isinstance(x,Mapping): return name,x
    for name,x in models.items():
        if isinstance(x,Mapping): return str(name),x
    return "",None

def joined_forward_rows(backend: Path,hours:int=8) -> Tuple[List[Dict[str,Any]],Dict[str,Any]]:
    if str(backend) not in sys.path: sys.path.insert(0,str(backend))
    root=backend/"fia_forward_oos"
    try:
        from fia.forward_oos import records as forward_records, verify_ledger
        audit=verify_ledger(root)
        if not audit.get("ok"): return [],{"status":"LEDGER_INTEGRITY_FAILURE","audit":audit}
        joined=forward_records(root); rows=[]
        for r in joined:
            outcome=r.get(f"{hours}h")
            if not isinstance(outcome,Mapping): continue
            actual=normalize_direction(outcome.get("actual_direction"))
            if actual not in DIRECTIONAL: continue
            model_name,pred=_pick_forward_model(r.get("models") or {})
            if not pred: continue
            direction=normalize_direction(pred.get("direction")); hp=pred.get("horizon_probabilities") or {}
            hpred=hp.get(f"{hours}h") if isinstance(hp,Mapping) else None
            pb=safe_float((hpred or {}).get("bullish_probability")) if isinstance(hpred,Mapping) else None
            if pb is None: pb=safe_float(pred.get("bullish_probability"))
            if direction not in DIRECTIONAL: continue
            rows.append({"timestamp":r.get("locked_at_utc"),"brain_status":"OK","direction":direction,"outcome_direction":actual,"bullish_probability":pb,"forward_model":model_name,"forecast_id":r.get("forecast_id"),"resolution_event_hash":outcome.get("resolution_event_hash")})
        return rows,{"status":"AVAILABLE" if rows else "COLLECTING","audit":audit,"joined_records":len(joined),"model_semantics":"Uses only the model actually locked pre-move in each immutable FORECAST_LOCK; no retrospective candidate insertion."}
    except Exception as e:
        return [],{"status":"FORWARD_MODULE_UNAVAILABLE","error":type(e).__name__+": "+str(e)[:500]}

def rolling_forward_metrics(backend: Path) -> Dict[str,Any]:
    rows,meta=joined_forward_rows(backend,8); now=datetime.now(timezone.utc)
    def subset(start,end): return [r for r in rows if (lambda d: d is not None and start<=d<end)(parse_dt(r.get("timestamp")))]
    week_start=now-timedelta(days=now.weekday(),hours=now.hour,minutes=now.minute,seconds=now.second,microseconds=now.microsecond); prev_start=week_start-timedelta(days=7)
    windows={"last_7d":subset(now-timedelta(days=7),now+timedelta(seconds=1)),"last_30d":subset(now-timedelta(days=30),now+timedelta(seconds=1)),"current_week":subset(week_start,now+timedelta(seconds=1)),"previous_week":subset(prev_start,week_start),"all_resolved":rows}
    return {"status":meta.get("status"),"source":"fia.forward_oos.records() joined immutable FORECAST_LOCK + RESOLUTION_8H events","historical_backfill_mixed":False,"resolved_rows_detected":len(rows),"windows":{k:score_records(v) for k,v in windows.items()},"integrity":meta.get("audit"),"model_semantics":meta.get("model_semantics"),"diagnostic":meta.get("error"),"note":"Forward-OOS stays separate from retrospective 1Y replay. No live win rate is shown before genuine resolution events exist."}


def make_report(backend:Path,brain_root:Path,history_path:Path,records_path:Path,master_result:Dict[str,Any],state:str,total:int,completed:int,brain_fp:Optional[Dict[str,Any]]=None) -> Dict[str,Any]:
    rows=load_jsonl_safe(records_path)
    scores=score_records(rows)
    pass_counts=defaultdict(int)
    for r in rows:
        for k,v in (r.get('brain_passes') or {}).items():
            if isinstance(v,bool) and v:pass_counts[k]+=1
    master_ok=master_result.get('status') in {'PASS','SKIPPED_BY_FLAG'}
    complete=state=='COMPLETE' and completed==total and master_ok
    report_state='COMPLETE' if complete else ('COMPLETE_WITH_BASELINE_FAILURE' if state=='COMPLETE' and completed==total else state)
    report={
        'schema_version':SCHEMA_VERSION,
        'generated_at_utc':utc_now(),
        'state':report_state,
        'final':complete,
        'evaluation_class':'RETROSPECTIVE_TIME_TRAVEL_CURRENT_BUILD_NOT_FORWARD_OOS',
        'training_overlap_unknown_or_possible':True,
        'primary_horizon_hours':PRIMARY_HORIZON_HOURS,
        'progress':{'completed_cases':completed,'total_cases':total,'pct':round(100*completed/total,2) if total else 0.0},
        'historical_1y_whole_system':scores,
        'brain_layer_completion_counts':dict(pass_counts),
        'factor_importance':load_phase36_importance(backend),
        'live_forward_oos':rolling_forward_metrics(backend),
        'provenance':{
            'historical_rows_path':str(history_path),'historical_rows_sha256':sha256_file(history_path) if history_path.exists() else None,
            'brain_root':str(brain_root),'brain_config_sha256':sha256_file(brain_root/'config.json') if (brain_root/'config.json').exists() else None,'brain_fingerprint':brain_fp,
            'records_path':str(records_path),'records_sha256':sha256_file(records_path) if records_path.exists() else None,'records_chain':verify_record_chain(records_path),
            'existing_master_backtest':master_result,
        },
        'truth_policy':{
            'no_future_leakage_by_design':True,
            'outcome_fields_removed_before_v6_6':True,
            'missing_data_never_zero_or_neutral_imputed':True,
            'no_edge_counted_separately':True,
            'fail_closed_counted_separately':True,
            'unresolved_counted_separately':True,
            'historical_and_forward_oos_never_mixed':True,
            'partial_run_never_labeled_final':True,
            'checkpoint_hash_chain_required':True,
            'brain_fingerprint_bound_to_case_identity':True,
            'win_rate_formula':'wins/(wins+losses) for resolved directional V6.6 calls; coverage and abstentions shown beside it',
        },
        'known_historical_limitations':[
            'Historical inputs that do not have genuine point-in-time archives remain explicitly unavailable and are never synthesized.',
            'Phase36 factor importance is imported under its original deterministic ablation scope; GPT-OSS internal layer usage is reported separately, not falsely called causal importance.',
            'Retrospective current-build replay is not the same as genuinely unseen Forward-OOS evidence and does not guarantee future market performance.',
        ],
    }
    report['report_sha256']=sha256_obj({k:v for k,v in report.items() if k!='report_sha256'})
    return report


# FINAL_FUSION_DUAL_HORIZON_V2
EVALUATION_HORIZONS = (4, 8)

def score_dual_records(records: Sequence[Mapping[str,Any]], hours: int) -> Dict[str,Any]:
    """Score the SAME locked V6.6 whole-system forecast against a genuine market
    resolution at the requested horizon. This does not pretend there were two
    independent model calls. 4H and 8H outcomes remain distinct and visible.
    """
    projected=[]
    key=f"{int(hours)}h"
    for r in records:
        outcomes=r.get('outcomes') if isinstance(r.get('outcomes'),Mapping) else {}
        h=outcomes.get(key) if isinstance(outcomes,Mapping) else None
        h=h if isinstance(h,Mapping) else {}
        projected.append({
            'timestamp':r.get('timestamp'),
            'brain_status':r.get('brain_status'),
            'direction':r.get('direction'),
            'bullish_probability':r.get('bullish_probability'),
            'bearish_probability':r.get('bearish_probability'),
            'confidence':r.get('confidence'),
            'outcome_direction':h.get('direction'),
        })
    out=score_records(projected)
    out['horizon_hours']=int(hours)
    out['forecast_semantics']='SAME_LOCKED_V6_6_WHOLE_SYSTEM_FORECAST_DUAL_GENUINE_RESOLUTION'
    out['outcome_semantics']=f'GENUINE_{int(hours)}H_MARKET_RESOLUTION'
    return out


def rolling_forward_metrics_dual(backend: Path) -> Dict[str,Any]:
    return {
        'historical_backfill_mixed':False,
        '4h':rolling_forward_metrics_horizon(backend,4),
        '8h':rolling_forward_metrics_horizon(backend,8),
        'note':'4H and 8H live metrics are resolved independently from immutable pre-move forecast locks. Historical replay is never mixed into these windows.',
    }


def rolling_forward_metrics_horizon(backend: Path,hours:int) -> Dict[str,Any]:
    rows,meta=joined_forward_rows(backend,int(hours)); now=datetime.now(timezone.utc)
    def subset(start,end):
        out=[]
        for r in rows:
            d=parse_dt(r.get('timestamp'))
            if d is not None and start<=d<end: out.append(r)
        return out
    week_start=now-timedelta(days=now.weekday(),hours=now.hour,minutes=now.minute,seconds=now.second,microseconds=now.microsecond)
    prev_start=week_start-timedelta(days=7)
    windows={
        'last_7d':subset(now-timedelta(days=7),now+timedelta(seconds=1)),
        'last_30d':subset(now-timedelta(days=30),now+timedelta(seconds=1)),
        'current_week':subset(week_start,now+timedelta(seconds=1)),
        'previous_week':subset(prev_start,week_start),
        'all_resolved':rows,
    }
    return {
        'status':meta.get('status'),
        'horizon_hours':int(hours),
        'source':f'fia.forward_oos.records() joined immutable FORECAST_LOCK + RESOLUTION_{int(hours)}H events',
        'resolved_rows_detected':len(rows),
        'windows':{k:score_records(v) for k,v in windows.items()},
        'integrity':meta.get('audit'),
        'model_semantics':meta.get('model_semantics'),
        'diagnostic':meta.get('error'),
    }


def make_dual_report(backend:Path,brain_root:Path,history_path:Path,brain_records_path:Path,dual_records_path:Path,master_result:Dict[str,Any],state:str,total:int,completed:int,brain_fp:Optional[Dict[str,Any]]=None,reused_brain_records:int=0,new_brain_runs:int=0) -> Dict[str,Any]:
    rows=load_jsonl_safe(dual_records_path)
    h4=score_dual_records(rows,4)
    h8=score_dual_records(rows,8)
    pass_counts=defaultdict(int)
    for r in rows:
        for k,v in (r.get('brain_passes') or {}).items():
            if isinstance(v,bool) and v: pass_counts[k]+=1
    master_ok=master_result.get('status') in {'PASS','SKIPPED_BY_FLAG'}
    complete=state=='COMPLETE' and completed==total and master_ok
    report_state='COMPLETE' if complete else ('COMPLETE_WITH_BASELINE_FAILURE' if state=='COMPLETE' and completed==total else state)
    report={
        'schema_version':SCHEMA_VERSION,
        'generated_at_utc':utc_now(),
        'state':report_state,
        'final':complete,
        'evaluation_class':'RETROSPECTIVE_TIME_TRAVEL_CURRENT_BUILD_NOT_FORWARD_OOS',
        'training_overlap_unknown_or_possible':True,
        'primary_horizon_hours':8,
        'secondary_horizon_hours':4,
        'evaluation_mode':'ONE_LOCKED_V6_6_WHOLE_SYSTEM_FORECAST__TWO_GENUINE_MARKET_RESOLUTIONS_4H_8H',
        'progress':{
            'completed_cases':completed,'total_cases':total,
            'pct':round(100*completed/total,2) if total else 0.0,
            'reused_brain_records':int(reused_brain_records),
            'new_brain_runs':int(new_brain_runs),
        },
        'horizons':{'4h':h4,'8h':h8},
        # Backward-compatible 8H alias so older dashboard integrations never invent a new number.
        'historical_1y_whole_system':h8,
        'brain_layer_completion_counts':dict(pass_counts),
        'factor_importance':load_phase36_importance(backend),
        'live_forward_oos':rolling_forward_metrics_dual(backend),
        'provenance':{
            'historical_rows_path':str(history_path),
            'historical_rows_sha256':sha256_file(history_path) if history_path.exists() else None,
            'brain_root':str(brain_root),
            'brain_config_sha256':sha256_file(brain_root/'config.json') if (brain_root/'config.json').exists() else None,
            'brain_fingerprint':brain_fp,
            'brain_checkpoint_records_path':str(brain_records_path),
            'brain_checkpoint_records_sha256':sha256_file(brain_records_path) if brain_records_path.exists() else None,
            'brain_checkpoint_chain':verify_record_chain(brain_records_path),
            'dual_resolution_records_path':str(dual_records_path),
            'dual_resolution_records_sha256':sha256_file(dual_records_path) if dual_records_path.exists() else None,
            'dual_resolution_chain':verify_record_chain(dual_records_path),
            'existing_master_backtest':master_result,
        },
        'truth_policy':{
            'no_future_leakage_by_design':True,
            'outcome_fields_removed_before_v6_6':True,
            'missing_data_never_zero_or_neutral_imputed':True,
            'same_locked_prediction_scored_at_4h_and_8h':True,
            'separate_4h_model_call_claimed':False,
            '4h_outcome_is_genuine_market_resolution':True,
            '8h_outcome_is_genuine_market_resolution':True,
            'no_edge_counted_separately':True,
            'fail_closed_counted_separately':True,
            'unresolved_counted_separately':True,
            'historical_and_forward_oos_never_mixed':True,
            'partial_run_never_labeled_final':True,
            'checkpoint_hash_chain_required':True,
            'brain_fingerprint_bound_to_case_identity':True,
            'win_rate_formula':'wins/(wins+losses) for resolved directional calls; directional calls into genuine NEUTRAL outcomes count as losses; coverage and abstentions are always shown.',
            'binary_brier_neutral_policy':'NEUTRAL outcomes excluded from binary Brier/calibration; never coerced to bearish.',
            'financial_mdd_policy':'UNAVAILABLE until execution, stop and position-sizing policy is locked.',
        },
        'known_historical_limitations':[
            'Historical inputs without genuine point-in-time archives remain explicitly unavailable and are never synthesized.',
            'The 4H metric is an early genuine market resolution of the same locked V6.6 4–8H research forecast; it is not mislabeled as a second independent 4H Brain run.',
            'Phase36 factor importance remains a development-only ablation diagnostic, not live causal proof.',
            'Retrospective current-build replay is not the same as genuinely unseen Forward-OOS evidence and does not guarantee future market performance.',
        ],
    }
    report['report_sha256']=sha256_obj({k:v for k,v in report.items() if k!='report_sha256'})
    return report
