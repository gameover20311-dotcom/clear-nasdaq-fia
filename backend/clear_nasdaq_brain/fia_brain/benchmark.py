from __future__ import annotations
import json, math, re
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
from .util import sha256_obj
from .cases import valid_output_hash
from .evidence import validate_ledger_integrity
from .parity_v6 import score as score_reasoning

REQ=("direction","bullish_probability","bearish_probability","confidence","thesis","evidence_ids","counter_evidence_ids","unknowns","failure_conditions")

def _read_jsonl(path: Union[str,Path]) -> List[Dict[str,Any]]:
    p=Path(path)
    if not p.exists(): return []
    rows=[]
    for n,line in enumerate(p.read_text(encoding="utf-8").splitlines(),1):
        if not line.strip(): continue
        def bad(x): raise ValueError("non-finite JSON")
        x=json.loads(line,parse_constant=bad)
        if not isinstance(x,dict): raise ValueError("row %d not object"%n)
        rows.append(x)
    return rows

def _index(rows: List[Dict[str,Any]], label: str) -> Dict[str,Dict[str,Any]]:
    out={}
    for x in rows:
        cid=str(x.get("case_id") or "")
        if not cid: raise ValueError(label+" row missing case_id")
        if cid in out: raise ValueError("duplicate case_id in %s: %s"%(label,cid))
        out[cid]=x
    return out

def case_hash(case: Dict[str,Any]) -> str:
    body={k:v for k,v in case.items() if k not in {"case_sha256","outcome_direction"}}
    return sha256_obj(body)

def _valid_binding(row: Dict[str,Any], case: Dict[str,Any]) -> bool:
    return (str(row.get("case_sha256"))==str(case.get("case_sha256")) and
            str(row.get("ledger_sha256"))==str((case.get("ledger") or {}).get("ledger_sha256")))

def _tokens(s: str): return set(re.findall(r"[a-z0-9_]+",str(s).lower()))
def _j(a,b):
    a,b=set(a),set(b)
    if not a and not b:return 1.0
    if not a or not b:return 0.0
    return len(a&b)/len(a|b)
def _finite(x):
    v=float(x)
    if not math.isfinite(v): raise ValueError("non-finite")
    return v

def score_pair(local: Dict[str,Any], teacher: Dict[str,Any]) -> Dict[str,Any]:
    lf=local.get("final",local); tf=teacher.get("final",teacher)
    if not all(k in lf for k in REQ) or not all(k in tf for k in REQ):
        raise ValueError("analysis contract incomplete")
    lp=_finite(lf["bullish_probability"]); tp=_finite(tf["bullish_probability"])
    lc=_finite(lf["confidence"]); tc=_finite(tf["confidence"])
    prob_gap=abs(lp-tp); conf_gap=abs(lc-tc)
    parts={
      "direction":20.0 if lf.get("direction")==tf.get("direction") else 0.0,
      "probability":max(0.0,20.0*(1-prob_gap/50.0)),
      "confidence":max(0.0,10.0*(1-conf_gap/100.0)),
      "evidence":15.0*_j(map(str,lf.get("evidence_ids",[])),map(str,tf.get("evidence_ids",[]))),
      "counter_evidence":10.0*_j(map(str,lf.get("counter_evidence_ids",[])),map(str,tf.get("counter_evidence_ids",[]))),
      "thesis_token_overlap":10.0*_j(_tokens(lf.get("thesis","")),_tokens(tf.get("thesis",""))),
      "contract":15.0,
    }
    return {"score":round(sum(parts.values()),2),"direction_match":lf.get("direction")==tf.get("direction"),
            "bullish_probability_gap":round(prob_gap,4),"confidence_gap":round(conf_gap,4),
            "components":{k:round(v,2) for k,v in parts.items()}}

def _outcomes(path: Optional[Union[str,Path]]) -> Dict[str,Dict[str,Any]]:
    if not path:return {}
    return _index(_read_jsonl(path),"outcomes")

