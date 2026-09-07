from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
from fia_brain.ensemble import aggregate
from fia_brain.probability_forge import forge
cands=[]
for p in (72,74,76):
    cands.append({'direction':'BULLISH','bullish_probability':p,'bearish_probability':100-p,'confidence':80,
                  'thesis':'x','evidence_ids':['E1','E2','E3'],'counter_evidence_ids':[],
                  'unknowns':[],'failure_conditions':[]})
ids={'E1','E2','E3'}
# All three evidence IDs are one source cluster: three agreeing model roles cannot manufacture independence.
clusters={'E1':'ONE_SOURCE','E2':'ONE_SOURCE','E3':'ONE_SOURCE'}
cons=aggregate(cands,ids,clusters)
cons['same_model_agreement_is_independent_evidence']=False
cons['independent_evidence_basis']='prediction_time_source_clusters_only'
chief={'direction':'BULLISH','bullish_probability':75,'bearish_probability':25,'confidence':80,'thesis':'x',
       'evidence_ids':['E1','E2','E3'],'counter_evidence_ids':[],'unknowns':[],'failure_conditions':[]}
sc={'worlds':[{'kind':'BULL','probability':65},{'kind':'BASE','probability':20},{'kind':'BEAR','probability':15}],'entropy':0.4}
trib={'grounding_score':90,'causal_score':90,'uncertainty_score':90,'recommended_confidence_cap':85,'fatal_flags':[]}
meta={'overall_uncertainty':15,'confidence_cap':85}
out,prov=forge(chief,cons,sc,trib,meta,{'fragile_to_single_driver':False},{'confidence_cap':90},clusters,None)
assert prov['supporting_independent_clusters']==1
assert out['direction']=='NO_EDGE'
assert 'insufficient_independent_support_clusters' in out['unknowns']
print('PASS test_three_brain_same_model_cluster_policy_v74')
