from pathlib import Path
import sys, copy
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
from fia_brain.three_brain import freeze, verify, horizon_candidates, model_independence_metadata, ROLES

def a(p,d):
    return {'direction':d,'bullish_probability':p,'bearish_probability':100-p,'confidence':60,
            'thesis':'grounded','evidence_ids':['E1','E2'],'counter_evidence_ids':['E3'],
            'unknowns':[],'failure_conditions':[]}
raw={
 '4h':{'BULL':a(62,'BULLISH'),'BEAR':a(39,'BEARISH'),'DISCONFIRMING_CRITIC':a(50,'NO_EDGE')},
 '8h':{'BULL':a(64,'BULLISH'),'BEAR':a(37,'BEARISH'),'DISCONFIRMING_CRITIC':a(49,'NO_EDGE')},
}
f=freeze(raw,'ledger123','gpt-oss:20b')
assert verify(f)
assert set(f['cells']['4h'])==set(ROLES) and set(f['cells']['8h'])==set(ROLES)
assert f['same_model_agreement_is_independent_evidence'] is False
m=model_independence_metadata(f)
assert m['pipeline_count']==6 and m['same_model_agreement_is_independent_evidence'] is False
c4=horizon_candidates(f,4); c8=horizon_candidates(f,8)
assert c4[0]['bullish_probability']==62 and c8[0]['bullish_probability']==64
# returned candidates are copies; later mutation cannot rewrite the freeze
c4[0]['bullish_probability']=99
assert f['cells']['4h']['BULL']['analysis']['bullish_probability']==62
# any mutation inside the frozen packet invalidates it
bad=copy.deepcopy(f); bad['cells']['8h']['BEAR']['analysis']['confidence']=99
assert not verify(bad)
print('PASS test_three_brain_freeze_v74')
