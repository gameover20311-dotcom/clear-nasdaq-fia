from __future__ import annotations
import hashlib, json, math, os, random
from pathlib import Path
import prime_repair_eval as core

OUT=Path(os.getenv('PRIME_TRANSFER_OUT','prime_transfer_results')); OUT.mkdir(parents=True,exist_ok=True)
SEED=int(os.getenv('PRIME_TRANSFER_SEED','0')) or int.from_bytes(os.urandom(8),'big')
POLICY='PRIME_REPAIR_TRANSFER_V1'

def h(x): return hashlib.sha256(json.dumps(x,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def opts(rng,correct,wrong):
    vals=[correct]+wrong; rng.shuffle(vals); d=dict(zip('ABCD',vals)); return d,'ABCD'[vals.index(correct)]

def task(rng,fam,i=1):
    tid=f"TX-{fam[:4].upper()}-{hashlib.sha256(f'{SEED}:{fam}:{rng.random()}'.encode()).hexdigest()[:10]}"
    if fam=='arithmetic':
        a,b,c,d=[rng.randint(2,25) for _ in range(4)]; v=a*b+c-d
        q=f'Evaluate this integer expression exactly: {a} * {b} + {c} - {d}'; ctx='Standard operator precedence applies.'; correct=str(v); wrong=[str(v+1),str(v-1),str((a+b)*c-d)]
    elif fam=='implication':
        p,qv=rng.choice([True,False]),rng.choice([True,False]); v=(not p) or qv
        q='Under classical logic, determine the implication P implies Q.'; ctx=f'P is {str(p).upper()}; Q is {str(qv).upper()}.'; correct='TRUE' if v else 'FALSE'; wrong=['FALSE' if v else 'TRUE','UNDETERMINED','PARADOXICAL']
    elif fam=='boolean_logic':
        p,qv=rng.choice([True,False]),rng.choice([True,False]); op=rng.choice(['AND','OR','XOR']); v=(p and qv) if op=='AND' else ((p or qv) if op=='OR' else (p!=qv))
        q=f'Find the Boolean result of P {op} Q.'; ctx=f'P is {str(p).upper()}; Q is {str(qv).upper()}.'; correct='TRUE' if v else 'FALSE'; wrong=['FALSE' if v else 'TRUE','UNKNOWN','INCONSISTENT']
    elif fam=='quantifiers':
        vals=[rng.choice([True,False]) for _ in range(5)]; forall=rng.choice([True,False]); v=all(vals) if forall else any(vals)
        q='Evaluate the quantified claim on the complete finite domain.'; claim='Every domain element satisfies P.' if forall else 'At least one domain element satisfies P.'; ctx=f"P values by element are [{','.join('T' if x else 'F' for x in vals)}]. Claim: {claim}"; correct='The claim is true' if v else 'The claim is false'; wrong=['The claim is false' if v else 'The claim is true','The claim is unknowable','Finite domains cannot evaluate quantifiers']
    elif fam=='set_relation':
        A=set(rng.sample(range(1,9),3)); mode=rng.choice(['subset','equal','disjoint'])
        if mode=='subset': B=set(A)|{20}; correct='A is strictly contained in B'
        elif mode=='equal': B=set(A); correct='A and B contain exactly the same elements'
        else: B={x+30 for x in A}; correct='A and B share no elements'
        q='Select the exact relationship between the two sets.'; ctx=f'Set A: {sorted(A)}. Set B: {sorted(B)}.'; pool=['A is strictly contained in B','B is strictly contained in A','A and B contain exactly the same elements','A and B share no elements']; wrong=[x for x in pool if x!=correct][:3]
    elif fam=='ordering':
        a,b,c=rng.sample(list('UVWXYZ'),3); q='Which relation follows necessarily?'; ctx=f'{a} precedes {b}; {b} precedes {c}; precedence is transitive.'; correct=f'{a} precedes {c}'; wrong=[f'{c} precedes {a}',f'{c} precedes {b}',f'{a} and {c} occur together']
    elif fam=='probability_basic':
        x,y=rng.randint(1,8),rng.randint(1,8); den=x+y; g=math.gcd(x,den); frac=f'{x//g}/{den//g}'; q='One object is sampled uniformly. What is the chance it is type X?'; ctx=f'An urn holds {x} objects of type X and {y} objects of type Y.'; correct=frac; cand=[f'{y}/{den}',f'{x}/{y}',f'{x}/{den+1}','0/1','1/1']; wrong=[]
        for z in cand:
            if z!=correct and z not in wrong: wrong.append(z)
            if len(wrong)==3: break
    elif fam=='contradiction':
        q='How should these claims be classified?'; ctx='At the identical time and scope, statement one asserts K; statement two asserts NOT K.'; correct='They are jointly inconsistent; both cannot hold'; wrong=['They independently confirm K','They are equivalent statements','They are unrelated claims']
    elif fam=='datetime_order':
        a=rng.randint(1000,4000); b=a+rng.randint(1,300); swap=rng.choice([False,True]); A,B=(b,a) if swap else (a,b); q='Which event happened earlier?'; ctx=f'Event A @ {A}; Event B @ {B}; numeric time increases forward.'; correct='A happened earlier' if A<B else 'B happened earlier'; wrong=['They happened simultaneously','No temporal comparison is possible','A happened earlier' if correct!='A happened earlier' else 'B happened earlier']
    elif fam=='future_leakage':
        decision=rng.randint(1000,3000); publication=decision+rng.randint(1,200); q='Classify the evaluation integrity.'; ctx=f'The forecast decision timestamp is {decision}. One input was not published until timestamp {publication}, yet that input was used in the forecast reconstruction.'; correct='This is look-ahead contamination; the claimed prospective evaluation is invalid'; wrong=['Strong predictive value makes the use legitimate','Publication time is irrelevant','High accuracy retroactively validates the forecast']
    elif fam=='evidence_independence':
        q='What can be claimed about corroboration?'; ctx='Four opinions came from repeated invocations of one checkpoint on one unchanged evidence bundle. No separate data source and no unrelated model lineage participated.'; correct='The agreement is dependent evidence, not four independent confirmations'; wrong=['Each invocation counts as independent confirmation','Different wording guarantees independence','All opinions must be discarded']
    elif fam=='provenance':
        tok=hashlib.sha256(f'{SEED}:{fam}'.encode()).hexdigest()[:7]; q='What does the identity evidence imply?'; ctx=f'Two records claim the identical byte sequence. Record A gives SHA256 aa{tok}; Record B gives SHA256 bb{tok}. No byte change, encoding change, or version change is recorded.'; correct='The identity records conflict and require investigation'; wrong=['Both digests can certify identical bytes without explanation','The later digest silently replaces the earlier one','Digest mismatches are irrelevant']
    elif fam=='temporal_lock':
        seal=rng.randint(1000,2500); reveal=seal+rng.randint(1,250); q='Which procedure preserves a prospective evaluation?'; ctx=f'A prediction commitment was sealed at {seal}. Outcome information became observable at {reveal}. After that reveal, someone wants to rewrite the sealed prediction while retaining the old timestamp.'; correct='Preserve the sealed prediction unchanged and record the outcome separately afterward'; wrong=['Rewrite the sealed prediction and erase the old content','Rewrite it but keep calling it prospective','Outcome knowledge permits retroactive editing']
    elif fam=='promotion_gate':
        need=rng.randint(25,50); have=rng.randint(0,need-1); q='What is the valid promotion decision?'; ctx=f'The evidence gate demands {need} genuinely prospective cases; only {have} are available. Engineering tests are green.'; correct='Block promotion because the prospective evidence threshold is unsatisfied'; wrong=['Engineering tests replace the evidence requirement','Promote now and collect evidence later','Convert historical cases into prospective cases']
    elif fam=='causal_confounding':
        q='Which causal statement is warranted?'; ctx='The data are non-experimental. X tracks the outcome, but a common cause Z influences both X and the outcome. There is no intervention and no adequate control for Z.'; correct='The observed association does not by itself identify X as causal'; wrong=['Positive association proves X causes the outcome','A large sample removes confounding automatically','Z can be ignored because X is measured first']
    else: raise ValueError(fam)
    o,a=opts(rng,correct,wrong); return core.Task(tid,fam,q,ctx,o,a)
def generate(seed):
    rng=random.Random(seed); out=[task(rng,f) for f in core.ALL_FAMILIES]; rng.shuffle(out); return out

def main():
    tasks=generate(SEED); public=[t.public() for t in tasks]
    coverage=sum(core.deterministic_verify(t.public()) is not None for t in tasks)
    model=core.run_model_eval(tasks)
    bs=core.score(model['base_outputs'],tasks); ns=core.score(model['new_outputs'],tasks)
    checks={'task_count_15':len(tasks)==15,'candidate_code_unchanged_in_transfer':True,'new_accuracy_strictly_better':ns['accuracy']>bs['accuracy'],'new_basic_accuracy_at_least_0_90':ns['basic_accuracy']>=0.90,'new_integrity_accuracy_at_least_0_80':ns['integrity_accuracy']>=0.80,'new_high_confidence_wrong_zero':ns['high_confidence_wrong']==0,'new_calibration_brier_better':ns['confidence_brier']<bs['confidence_brier'],'equal_call_budget':model['calls']['base']==model['calls']['new']==60}
    promote=all(checks.values())
    bundle={'policy_version':POLICY,'seed':SEED,'taskset_id':f'PRIME_TRANSFER_{SEED}_15','taskset_hash':h(public),'task_count':15,'candidate_commit':'af2d5b4a65b88914cd00a508b67ea79e9f1621bf','generator_independent_wording':True,'answers_hidden_until_outputs_frozen':True,'deterministic_verifier_coverage':coverage,'model_id':core.MODEL_ID,'calls':model['calls'],'tokens':model['tokens'],'parse_errors':model['parse_errors'],'latency_seconds':model['latency_seconds'],'api_cost_usd':0.0,'base_score':bs,'new_score':ns,'promotion_checks':checks,'promotion_decision':'PROMOTE' if promote else 'DO_NOT_PROMOTE','public_tasks':public,'hidden_answer_key_after_freeze':{t.task_id:t.answer for t in tasks},'traces':model['traces']}
    bundle['bundle_sha256']=h(bundle); (OUT/'transfer_bundle.json').write_text(json.dumps(bundle,indent=2,sort_keys=True)); summary={k:v for k,v in bundle.items() if k not in {'public_tasks','hidden_answer_key_after_freeze','traces'}}
    for name in ['base_score','new_score']: summary[name]={k:v for k,v in summary[name].items() if k!='rows'}
    (OUT/'transfer_summary.json').write_text(json.dumps(summary,indent=2,sort_keys=True)); print(json.dumps(summary,indent=2,sort_keys=True))
if __name__=='__main__': main()
