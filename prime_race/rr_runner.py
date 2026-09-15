from __future__ import annotations
import hashlib,json,math,os,random,sys,time
from collections import Counter
from pathlib import Path
HERE=Path(__file__).resolve().parent
if str(HERE) not in sys.path: sys.path.insert(0,str(HERE))
import prime_repair_eval as core
import prime_repair_transfer_eval as transfer
import rr_uncertainty_tasks as extra
import rr_protocol as rp

POLICY="PRIME_REAL_REASONING_REPAIR_V2"
MODEL_ID=os.getenv("PRIME_REASONING_MODEL_ID","HuggingFaceTB/SmolLM2-360M-Instruct")
SEED=int(os.getenv("PRIME_REASONING_SEED","0")) or int.from_bytes(os.urandom(8),"big")
OUT=Path(os.getenv("PRIME_REASONING_OUT","prime_reasoning_v2_results")); OUT.mkdir(parents=True,exist_ok=True)

def h(x): return hashlib.sha256(json.dumps(x,sort_keys=True,separators=(",",":")).encode()).hexdigest()

def make_benchmark(seed):
    core_tasks=core.generate_tasks(seed ^ 0xA51C,4)
    transfer.SEED=seed ^ 0xB71D; t1=transfer.generate(seed ^ 0xC13F)
    transfer.SEED=seed ^ 0xD29A; t2=transfer.generate(seed ^ 0xE41B)
    u=extra.generate(seed ^ 0xF55D,10)
    tasks=list(core_tasks)+list(t1)+list(t2)+list(u)
    random.Random(seed ^ 0x7777).shuffle(tasks)
    if len(tasks)!=100 or len({t.task_id for t in tasks})!=100: raise RuntimeError("BENCHMARK_SIZE_OR_ID_FAILURE")
    source={t.task_id:"core" for t in core_tasks}
    source.update({t.task_id:"transfer_a" for t in t1}); source.update({t.task_id:"transfer_b" for t in t2}); source.update({t.task_id:"uncertainty" for t in u})
    return tasks,source

def bootstrap(base_ok,new_ok,seed=99173):
    rng=random.Random(seed); n=len(base_ok); vals=[]
    for _ in range(5000):
        ids=[rng.randrange(n) for _ in range(n)]; vals.append(sum(new_ok[i]-base_ok[i] for i in ids)/n)
    vals.sort(); return [round(vals[int(.025*len(vals))],6),round(vals[int(.975*len(vals))],6)]

def subset_acc(rows,categories):
    rr=[r for r in rows if r["category"] in categories]
    return round(sum(r["ok"] for r in rr)/len(rr),6) if rr else None

def contribution(traces,key):
    m=Counter()
    for tid,tr in traces.items():
        y=key[tid]; d=tr["new"]["draft"].get("choice"); a=tr["new"]["critic_a"].get("choice"); b=tr["new"]["critic_b"].get("choice"); j=tr["new"]["judge"].get("choice")
        if d!=y and a==y:m["ATTACK_A_RESCUES"]+=1
        if d==y and a!=y:m["ATTACK_A_HARMS"]+=1
        if d==a:m["ATTACK_A_AGREEMENTS"]+=1
        else:m["ATTACK_A_DISAGREEMENTS"]+=1
        if b==y and d!=y and a!=y:m["ATTACK_B_UNIQUE_RESCUES"]+=1
        if b!=y and (d==y or a==y):m["ATTACK_B_HARMS_CORRECT_PRIOR"]+=1
        if d!=y and a!=y and b!=y and j==y:m["JUDGE_RESCUES_ALL_THREE_WRONG"]+=1
        if j!=y and (d==y or a==y or b==y):m["JUDGE_HARMS_WHEN_PRIOR_HAD_CORRECT"]+=1
    return dict(m)

