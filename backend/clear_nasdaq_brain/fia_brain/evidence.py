from __future__ import annotations
import json, time, urllib.request, re
from typing import Any, Dict, Iterable, List, Tuple
from .util import sha256_obj, utc_now
from .network import assert_loopback_url, no_proxy_opener

PRIORITY_TOKENS=(
 "direction","probability","confidence","regime","score","coverage","nq","qqq","spy","spx","es","dxy",
 "us10y","yield","vix","nvda","msft","aapl","amzn","meta","avgo","goog","tsla","amd","mu","semi",
 "breadth","macro","fed","cpi","pce","nfp","news","earnings","liquidity","session","fresh","provider","status",
)

def _loads_strict(raw: bytes) -> Any:
    def bad(x): raise ValueError("non-finite JSON constant forbidden: "+x)
    return json.loads(raw.decode("utf-8"),parse_constant=bad)

def http_json(url: str,timeout: int=8,max_bytes: int=4_000_000) -> Tuple[int,Any]:
    assert_loopback_url(url)
    req=urllib.request.Request(url,headers={"Accept":"application/json","User-Agent":"FIA-Brain-V5/5.0"})
    with no_proxy_opener().open(req,timeout=timeout) as r:
        raw=r.read(max_bytes+1)
        if len(raw)>max_bytes: raise ValueError("response exceeds max_bytes")
        ctype=(r.headers.get("Content-Type") or "").lower()
        if "json" not in ctype and not raw.lstrip().startswith((b"{",b"[")):
            raise ValueError("response is not JSON")
        return int(r.status),_loads_strict(raw)

def _fetch(base: str,path: str,timeout: int) -> Tuple[Dict[str,Any],Any]:
    started=time.monotonic()
    try:
        status,body=http_json(base+path,timeout=timeout)
        return {
            "ok":200<=status<300,"status":status,"error":None,
            "elapsed_ms":round((time.monotonic()-started)*1000,2),
        },body
    except Exception as e:
        status=getattr(e,"code",0) or 0
        return {
            "ok":False,"status":int(status),
            "error":type(e).__name__+": "+str(e)[:240],
            "elapsed_ms":round((time.monotonic()-started)*1000,2),
        },None

PREDICTION_DASHBOARD_TOP_LEVEL=("ok","generated_at","live")

def project_prediction_time_payload(endpoint: str,body: Any) -> Tuple[Any,Dict[str,Any]]:
    """Build the model-facing prediction-time view of an atomic backend payload.

    `/api/dashboard` intentionally contains both live evidence and retrospective
    validation/backtest analytics for humans.  Those outcome-time branches must
    never enter the model ledger.  We therefore keep the backend route truth but
    project only the dashboard's live branch before ledger construction.

    This is not a leakage bypass: semantic future-field checks still run on the
    projected ledger.  If a forbidden field appears inside `live`, the Brain
    still fail-closes before any model call.
    """
    endpoint=str(endpoint or "")
    # V6.6.2: this was exact string equality against "/api/dashboard". One character of
    # config drift (a trailing slash, a query string, a renamed route) silently reverted
    # the whole prediction-time boundary to identity, admitting the retrospective
    # "backtest" branch into the model ledger. The projection is now decided by the
    # PAYLOAD SHAPE: any dashboard-shaped body (one carrying a "live" branch) is
    # projected, whatever the route is called.
    normalized=endpoint.split("?",1)[0].split("#",1)[0].rstrip("/") or endpoint
    dashboard_shaped=isinstance(body,dict) and ("live" in body or "backtest" in body)
    if normalized!="/api/dashboard" and not dashboard_shaped:
        return body,{"policy":"identity","endpoint":endpoint,
                     "raw_payload_sha256":sha256_obj(body) if body is not None else None}
    if not isinstance(body,dict):
        return None,{"policy":"dashboard_live_only_v1","error":"dashboard_payload_not_object","raw_payload_sha256":sha256_obj(body) if body is not None else None}
    projected=_prediction_projection(endpoint,body)
    # Missing live data is represented as unavailable, never replaced with
    # retrospective sections.  The downstream empty/coverage guards then fail closed.
    if "live" not in projected:
        projected["live"]=None
    excluded=sorted(str(k) for k in body.keys() if k not in PREDICTION_DASHBOARD_TOP_LEVEL)
    return projected,{
        "policy":"dashboard_live_only_v1",
        "endpoint":endpoint,
        "selected_by":("endpoint_match" if normalized=="/api/dashboard" else "payload_shape"),
        "raw_payload_sha256":sha256_obj(body),
        "projected_payload_sha256":sha256_obj(projected),
        "excluded_top_level_keys":excluded,
    }

