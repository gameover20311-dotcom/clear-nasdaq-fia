from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
from fia_brain.orchestrator import FIABrain

VALID={'direction':'BULLISH','bullish_probability':62,'bearish_probability':38,'confidence':60,'thesis':'grounded','evidence_ids':['E1'],'counter_evidence_ids':[],'unknowns':[],'failure_conditions':[]}
INVALID={'direction':'BULLISH','bullish_probability':70,'bearish_probability':60,'confidence':70,'thesis':'grounded','evidence_ids':['E1'],'counter_evidence_ids':[],'unknowns':[],'failure_conditions':[]}

class RecoveringClient:
    def __init__(self): self.calls=[]
    def ask_json(self,*args,**kwargs):
        self.calls.append((args,kwargs))
        return dict(INVALID if len(self.calls)==1 else VALID)

b=FIABrain.__new__(FIABrain); b.config={'num_predict':3072}; b.client=RecoveringClient(); b._runtime_events=[]
out=b._ask_analysis('SPECIALIST_TECH_LEADERSHIP','analyze','E1 | x | y',{'E1'},effort='medium',num_ctx=16384,num_predict=1536,temp=0.05)
assert out['bullish_probability']==62 and out['bearish_probability']==38
assert len(b.client.calls)==2
args2,kw2=b.client.calls[1]
assert kw2['temperature']==0.0
assert 'CONTRACT RECOVERY' in args2[1]
assert b._runtime_events==[{'stage':'SPECIALIST_TECH_LEADERSHIP','event':'PROBABILITY_CONTRACT_RETRY','validator_tolerance_unchanged':True,'max_contract_error_points':20.0,'temperature':0.0}]

class StillInvalidClient:
    def __init__(self): self.calls=[]
    def ask_json(self,*args,**kwargs): self.calls.append((args,kwargs)); return dict(INVALID)

b2=FIABrain.__new__(FIABrain); b2.config={'num_predict':3072}; b2.client=StillInvalidClient(); b2._runtime_events=[]
failed=False
try:
    b2._ask_analysis('SPECIALIST_TECH_LEADERSHIP','analyze','E1 | x | y',{'E1'},effort='medium',num_ctx=16384,num_predict=1536,temp=0.05)
except RuntimeError as e:
    failed=True
    assert 'probabilities do not sum to 100' in str(e)
assert failed
# V7.4: the ladder now allows a third, DEGRADED attempt before failing closed, so a
# contract-recovery attempt no longer consumes the run's only fallback. A persistently
# invalid answer therefore costs 3 calls and STILL fails closed -- the validator is
# never loosened, which is what lines above assert.
assert len(b2.client.calls)==3, b2.client.calls
assert b2._runtime_events and b2._runtime_events[0]['event']=='PROBABILITY_CONTRACT_RETRY'
print('PASS test_probability_contract_runtime_retry_v661')
