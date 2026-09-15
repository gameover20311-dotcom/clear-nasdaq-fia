from __future__ import annotations
import json, math, random, re
from collections import Counter

def parse(text):
    raw=text.strip(); choice=None; confidence=50
    m=re.search(r'["\']?choice["\']?\s*[:=]\s*["\']?([ABCD])\b',raw,flags=re.I)
    if m: choice=m.group(1).upper()
    if choice is None:
        m=re.match(r'^\s*(?:answer\s*[:=]?\s*)?([ABCD])(?=\s|[\.\)\]:,;\-]|$)',raw,flags=re.I)
        if m: choice=m.group(1).upper()
    cm=re.search(r'["\']?confidence["\']?\s*[:=]\s*([0-9]{1,3})',raw,flags=re.I)
    if cm: confidence=max(0,min(100,int(cm.group(1))))
    if choice not in set("ABCD"): raise RuntimeError("UNPARSEABLE")
    return {"choice":choice,"confidence":confidence,"raw":raw}

def stage_prompt(task,seed):
    rng=random.Random(seed); pairs=list(task["options"].items()); rng.shuffle(pairs); local={}; mapping={}
    for lbl,(canon,text) in zip("ABCD",pairs): local[lbl]=text; mapping[lbl]=canon
    opts="\n".join(f"{k}. {v}" for k,v in local.items())
    p=(f"TASK {task['id']}\nCATEGORY: {task['category']}\nQUESTION:\n{task['question']}\n\nEVIDENCE:\n{task['context']}\n\nOPTIONS:\n{opts}\n\n" 'Return JSON only: {"choice":"A|B|C|D","confidence":0-100}.')
    return p,mapping

def canonical(parsed,mapping):
    out=dict(parsed); out["choice"]=mapping.get(parsed.get("choice")); return out

def guide(category,role):
    common={"arithmetic":"Recompute exact arithmetic in precedence order.","implication":"Apply the material implication truth rule exactly.","boolean_logic":"Evaluate the Boolean expression exactly.","quantifiers":"Check the complete finite domain.","set_relation":"Compare set membership exactly.","ordering":"Use transitivity and only stated ordering facts.","probability_basic":"Use the correct sample-space denominator and reduce the fraction.","contradiction":"Check same proposition, time, and scope.","datetime_order":"Compare timestamps directly.","future_leakage":"Compare decision time with first information availability.","evidence_independence":"Separate repeated agreement from independent evidence.","provenance":"Reconcile conflicting identity records before trusting identity.","temporal_lock":"Preserve pre-outcome commitments after outcome information exists.","promotion_gate":"A mandatory evidence threshold must actually be met.","causal_confounding":"Unresolved confounding blocks a causal claim.","missing_information":"Do not invent missing facts; choose the cannot-determine option when required."}
    base=common.get(category,"Use only supplied evidence and check every option.")
    if role=="a": return base+" Recompute and look for a boundary or logic failure."
    if role=="b": return base+" Solve independently by a different route; do not rely on another stage."
    if role=="judge": return base+" Solve independently, then compare the locked candidates; all candidates may be wrong."
    return base+" Solve directly from the supplied evidence."

def candidate_text(task,result):
    ch=result.get("choice"); return json.dumps({"answer_text":task["options"].get(ch,"UNPARSEABLE"),"reported_confidence":result.get("confidence",0)},sort_keys=True)

def confidence(choices,judge):
    final=judge.get("choice")
    if not final:return 0
    n=sum(x==final for x in choices); evidence={4:78,3:68,2:55,1:38,0:25}.get(n,25); raw=int(judge.get("confidence",50))
    return min(80,max(20,round(.85*evidence+.15*raw)))

def state(task,choice,conf):
    text=task["options"].get(choice,"").lower()
    if "cannot determine" in text or "insufficient information" in text:return "ABSTAIN"
    if not choice:return "INCONCLUSIVE"
    if conf>=70:return "STRONGLY_SUPPORTED"
    if conf>=55:return "PARTIALLY_SUPPORTED"
    if conf>=40:return "WEAK_EVIDENCE"
    return "INCONCLUSIVE"

def consensus3(stages):
    vals=[x.get("choice") for x in stages if x.get("choice") in set("ABCD")]
    if not vals:return {"choice":None,"confidence":0,"state":"INCONCLUSIVE"}
    c=Counter(vals); top=c.most_common()
    if len(top)>1 and top[0][1]==top[1][1]:return {"choice":None,"confidence":20,"state":"INCONCLUSIVE"}
    ch,n=top[0]; return {"choice":ch,"confidence":{3:72,2:56,1:35}.get(n,35),"state":"DIAGNOSTIC"}

def score(outputs,tasks):
    rows=[]
    for t in tasks:
        o=outputs.get(t.task_id,{}); ch=o.get("choice"); ok=ch==t.answer; txt=t.options.get(ch,"").lower(); rows.append({"id":t.task_id,"category":t.family,"choice":ch,"answer":t.answer,"ok":ok,"confidence":int(o.get("confidence",0)),"abstain":("cannot determine" in txt or "insufficient information" in txt)})
    correct=sum(r["ok"] for r in rows); probs=[r["confidence"]/100 for r in rows]; ys=[1.0 if r["ok"] else 0.0 for r in rows]; brier=sum((p-y)**2 for p,y in zip(probs,ys))/len(rows); mean=sum(probs)/len(probs); var=sum((p-mean)**2 for p in probs)/len(probs)
    bins=[(0,.4),(.4,.55),(.55,.7),(.7,.85),(.85,1.01)]; ece=0; buckets=[]
    for lo,hi in bins:
        idx=[i for i,p in enumerate(probs) if lo<=p<hi]
        if idx:
            cf=sum(probs[i] for i in idx)/len(idx); ac=sum(ys[i] for i in idx)/len(idx); ece+=len(idx)/len(rows)*abs(cf-ac); buckets.append({"range":[lo,hi],"n":len(idx),"confidence":round(cf,4),"accuracy":round(ac,4)})
    miss=[r for r in rows if r["category"]=="missing_information"]; got=[r for r in rows if r["abstain"]]
    return {"correct":correct,"n":len(rows),"accuracy":round(correct/len(rows),6),"brier":round(brier,6),"ece":round(ece,6),"confidence_variance":round(var,6),"abstains":len(got),"abstain_precision":round(sum(r["ok"] for r in got)/len(got),6) if got else 0.0,"abstain_recall":round(sum(r["ok"] for r in miss)/len(miss),6) if miss else 0.0,"rows":rows,"buckets":buckets}

def exact_p(new_wins,base_wins):
    n=new_wins+base_wins
    if n==0:return 1.0
    s=min(new_wins,base_wins); return min(1.0,2*sum(math.comb(n,k) for k in range(s+1))/(2**n))