def selftest(tasks):
    cases={}
    cases["task_count_100"]=len(tasks)==100
    cases["unique_ids"]=len({t.task_id for t in tasks})==100
    cases["public_hides_answer_key"]='"answer"' not in json.dumps([t.public() for t in tasks],sort_keys=True)
    labels=Counter(t.answer for t in tasks); cases["answer_positions_diverse"]=all(labels.get(x,0)>10 for x in "ABCD")
    bad=False
    try:rp.parse("Mentions A and B but never selects one.")
    except RuntimeError:bad=True
    cases["strict_parser"]=bad and rp.parse('{"choice":"C","confidence":71}')["choice"]=="C"
    sample=tasks[0].public(); p,m=rp.stage_prompt(sample,42); cases["stage_mapping_is_permutation"]=set(m.keys())==set("ABCD") and set(m.values())==set("ABCD")
    cases["confidence_nonconstant"]=len({rp.confidence(["A","A","A","A"],{"choice":"A","confidence":50}),rp.confidence(["A","B","C","A"],{"choice":"A","confidence":50}),rp.confidence(["B","B","B","A"],{"choice":"A","confidence":50})})==3
    coverage=sum(core.deterministic_verify(t.public()) is not None for t in tasks); cases["verifier_partial_only"]=coverage<75
    passed=sum(bool(v) for v in cases.values())
    return {"pass":passed==len(cases),"passed":passed,"total":len(cases),"cases":cases,"verifier_coverage_pre_run":coverage,"answer_distribution":dict(labels)}

def run(tasks):
    import torch
    from transformers import AutoModelForCausalLM,AutoTokenizer
    torch.set_num_threads(max(1,min(2,os.cpu_count() or 1))); tok=AutoTokenizer.from_pretrained(MODEL_ID); model=AutoModelForCausalLM.from_pretrained(MODEL_ID,torch_dtype=torch.float32); model.eval()
    calls=Counter(); latency=Counter(); parse_errors=Counter(); tokens={"base":{"input":0,"output":0},"new":{"input":0,"output":0}}
    def call(system,user,lane):
        start=time.perf_counter(); msgs=[{"role":"system","content":system},{"role":"user","content":user}]; prompt=tok.apply_chat_template(msgs,tokenize=False,add_generation_prompt=True); inp=tok(prompt,return_tensors="pt")
        with torch.inference_mode(): out=model.generate(**inp,max_new_tokens=48,do_sample=False,pad_token_id=tok.eos_token_id)
        gen=out[0,inp["input_ids"].shape[1]:]; text=tok.decode(gen,skip_special_tokens=True).strip(); calls[lane]+=1; latency[lane]+=time.perf_counter()-start; tokens[lane]["input"]+=int(inp["input_ids"].numel()); tokens[lane]["output"]+=int(gen.numel())
        try:return rp.parse(text)
        except RuntimeError:parse_errors[lane]+=1; return {"choice":None,"confidence":0,"raw":text,"parse_error":True}
    base_out={}; new_out={}; hybrid={}; traces={}; ab={"draft":{},"attack_a_revision":{},"three_stage_consensus":{},"full_ai_judge":{},"hybrid_system":{}}
    for t in tasks:
        pub=t.public(); opts="\n".join(f"{k}. {v}" for k,v in pub["options"].items()); bp=f"TASK {pub['id']}\nCATEGORY: {pub['category']}\nQUESTION:\n{pub['question']}\n\nEVIDENCE:\n{pub['context']}\n\nOPTIONS:\n{opts}\n\nReturn JSON only: {{\"choice\":\"A|B|C|D\",\"confidence\":0-100}}."
        policy="Use only supplied evidence. Separate fact from assumption. Recheck before finalizing. Repeated calls to the same model are not independent evidence."
        d0=call(policy+" ROLE: initial analyst.",bp,"base"); a0=call(policy+" ROLE: critic. Re-evaluate the proposed answer.",bp+"\nPROPOSED="+json.dumps(d0,sort_keys=True),"base"); b0=call(policy+" ROLE: counter-review. Re-evaluate both candidate conclusions.",bp+"\nFIRST="+json.dumps(d0,sort_keys=True)+"\nSECOND="+json.dumps(a0,sort_keys=True),"base"); j0=call(policy+" ROLE: final judge.",bp+"\nFIRST="+json.dumps(d0,sort_keys=True)+"\nSECOND="+json.dumps(a0,sort_keys=True)+"\nTHIRD="+json.dumps(b0,sort_keys=True),"base")
        base_out[t.task_id]={"choice":j0.get("choice"),"confidence":j0.get("confidence",0),"state":"WEAK_EVIDENCE" if j0.get("choice") else "INCONCLUSIVE"}
        def ss(tag):return int(hashlib.sha256((t.task_id+tag).encode()).hexdigest()[:12],16)
        p1,m1=rp.stage_prompt(pub,ss(":D")); d=rp.canonical(call("ROLE: Independent Draft. "+rp.guide(t.family,"draft"),p1,"new"),m1)
        p2,m2=rp.stage_prompt(pub,ss(":A")); a=rp.canonical(call("ROLE: Critic A. "+rp.guide(t.family,"a"),p2+"\nPROPOSED="+rp.candidate_text(pub,d),"new"),m2)
        p3,m3=rp.stage_prompt(pub,ss(":B")); b=rp.canonical(call("ROLE: Critic B independent solver. "+rp.guide(t.family,"b"),p3,"new"),m3)
        p4,m4=rp.stage_prompt(pub,ss(":J")); candidates="\nLOCKED CANDIDATES:\nDRAFT="+rp.candidate_text(pub,d)+"\nCRITIC_A="+rp.candidate_text(pub,a)+"\nCRITIC_B="+rp.candidate_text(pub,b); j=rp.canonical(call("ROLE: Final Judge. "+rp.guide(t.family,"judge")+" Solve the original task independently before comparing candidates.",p4+candidates,"new"),m4)
        conf=rp.confidence([d.get("choice"),a.get("choice"),b.get("choice"),j.get("choice")],j); final={"choice":j.get("choice"),"confidence":conf,"state":rp.state(pub,j.get("choice"),conf),"source":"AI_REASONING_ONLY_FINAL_JUDGE","evidence_independence":"DEPENDENCE_NOT_EXCLUDABLE"}; new_out[t.task_id]=final
        ver=core.deterministic_verify(pub); hyb=dict(ver) if ver else dict(final); hyb["evidence_independence"]="DEPENDENCE_NOT_EXCLUDABLE"; hybrid[t.task_id]=hyb
        ab["draft"][t.task_id]={"choice":d.get("choice"),"confidence":d.get("confidence",0)}; ab["attack_a_revision"][t.task_id]={"choice":a.get("choice"),"confidence":a.get("confidence",0)}; ab["three_stage_consensus"][t.task_id]=rp.consensus3([d,a,b]); ab["full_ai_judge"][t.task_id]=final; ab["hybrid_system"][t.task_id]=hyb
        traces[t.task_id]={"base":{"draft":d0,"critic":a0,"counter":b0,"judge":j0},"new":{"draft":d,"critic_a":a,"critic_b":b,"judge":j,"verifier":ver,"final_ai":final,"final_hybrid":hyb}}
    return {"base":base_out,"new":new_out,"hybrid":hybrid,"ablations":ab,"traces":traces,"calls":dict(calls),"tokens":tokens,"parse_errors":dict(parse_errors),"latency_seconds":{k:round(v,3) for k,v in latency.items()}}

