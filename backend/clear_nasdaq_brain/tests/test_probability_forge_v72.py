from pathlib import Path
import sys,copy
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from fia_brain.probability_forge import forge

def chief(p=70,d='BULLISH',c=80,e=None,ce=None):
    return {'direction':d,'bullish_probability':p,'bearish_probability':100-p,'confidence':c,'thesis':'x',
            'evidence_ids':e or ['E1','E2','E3'],'counter_evidence_ids':ce or ['E4'],'unknowns':[],'failure_conditions':[]}
def consensus(p=68,spread=5,c=75):
    return {'direction':'BULLISH' if p>=56 else ('BEARISH' if p<=44 else 'NO_EDGE'),'bullish_probability':p,'bearish_probability':100-p,
            'confidence':c,'probability_spread_std':spread,'evidence_ids':['E1','E2'],'counter_evidence_ids':['E4']}
def scenarios(bull=55,base=25,bear=20,entropy=.7):
    return {'worlds':[{'kind':'BULL','probability':bull},{'kind':'BASE','probability':base},{'kind':'BEAR','probability':bear}],'entropy':entropy}
trib={'grounding_score':90,'causal_score':88,'uncertainty_score':85,'recommended_confidence_cap':82,'fatal_flags':[]}
meta={'overall_uncertainty':20,'confidence_cap':85}
inter={'fragile_to_single_driver':False}
sq={'confidence_cap':90}
clusters={'E1':'C1','E2':'C2','E3':'C3','E4':'C4'}

# aligned case remains directional, bounded and auditable
x,prov=forge(chief(),consensus(),scenarios(),trib,meta,inter,sq,clusters,None)
assert x['direction']=='BULLISH',x
assert 56<=x['bullish_probability']<=75,x
assert x['bearish_probability']==round(100-x['bullish_probability'],2)
assert prov['probability_provenance_sha256'] and prov['supporting_independent_clusters']==3

# severe disagreement shrinks/abstains rather than preserving false precision
x,_=forge(chief(82,'BULLISH',85),consensus(48,28,55),scenarios(25,40,35,.98),trib,{'overall_uncertainty':82,'confidence_cap':45},inter,sq,clusters,None)
assert x['direction']=='NO_EDGE',x
assert abs(x['bullish_probability']-50)<10,x
assert x['confidence']<=45,x

# one independent cluster cannot sustain directional conviction
one={'E1':'C1','E2':'C1','E3':'C1','E4':'C2'}
x,_=forge(chief(72,'BULLISH',80,['E1','E2','E3']),consensus(70,4),scenarios(60,20,20,.5),trib,meta,inter,sq,one,None)
assert x['direction']=='NO_EDGE',x
assert x['confidence']<=40,x
assert 'insufficient_independent_support_clusters' in x['unknowns']

# mature empirical calibration may permit more probability range, but never >80/20 here
profile={'enabled':True,'resolved_n':80}
x,prov=forge(chief(88,'BULLISH',85),consensus(84,2,82),scenarios(82,10,8,.25),trib,{'overall_uncertainty':8,'confidence_cap':90},inter,sq,clusters,profile)
assert prov['mature_empirical_calibration'] is True
assert x['bullish_probability']<=80.0,x

# deterministic / no input mutation
c=chief(); before=copy.deepcopy(c)
x1,p1=forge(c,consensus(),scenarios(),trib,meta,inter,sq,clusters,None)
x2,p2=forge(c,consensus(),scenarios(),trib,meta,inter,sq,clusters,None)
assert c==before
assert x1==x2 and p1==p2
print('PASS test_probability_forge_v72')
