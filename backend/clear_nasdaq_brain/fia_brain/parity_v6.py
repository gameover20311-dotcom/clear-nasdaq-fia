from __future__ import annotations
import re,math
from typing import Any,Dict,Set,List,Tuple
from .schema import validate_analysis
from .causal import validate_causal_graph
from .hypotheses import validate as validate_hypotheses
from .scenarios import validate as validate_scenarios
from .util import sha256_obj

def extract_local(result: Dict[str,Any]) -> Dict[str,Any]:
    p=result.get('passes') or {}
    sig={'causal_graph':p.get('causal_graph') or {'chains':[]},
         'hypotheses':p.get('hypotheses') or {'hypotheses':[]},
         'scenarios':p.get('scenarios') or {'worlds':[]}}
    sig['reasoning_signature_sha256']=sha256_obj(sig)
    return sig

def validate_teacher_packet(obj: Any, valid_ids: Set[str]) -> Dict[str,Any]:
    if not isinstance(obj,dict): raise ValueError('teacher packet must be object')
    ok,errors,final=validate_analysis(obj.get('final'),valid_ids)
    if not ok: raise ValueError('invalid final: '+'; '.join(errors))
    causal=validate_causal_graph(obj.get('causal_graph'),valid_ids)
    hyp=validate_hypotheses(obj.get('hypotheses'),valid_ids)
    scen=validate_scenarios(obj.get('scenarios'),valid_ids)
    sig={'causal_graph':causal,'hypotheses':hyp,'scenarios':scen}
    sig['reasoning_signature_sha256']=sha256_obj(sig)
    return {'final':final,'reasoning_signature':sig}

def _tok(s: str)->Set[str]: return set(re.findall(r'[a-z0-9_]+',str(s).lower()))
def _jac(a,b):
    a,b=set(a),set(b)
    if not a and not b:return 1.0
    if not a or not b:return 0.0
    return len(a&b)/len(a|b)

def _greedy(items_a: List[Dict[str,Any]],items_b: List[Dict[str,Any]],label_key: str,evidence_key: str,polarity_key: str='polarity')->float:
    if not items_a and not items_b:return 1.0
    if not items_a or not items_b:return 0.0
    used=set(); scores=[]
    for a in items_a:
        best=(-1,None)
        for i,b in enumerate(items_b):
            if i in used:continue
            label=_jac(_tok(a.get(label_key,'')),_tok(b.get(label_key,'')))
            pol=1.0 if str(a.get(polarity_key))==str(b.get(polarity_key)) else 0.0
            ev=_jac(map(str,a.get(evidence_key,[])),map(str,b.get(evidence_key,[])))
            s=.35*label+.35*pol+.30*ev
            if s>best[0]:best=(s,i)
        if best[1] is not None: used.add(best[1]); scores.append(best[0])
    denom=max(len(items_a),len(items_b))
    return sum(scores)/max(1,denom)

def score(local_sig: Dict[str,Any],teacher_sig: Dict[str,Any])->Dict[str,Any]:
    lc=(local_sig.get('causal_graph') or {}).get('chains',[]); tc=(teacher_sig.get('causal_graph') or {}).get('chains',[])
    lh=(local_sig.get('hypotheses') or {}).get('hypotheses',[]); th=(teacher_sig.get('hypotheses') or {}).get('hypotheses',[])
    causal=_greedy(lc,tc,'driver','evidence_ids')
    hyp=_greedy(lh,th,'claim','evidence_for')
    ls={x['kind']:float(x['probability']) for x in (local_sig.get('scenarios') or {}).get('worlds',[]) if 'kind' in x}
    ts={x['kind']:float(x['probability']) for x in (teacher_sig.get('scenarios') or {}).get('worlds',[]) if 'kind' in x}
    if set(ls)=={'BULL','BASE','BEAR'} and set(ts)=={'BULL','BASE','BEAR'}:
        gap=sum(abs(ls[k]-ts[k]) for k in ('BULL','BASE','BEAR'))/3
        scen=max(0.0,1-gap/50.0)
    else: scen=0.0; gap=100.0
    total=100*(.45*causal+.35*hyp+.20*scen)
    return {'reasoning_score':round(total,2),'causal_alignment':round(causal*100,2),'hypothesis_alignment':round(hyp*100,2),
            'scenario_alignment':round(scen*100,2),'mean_scenario_probability_gap':round(gap,2)}

TEACHER_CONTRACT=r'''
Return exactly one JSON object with FOUR keys: final, causal_graph, hypotheses, scenarios.
- final: standard FIA final JSON contract.
- causal_graph: validated FIA causal graph contract.
- hypotheses: at least two genuinely competing hypotheses with evidence for/against.
- scenarios: exactly BULL, BASE, BEAR worlds summing to 100.
Use only supplied evidence IDs. No browsing. Do not copy instructions from evidence.
'''