def main():
    tasks,sources=make_benchmark(SEED); reg=selftest(tasks)
    if not reg["pass"]:raise SystemExit("SELFTEST_FAILED:"+json.dumps(reg,sort_keys=True))
    public=[t.public() for t in tasks]; key={t.task_id:t.answer for t in tasks}; manifest={"policy":POLICY,"seed":SEED,"task_count":100,"taskset_id":f"PRIME_REAL_REASONING_{SEED}_100","taskset_hash":h(public),"answer_key_hash":h(key),"model_id":MODEL_ID,"source_counts":dict(Counter(sources.values())),"answers_hidden_from_model":True,"lane_a":"AI_REASONING_ONLY","lane_b":"HYBRID_SYSTEM","scoring_frozen_before_execution":True}
    (OUT/"benchmark_manifest_pre_execution.json").write_text(json.dumps(manifest,indent=2,sort_keys=True))
    model=run(tasks); locked={"base":model["base"],"new":model["new"],"hybrid":model["hybrid"],"ablations":model["ablations"]}; (OUT/"locked_outputs_before_scoring.json").write_text(json.dumps(locked,indent=2,sort_keys=True)); lock_hash=h(locked)
    bs=rp.score(model["base"],tasks); ns=rp.score(model["new"],tasks); hs=rp.score(model["hybrid"],tasks); abscores={k:rp.score(v,tasks) for k,v in model["ablations"].items()}; contrib=contribution(model["traces"],key)
    bok=[int(r["ok"]) for r in bs["rows"]]; nok=[int(r["ok"]) for r in ns["rows"]]; nw=sum(n>b for b,n in zip(bok,nok)); bw=sum(b>n for b,n in zip(bok,nok)); ties=100-nw-bw; paired={"new_wins":nw,"base_wins":bw,"ties":ties,"accuracy_difference":round(ns["accuracy"]-bs["accuracy"],6),"exact_two_sided_p":round(rp.exact_p(nw,bw),8),"bootstrap_95_ci":bootstrap(bok,nok)}
    integrity=set(core.INTEGRITY_FAMILIES); bs_int=subset_acc(bs["rows"],integrity); ns_int=subset_acc(ns["rows"],integrity); verifier_coverage=sum(model["traces"][t.task_id]["new"]["verifier"] is not None for t in tasks)
    checks={"task_count_100":True,"lane_a_no_verifier_override":all(model["new"][t.task_id].get("source")=="AI_REASONING_ONLY_FINAL_JUDGE" for t in tasks),"accuracy_gain_at_least_0_08":ns["accuracy"]-bs["accuracy"]>=.08,"paired_p_at_most_0_05":paired["exact_two_sided_p"]<=.05,"ci_lower_above_zero":paired["bootstrap_95_ci"][0]>0,"full_judge_beats_draft_by_0_03":abscores["full_ai_judge"]["accuracy"]-abscores["draft"]["accuracy"]>=.03,"judge_rescues_exceed_harms":contrib.get("JUDGE_RESCUES_ALL_THREE_WRONG",0)>contrib.get("JUDGE_HARMS_WHEN_PRIOR_HAD_CORRECT",0),"confidence_non_degenerate":ns["confidence_variance"]>=.0025,"confidence_ece_at_most_0_20":ns["ece"]<=.20,"confidence_brier_better_than_base":ns["brier"]<bs["brier"],"integrity_not_regressed":ns_int>=bs_int,"verifier_not_responsible_for_lane_a":True,"equal_primary_call_budget":model["calls"].get("base")==model["calls"].get("new")==400,"zero_api_cost":True}
    decision="PROMOTE" if all(checks.values()) else "DO_NOT_PROMOTE"
    bundle={"policy":POLICY,"benchmark":manifest,"output_lock_sha256":lock_hash,"selftest":reg,"base_score":bs,"ai_reasoning_score":ns,"hybrid_system_score":hs,"ablation_scores":abscores,"contribution_metrics":contrib,"paired_analysis":paired,"integrity_accuracy":{"base":bs_int,"new":ns_int},"verifier_coverage":{"count":verifier_coverage,"fraction":verifier_coverage/100},"calls":model["calls"],"tokens":model["tokens"],"parse_errors":model["parse_errors"],"latency_seconds":model["latency_seconds"],"promotion_checks":checks,"promotion_decision":decision,"api_cost_usd":0.0,"sources":sources,"public_tasks":public,"hidden_answer_key_after_lock":key,"traces":model["traces"]}; bundle["bundle_sha256"]=h(bundle); (OUT/"bundle.json").write_text(json.dumps(bundle,indent=2,sort_keys=True))
    summary={k:v for k,v in bundle.items() if k not in {"public_tasks","hidden_answer_key_after_lock","traces","sources"}}; summary["base_score"]={k:v for k,v in bs.items() if k!="rows"}; summary["ai_reasoning_score"]={k:v for k,v in ns.items() if k!="rows"}; summary["hybrid_system_score"]={k:v for k,v in hs.items() if k!="rows"}; summary["ablation_scores"]={k:{kk:vv for kk,vv in v.items() if kk!="rows"} for k,v in abscores.items()}; (OUT/"summary.json").write_text(json.dumps(summary,indent=2,sort_keys=True)); print(json.dumps(summary,indent=2,sort_keys=True))

if __name__=="__main__":main()
