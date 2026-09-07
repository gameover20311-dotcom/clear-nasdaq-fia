from __future__ import annotations
import csv, json, math
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple

from .phase35_data_foundation import ROOT, _num
from .phase35_replay_engine import feature_votes, sig, fit_platt

ENR = ROOT / "fia_phase35" / "data" / "enriched_pti.jsonl"
OUT = ROOT / "fia_backtest_phase36" / "results"
POLICY = ROOT / "fia_phase36" / "PHASE36_POLICY.json"
DEV_FRACTION = 0.70

GROUPS: Dict[str, Set[str]] = {
    "CROSS_ASSET": {"CROSS_ASSET"},
    "LEADERSHIP_SEMIS": {"MEGA_CAP", "SEMIS"},
    "VOLATILITY": {"VIX", "VXN"},
    "RATES_REAL_YIELD": {"US2Y", "US10Y", "REAL_YIELD"},
    "NEWS_NOVELTY": {"NEWS", "NEWS_NOVELTY"},
    "EARNINGS": {"EARNINGS_SURPRISE"},
    "FUTURES_BASIS_PROXY": {"FUTURES_BASIS_PROXY"},
    "ORDERFLOW_LICENSED": {"L2_IMBALANCE", "VOLUME_DELTA"},
    "OPTIONS_LICENSED": {"DEALER_GAMMA", "OPTIONS_SKEW"},
    "ETF_FLOW_LICENSED": {"ETF_FLOW"},
}
ALL_FEATURES = {"BASE_FIA"} | set().union(*GROUPS.values())


def _actual(r: Dict[str, Any], h: str):
    a = str((r.get("base") or {}).get(f"actual_{h}") or "").upper()
    return 1 if a == "BULLISH" else 0 if a == "BEARISH" else None


def _resolved(r: Dict[str, Any], h: str) -> bool:
    v = str((r.get("base") or {}).get(f"correct_{h}") or "").lower()
    return v in {"true", "false", "1", "0", "yes", "no"}


def load_development(path: Path = ENR) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    if not path.exists():
        raise RuntimeError(f"Missing Phase35 enriched PTI dataset: {path}")
    rows = [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]
    cut = max(30, int(len(rows) * DEV_FRACTION))
    dev = rows[:cut]  # HARD RULE: Phase36 diagnosis uses development slice only for model selection.
    return dev, {"all_rows": len(rows), "development_rows": len(dev), "holdout_rows_not_loaded_for_diagnosis": len(rows)-len(dev)}


def _score(r: Dict[str, Any], allowed: Set[str]) -> Tuple[float, float, List[Tuple[str,float,float]]]:
    votes = [(n, float(x), float(w)) for n, x, w in feature_votes(r) if n in allowed]
    den = sum(w for _, _, w in votes)
    if den <= 0:
        return 0.0, 0.0, votes
    z = sum(x*w for _, x, w in votes) / den
    # Coverage is informational only. Removed groups do not get an artificial score-magnitude penalty.
    present = len({n for n,_,_ in votes})
    expected = max(1, len(allowed))
    return max(-1.0, min(1.0, z)), present/expected, votes


