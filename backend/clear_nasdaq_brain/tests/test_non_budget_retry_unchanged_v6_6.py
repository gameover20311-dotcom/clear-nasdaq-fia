from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
from fia_brain.orchestrator import FIABrain

class FakeClient:
    def __init__(self): self.calls=[]
    def ask_json(self,*args,**kwargs):
        self.calls.append(kwargs)
        if len(self.calls)==1: raise RuntimeError('ordinary transient parse failure')
        return {'direction':'NEUTRAL','bullish_probability':50,'bearish_probability':50,'confidence':20,'thesis':'ok','evidence_ids':['E1'],'counter_evidence_ids':[],'unknowns':[],'failure_conditions':[]}

b=FIABrain.__new__(FIABrain); b.config={'num_predict':3072}; b.client=FakeClient(); b._runtime_events=[]
out=b._ask_analysis('X','x','E1 | s | p = v',{'E1'},effort='medium',num_ctx=16384,num_predict=1536,temp=0.05)
assert out['direction']=='NEUTRAL'
assert b.client.calls[1]['reasoning_effort']=='medium'
assert b.client.calls[1]['num_predict']==1536
assert b.client.calls[1]['temperature']==0.05
assert b._runtime_events==[]
print('PASS test_non_budget_retry_unchanged_v6_6')