def evaluate(local_path: Union[str,Path],teacher_path: Union[str,Path],cases_path: Union[str,Path],
             outcomes_path: Optional[Union[str,Path]]=None,split: str="HOLDOUT") -> Dict[str,Any]:
    cases_all=_index(_read_jsonl(cases_path),"cases")
    cases={cid:c for cid,c in cases_all.items() if str(c.get("split","DEV")).upper()==split.upper()}
    local=_index(_read_jsonl(local_path),"local")
    teacher=_index(_read_jsonl(teacher_path),"teacher")
    outcomes=_outcomes(outcomes_path)
    expected=set(cases); missing_local=sorted(expected-set(local)); missing_teacher=sorted(expected-set(teacher))
    extra_local=sorted(set(local)-set(cases_all)); extra_teacher=sorted(set(teacher)-set(cases_all))
    rows=[]; excluded=[]
    for cid in sorted(expected & set(local) & set(teacher)):
        case=cases[cid]
        if str(case.get("case_sha256")) != case_hash(case):
            excluded.append({"case_id":cid,"reason":"case_hash_mismatch"}); continue
        ledger_ok,ledger_errors=validate_ledger_integrity(case.get("ledger") or {})
        if not ledger_ok:
            excluded.append({"case_id":cid,"reason":"ledger_integrity_failure:"+",".join(ledger_errors[:4])}); continue
        if str(case.get("ledger_sha256"))!=str((case.get("ledger") or {}).get("ledger_sha256")):
            excluded.append({"case_id":cid,"reason":"case_ledger_sha_mismatch"}); continue
        if not valid_output_hash(local[cid]):
            excluded.append({"case_id":cid,"reason":"local_output_hash_mismatch"}); continue
        if not valid_output_hash(teacher[cid]):
            excluded.append({"case_id":cid,"reason":"teacher_output_hash_mismatch"}); continue
        if not _valid_binding(local[cid],case):
            excluded.append({"case_id":cid,"reason":"local_binding_mismatch"}); continue
        if not _valid_binding(teacher[cid],case):
            excluded.append({"case_id":cid,"reason":"teacher_binding_mismatch"}); continue
        ids={str(r.get("evidence_id")) for r in ((case.get("ledger") or {}).get("records") or [])}
        bad=False
        for label,row in (("local",local[cid]),("teacher",teacher[cid])):
            f=row.get("final",row)
            refs=set(map(str,f.get("evidence_ids",[])))|set(map(str,f.get("counter_evidence_ids",[])))
            if not refs.issubset(ids): excluded.append({"case_id":cid,"reason":label+"_invalid_evidence_reference"}); bad=True; break
        if bad: continue
        s=score_pair(local[cid],teacher[cid])
        lrs=local[cid].get("reasoning_signature"); trs=teacher[cid].get("reasoning_signature")
        if split.upper()=="HOLDOUT" and (not isinstance(lrs,dict) or not isinstance(trs,dict)):
            excluded.append({"case_id":cid,"reason":"v6_reasoning_signature_missing"}); continue
        if isinstance(lrs,dict) and isinstance(trs,dict):
            rs=score_reasoning(lrs,trs); s["structured_reasoning"]=rs
            s["score"]=round(0.60*s["score"]+0.40*rs["reasoning_score"],2)
        s["case_id"]=cid; rows.append(s)
    n=len(rows); complete=(not missing_local and not missing_teacher and not excluded)
    mean=sum(r["score"] for r in rows)/n if n else None
    da=sum(1 for r in rows if r["direction_match"])/n*100 if n else None
    mpg=sum(r["bullish_probability_gap"] for r in rows)/n if n else None
    mcg=sum(r["confidence_gap"] for r in rows)/n if n else None
    market=[]
    for r in rows:
        cid=r["case_id"]; o=outcomes.get(cid)
        if not o: continue
        if str(o.get("case_sha256"))!=str(cases[cid].get("case_sha256")): continue
        direction=str(o.get("outcome_direction","")).upper()
        if direction not in {"BULLISH","BEARISH"}: continue
        y=1.0 if direction=="BULLISH" else 0.0
        lf=local[cid].get("final",local[cid]); tf=teacher[cid].get("final",teacher[cid])
        market.append(((_finite(lf["bullish_probability"])/100-y)**2,(_finite(tf["bullish_probability"])/100-y)**2))
    market_score=None
    if market:
        market_score={"resolved_n":len(market),"local_brier":round(sum(x for x,_ in market)/len(market),6),
                      "teacher_brier":round(sum(y for _,y in market)/len(market),6),"lower_is_better":True}
    label="INSUFFICIENT_SAMPLE" if n<30 else ("PRELIMINARY_EVALUATION" if n<100 else "SERIOUS_EVALUATION")
    mean_rs=(sum(r.get("structured_reasoning",{}).get("reasoning_score",0) for r in rows)/n) if n else None
    parity=bool(complete and n>=100 and mean is not None and mean>=90 and da is not None and da>=85 and mpg is not None and mpg<=7 and mean_rs is not None and mean_rs>=85)
    reason_scores=[r.get("structured_reasoning",{}).get("reasoning_score") for r in rows if r.get("structured_reasoning")]
    return {"benchmark":"FIA_DOMAIN_BEHAVIORAL_REFERENCE_V6","split":split.upper(),"expected_cases":len(expected),
            "paired_cases_valid":n,"complete_cohort":complete,"missing_local":missing_local,"missing_teacher":missing_teacher,
            "extra_local_unknown_cases":extra_local,"extra_teacher_unknown_cases":extra_teacher,"excluded":excluded,
            "sample_label":label,"mean_teacher_similarity_score":round(mean,2) if mean is not None else None,
            "direction_agreement_pct":round(da,2) if da is not None else None,
            "mean_bullish_probability_gap":round(mpg,2) if mpg is not None else None,
            "mean_confidence_gap":round(mcg,2) if mcg is not None else None,"mean_structured_reasoning_score":round(sum(reason_scores)/len(reason_scores),2) if reason_scores else None,"behavioral_parity_gate_pass":parity,
            "market_outcome_score":market_score,
            "truth_note":"Behavioral parity is domain-specific and is not global model equivalence; market edge requires separate future-resolved outcomes.",
            "rows":rows}