def _rolling_folds(n: int) -> List[Tuple[int,int,int]]:
    # Chronological expanding-window validation entirely inside development.
    if n < 60:
        a=max(20,n//2); b=max(a+10,min(n,a+20)); return [(0,a,b)] if b<=n else []
    test = max(15, n//8)
    first_train = max(45, n - test*4)
    folds=[]; train_end=first_train
    while train_end + test <= n:
        folds.append((0, train_end, train_end+test)); train_end += test
    return folds[-4:]


def _metrics(binary: List[Tuple[float,int]]) -> Dict[str, Any]:
    if not binary: return {"n":0}
    n=len(binary); correct=sum((p>=.5)==bool(y) for p,y in binary); acc=correct/n
    br=sum((p-y)**2 for p,y in binary)/n
    ll=-sum(y*math.log(max(.001,min(.999,p)))+(1-y)*math.log(max(.001,min(.999,1-p))) for p,y in binary)/n
    bins=defaultdict(list)
    for p,y in binary: bins[min(9,int(max(0,min(.999999,p))*10))].append((p,y))
    ece=sum(len(v)/n*abs(sum(p for p,y in v)/len(v)-sum(y for p,y in v)/len(v)) for v in bins.values())
    z=1.96; den=1+z*z/n; center=(acc+z*z/(2*n))/den; half=z*math.sqrt(acc*(1-acc)/n+z*z/(4*n*n))/den
    return {"n":n,"correct":correct,"incorrect":n-correct,"accuracy":round(100*acc,2),"brier":round(br,4),"log_loss":round(ll,4),"ece":round(ece,4),"wilson95":[round(100*(center-half),2),round(100*(center+half),2)]}


def evaluate_config(rows: List[Dict[str, Any]], allowed: Set[str], horizon: str) -> Dict[str, Any]:
    resolved=[r for r in rows if _resolved(r,horizon) and _actual(r,horizon) is not None]
    folds=_rolling_folds(len(resolved)); predictions=[]; fold_rows=[]
    for fi,(start,train_end,test_end) in enumerate(folds,1):
        tr=resolved[start:train_end]; te=resolved[train_end:test_end]
        xs=[]; ys=[]
        for r in tr:
            s,_,_=_score(r,allowed); xs.append(s*3.0); ys.append(_actual(r,horizon))
        if len(set(ys))<2: continue
        a,b=fit_platt(xs,ys)
        local=[]
        for r in te:
            s,_,_=_score(r,allowed); p=sig(a*s*3.0+b); y=_actual(r,horizon); predictions.append((p,y)); local.append((p,y))
        fm=_metrics(local); fm.update({"fold":fi,"train_n":len(tr),"test_n":len(te)})
        fold_rows.append(fm)
    out=_metrics(predictions); out["folds"]=len(fold_rows); out["fold_metrics"]=fold_rows
    return out


def _delta(a: Dict[str,Any], b: Dict[str,Any]) -> Dict[str,Any]:
    # a - b: positive accuracy is improvement; negative Brier is improvement.
    return {
        "accuracy_pp": round((a.get("accuracy") or 0)-(b.get("accuracy") or 0),2),
        "brier": round((a.get("brier") or 0)-(b.get("brier") or 0),4),
        "log_loss": round((a.get("log_loss") or 0)-(b.get("log_loss") or 0),4),
    }


def run_ablation() -> Dict[str,Any]:
    rows,meta=load_development(); configs: Dict[str,Set[str]]={"BASE_ONLY":{"BASE_FIA"},"FULL_AVAILABLE":set(ALL_FEATURES)}
    for g,names in GROUPS.items():
        configs[f"BASE_PLUS_{g}"]={"BASE_FIA"}|set(names)
        configs[f"FULL_MINUS_{g}"]=set(ALL_FEATURES)-set(names)
    results={}
    for name,allowed in configs.items():
        results[name]={h:evaluate_config(rows,allowed,h) for h in ("4h","8h")}
    base=results["BASE_ONLY"]; full=results["FULL_AVAILABLE"]
    diagnosis=[]
    for g in GROUPS:
        plus=results[f"BASE_PLUS_{g}"]; minus=results[f"FULL_MINUS_{g}"]
        by_h={}
        for h in ("4h","8h"):
            by_h[h]={"add_to_base":_delta(plus[h],base[h]),"remove_from_full":_delta(minus[h],full[h])}
        add_acc=sum(by_h[h]["add_to_base"]["accuracy_pp"] for h in ("4h","8h"))/2
        rem_acc=sum(by_h[h]["remove_from_full"]["accuracy_pp"] for h in ("4h","8h"))/2
        add_br=sum(by_h[h]["add_to_base"]["brier"] for h in ("4h","8h"))/2
        rem_br=sum(by_h[h]["remove_from_full"]["brier"] for h in ("4h","8h"))/2
        if rem_acc>=1.0 or rem_br<=-0.005 or add_acc<=-1.0 or add_br>=0.005:
            label="SUSPECT_HARMFUL_ON_DEVELOPMENT"
        elif add_acc>=1.0 or add_br<=-0.005 or rem_acc<=-1.0 or rem_br>=0.005:
            label="HELPFUL_ON_DEVELOPMENT"
        else:
            label="MIXED_OR_SMALL_EFFECT"
        diagnosis.append({"group":g,"label":label,"mean_add_accuracy_pp":round(add_acc,2),"mean_remove_accuracy_pp":round(rem_acc,2),"mean_add_brier_delta":round(add_br,4),"mean_remove_brier_delta":round(rem_br,4),"by_horizon":by_h})
    diagnosis.sort(key=lambda x:(x["label"]!="SUSPECT_HARMFUL_ON_DEVELOPMENT",-x["mean_remove_accuracy_pp"]))
    helpful=[x["group"] for x in diagnosis if x["label"]=="HELPFUL_ON_DEVELOPMENT"]
    suspect=[x["group"] for x in diagnosis if x["label"]=="SUSPECT_HARMFUL_ON_DEVELOPMENT"]
    candidate={"status":"DEV_ONLY_RESEARCH_CANDIDATE_NOT_LIVE","always_include":["BASE_FIA"],"candidate_include_groups":helpful,"candidate_exclude_groups":suspect,"rule":"Never deploy from Phase36 alone. Candidate must be frozen and tested on genuinely new unseen data."}
    result={"ok":True,"phase":"PHASE 36 ROOT-CAUSE + ABLATION LAB","policy":"DEVELOPMENT_ONLY_WALK_FORWARD","meta":meta,"base_only":base,"full_available":full,"diagnosis":diagnosis,"candidate_policy":candidate,"phase35_holdout_used_for_selection":False,"production_weights_changed":False,"rl_live_weight":0.0,"broker_execution":False,"note":"This lab diagnoses marginal evidence value without reading the Phase35 holdout for selection. It does not claim a new production edge."}
    OUT.mkdir(parents=True,exist_ok=True)
    (OUT/"phase36_ablation_summary.json").write_text(json.dumps(result,indent=2),encoding="utf-8")
    (OUT/"phase36_candidate_policy.json").write_text(json.dumps(candidate,indent=2),encoding="utf-8")
    with (OUT/"phase36_group_diagnosis.csv").open("w",newline="",encoding="utf-8") as f:
        w=csv.writer(f); w.writerow(["group","label","mean_add_accuracy_pp","mean_remove_accuracy_pp","mean_add_brier_delta","mean_remove_brier_delta"])
        for x in diagnosis:w.writerow([x[k] for k in ["group","label","mean_add_accuracy_pp","mean_remove_accuracy_pp","mean_add_brier_delta","mean_remove_brier_delta"]])
    return result