def collect_atomic(base_url: str,atomic_endpoint: str,health_endpoints: List[str],timeout: int=8) -> Dict[str,Any]:
    """
    Evidence comes from ONE canonical dashboard request only.
    For `/api/dashboard`, the model-facing payload is a deterministic live-only
    projection; retrospective `backtest`/validation branches remain available
    to the dashboard but never enter the prediction ledger.
    Supplementary health endpoints are gates/metadata and are NEVER merged into
    the evidence ledger.
    """
    base=base_url.rstrip("/")
    started_utc=utc_now(); t0=time.monotonic()
    endpoint_health: Dict[str,Any]={}
    atomic_health,atomic_body=_fetch(base,atomic_endpoint,timeout)
    atomic_attempts=1
    if not atomic_health.get("ok"):
        # A busy local backend can transiently miss one request. Retry the ENTIRE
        # canonical atomic payload once; never combine fields across attempts.
        time.sleep(0.75)
        atomic_health,atomic_body=_fetch(base,atomic_endpoint,timeout)
        atomic_attempts=2
    atomic_health=dict(atomic_health)
    atomic_health["attempts"]=atomic_attempts
    endpoint_health[atomic_endpoint]=atomic_health
    projected_body,projection_meta=project_prediction_time_payload(atomic_endpoint,atomic_body)
    health_payloads={}
    for path in health_endpoints:
        h,b=_fetch(base,path,timeout)
        endpoint_health[path]=h
        health_payloads[path]=b
    snap={
        "captured_at_utc":utc_now(),
        "capture_started_at_utc":started_utc,
        "capture_elapsed_ms":round((time.monotonic()-t0)*1000,2),
        "base_url":base,
        "atomic_evidence_endpoint":atomic_endpoint,
        "endpoint_health":endpoint_health,
        "prediction_projection":projection_meta,
        "payloads":{atomic_endpoint:projected_body},
        "health_payloads":health_payloads,
    }
    snap["snapshot_sha256"]=sha256_obj(snap)
    return snap

# Legacy name intentionally maps to atomic behavior only when caller supplies one endpoint.
def collect(base_url: str,endpoints: List[str],timeout: int=8) -> Dict[str,Any]:
    if not endpoints: raise ValueError("at least one endpoint required")
    return collect_atomic(base_url,endpoints[0],endpoints[1:],timeout)

def _walk(x: Any,prefix: str="") -> Iterable[Tuple[str,Any]]:
    if isinstance(x,dict):
        for k in sorted(x):
            p=f"{prefix}.{k}" if prefix else str(k)
            yield from _walk(x[k],p)
    elif isinstance(x,list):
        for i,v in enumerate(x[:40]):
            p=f"{prefix}[{i}]"; yield from _walk(v,p)
    elif x is None or isinstance(x,(str,int,float,bool)):
        yield prefix,x

def _priority(path: str) -> int:
    p=path.lower()
    # V7.4: match priority concepts as lexical TOKENS, not arbitrary substrings.
    # Substring matching gave metadata->"meta", cumulative->"mu" and
    # transmission->"ism" spurious priority, biasing which evidence survives the
    # max_records/max_chars cutoff. Same defect class as the V6.6.2 status-matching fix.
    def hit(tok: str) -> bool:
        return re.search(r"(?<![a-z0-9])"+re.escape(tok.lower())+r"(?![a-z0-9])",p) is not None
    return sum(5 for t in PRIORITY_TOKENS if hit(t))-min(len(p)//100,3)

# ---------------------------------------------------------------------------
# V7.4 + V6.6.2 MERGED PREDICTION-TIME PROJECTION
# ---------------------------------------------------------------------------
# V7.4 contribution: a strict WHITELIST of live evidence branches, and exclusion of
#   live.forecast / live.cognitive so the Brain cannot anchor on another model's
#   conclusion and then cite it back as a fact. Unexpected schema fails closed
#   instead of falling back to the unprojected payload.
# V6.6.2 contribution: selection by PAYLOAD SHAPE as well as route, so one character
#   of config drift (trailing slash, query string, renamed route) cannot silently
#   revert the boundary to identity.
# Applied inside build_ledger as defence in depth: the boundary holds even if a
# caller forgets to project at capture time. Projection is idempotent.
PREDICTION_ALLOWED_LIVE_BRANCHES=("snapshot","liquidity","liquidity_groups","upcoming_earnings")
PREDICTION_EXCLUDED_LIVE_BRANCHES=("forecast","cognitive","premove_watch")

def _is_dashboard_payload(endpoint: str, body: Any) -> bool:
    normalized=str(endpoint or "").split("?",1)[0].split("#",1)[0].rstrip("/")
    if normalized=="/api/dashboard": return True
    return isinstance(body,dict) and ("live" in body or "backtest" in body)

def _prediction_projection(endpoint: str, body: Any) -> Any:
    if not _is_dashboard_payload(endpoint,body) or not isinstance(body,dict):
        return body
    live=body.get("live")
    if not isinstance(live,dict):
        return {"ok":body.get("ok"),"generated_at":body.get("generated_at"),"live_schema_missing":True}
    allowed={k:live[k] for k in PREDICTION_ALLOWED_LIVE_BRANCHES if k in live}
    out={"ok":body.get("ok"),"generated_at":body.get("generated_at"),"live":allowed}
    if "data_as_of" in body: out["data_as_of"]=body["data_as_of"]
    elif isinstance(live.get("data_as_of"),str): out["data_as_of"]=live["data_as_of"]
    return out

def build_ledger(snapshot: Dict[str,Any],max_records: int=360,max_chars: int=64000) -> Dict[str,Any]:
    rows=[]
    # STRICT: only snapshot["payloads"] enters evidence. health_payloads never enters.
    for endpoint,body in (snapshot.get("payloads") or {}).items():
        if body is None: continue
        projected=_prediction_projection(endpoint,body)
        for path,value in _walk(projected):
            record={"source":endpoint,"path":path,"value":value}
            record["record_hash"]=sha256_obj(record)
            rows.append((_priority(path),record))
    rows.sort(key=lambda x:(-x[0],x[1]["source"],x[1]["path"]))
    selected=[]; used=0
    for _,record0 in rows:
        record=dict(record0); record["evidence_id"]=f"E{len(selected)+1:04d}"
        size=len(json.dumps(record,ensure_ascii=False,allow_nan=False))
        if selected and used+size>max_chars: break
        selected.append(record); used+=size
        if len(selected)>=max_records: break
    ledger={"snapshot_sha256":snapshot.get("snapshot_sha256"),"record_count":len(selected),"records":selected}
    ledger["ledger_sha256"]=sha256_obj(ledger)
    return ledger

def evidence_text(ledger: Dict[str,Any]) -> str:
    lines=[]
    for r in ledger.get("records",[]):
        v=r.get("value")
        if isinstance(v,str): v=" ".join(v.replace("\x00"," ").split())[:800]
        lines.append(f'{r["evidence_id"]} | {r["source"]} | {r["path"]} = {json.dumps(v,ensure_ascii=False,allow_nan=False)}')
    return "\n".join(lines)


def validate_ledger_integrity(ledger: Dict[str,Any]) -> Tuple[bool,List[str]]:
    errors=[]
    if not isinstance(ledger,dict): return False,["ledger_not_object"]
    records=ledger.get("records")
    if not isinstance(records,list): return False,["records_not_list"]
    if int(ledger.get("record_count",-1))!=len(records): errors.append("record_count_mismatch")
    seen=set()
    for i,r in enumerate(records,1):
        if not isinstance(r,dict): errors.append("record_not_object:%d"%i); continue
        eid=str(r.get("evidence_id") or "")
        if eid in seen or eid!="E%04d"%i: errors.append("evidence_id_invalid:%d"%i)
        seen.add(eid)
        body={"source":r.get("source"),"path":r.get("path"),"value":r.get("value")}
        try:
            expected=sha256_obj(body)
        except Exception:
            errors.append("record_noncanonical:%d"%i); continue
        if str(r.get("record_hash"))!=expected: errors.append("record_hash_mismatch:%s"%eid)
    body={k:v for k,v in ledger.items() if k!="ledger_sha256"}
    try:
        expected_ledger=sha256_obj(body)
        if str(ledger.get("ledger_sha256"))!=expected_ledger: errors.append("ledger_sha256_mismatch")
    except Exception:
        errors.append("ledger_noncanonical")
    return not errors,errors

# Fields that are only knowable after a forecast timestamp and therefore forbidden
# at the Brain prediction boundary, even if an upstream caller accidentally supplies them.
# The exact-name set catches known legacy fields; the semantic detector below blocks
# equivalent future labels under unseen names such as target_close_8h or
# realized_return_4h without suppressing legitimate contemporaneous facts such as
# macro.cpi.actual, fed.target_rate, or realized_volatility.
FUTURE_OUTCOME_FIELDS={
    "nq_4h","nq_8h","move_4h_pct","move_8h_pct","actual_4h","actual_8h",
    "correct_4h","correct_8h","future_price","future_price_4h","future_price_8h",
    "outcome_direction","outcome_4h","outcome_8h","mfe_pct","mae_pct",
    "maximum_favorable_excursion","maximum_adverse_excursion"
}
_FIELD_RE=re.compile(r"[a-z0-9_]+",re.I)
_SEMANTIC_TOKEN_RE=re.compile(r"[a-z0-9]+",re.I)

# V6.6.2: concept-level outcome vocabulary. The V6.6.1 detector matched a narrow
# token list and let ~18 of 21 tested aliases through (settled_direction,
# verified_move, post_move_pct, eod_close, close_after_8h, px_t_plus_4h, y_true,
# hit_target, excursion, drawdown_after, subsequent_return, ex_post_return,
# forward_4h, fwd_ret, t_plus_8, settlement_price, final_move, move_realized...).
# Two deliberate REMOVALS from the marker set: bare "resolution" and bare "label".
# "resolution" is a legitimate candle-interval field name and "label" a legitimate
# display field; blocking them destroyed real present-tense evidence. Both are still
# caught when combined with a directional/outcome word below.
_FUTURE_SUBSTRINGS=(
    "forward_return","future_price","ground_truth","truth_direction",
    "next_price","next_close","next_return","maximum_favorable_excursion",
    "maximum_adverse_excursion","post_move","postmove","after_move","move_after",
    "subsequent_return","subsequent_move","ex_post","expost","settlement_price",
    "settled_price","eod_close","close_after","price_after","return_after",
    "drawdown_after","runup_after","hit_target","target_hit","was_correct",
    "y_true","ytrue","y_label","final_move","move_realized","realized_move",
    "verified_move","settled_direction","final_direction","final_outcome",
    "t_plus","tplus","px_t_","fwd_ret","fwd_return","forward_move",
    "hindsight","lookahead","look_ahead","peek_ahead",
)
_OUTCOME_CONTEXT={"direction","price","close","return","outcome","label","pnl",
                  "move","pct","percent","value","result","excursion","drawdown"}

def _future_semantic_path(path: str) -> bool:
    p=str(path or "").lower()
    leaf=re.split(r"[.\[\]/:]",p)[-1]
    if leaf in FUTURE_OUTCOME_FIELDS:
        return True
    toks=set(_SEMANTIC_TOKEN_RE.findall(p))
    compact=p.replace("-","_")
    if any(x in compact for x in _FUTURE_SUBSTRINGS):
        return True
    horizon=bool({"4h","8h","h4","h8"} & toks) or bool(re.search(r"(?:^|[^0-9])(4|8)h(?:[^a-z0-9]|$)",p))
    # t+N / t_plus_N style horizon offsets
    if re.search(r"(?:^|_)t[_+]?plus[_]?\d+",compact) or re.search(r"(?:^|_)t\+\d+",compact):
        return True
    future_markers={"future","outcome","correct","resolved","mfe","mae","pnl",
                    "settled","hindsight","lookahead","realised"}
    if toks & future_markers:
        return True
    # An analyst/consensus price target is a PUBLISHED PRESENT-TENSE estimate, not a
    # realized outcome. Allow it explicitly so the boundary does not delete real evidence.
    analyst_context=bool({"analyst","analysts","consensus","estimate","estimates",
                          "sellside","street"} & toks)
    for stem in ("actual","target","realized","next","result","final","verified",
                 "settled","subsequent","posterior","label","resolution","forward"):
        if stem=="target" and analyst_context and not horizon:
            continue
        if stem in toks and (horizon or bool(_OUTCOME_CONTEXT & (toks-{stem}))):
            return True
    if "excursion" in toks or "drawdown" in toks:
        return True
    return False

def prediction_time_violations(ledger: Dict[str,Any]) -> List[str]:
    bad=[]
    for r in ledger.get("records",[]):
        path=str(r.get("path","")).lower()
        toks=set(_FIELD_RE.findall(path))
        hit=sorted(FUTURE_OUTCOME_FIELDS & toks)
        if hit or _future_semantic_path(path):
            bad.append(str(r.get("path","")))
    return sorted(set(bad))
