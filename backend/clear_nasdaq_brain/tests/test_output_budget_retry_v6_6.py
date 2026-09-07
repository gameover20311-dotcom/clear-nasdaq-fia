from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
from fia_brain.orchestrator import FIABrain
from fia_brain.local_llm import LocalModelError

class FakeClient:
    def __init__(self): self.calls=[]
    def ask_json(self,*args,**kwargs):
        self.calls.append(kwargs)
        if len(self.calls)==1:
            raise LocalModelError('model did not return one parseable JSON object; done_reason=length; content_chars=0')
        return {
            'direction':'NEUTRAL','bullish_probability':50,'bearish_probability':50,
            'confidence':20,'thesis':'retry ok','evidence_ids':['E1'],
            'counter_evidence_ids':[],'unknowns':[],'failure_conditions':[]
        }

b=FIABrain.__new__(FIABrain)
b.config={'num_predict':3072}; b.client=FakeClient(); b._runtime_events=[]
evidence=('E1 | src | path = x\n')*3000
out=b._ask_analysis('SPECIALIST_CATALYST_FRESHNESS','x',evidence,{'E1'},effort='medium',num_ctx=16384,num_predict=1536)
assert out['direction']=='NEUTRAL'
assert len(b.client.calls)==2
assert b.client.calls[0]['reasoning_effort']=='medium' and b.client.calls[0]['num_predict']==1536
assert b.client.calls[1]['reasoning_effort']=='low' and b.client.calls[1]['num_predict']==3072
assert b.client.calls[1]['temperature']==0.0
assert b._runtime_events and b._runtime_events[0]['event']=='OUTPUT_BUDGET_RETRY'
assert b._runtime_events[0]['evidence_chars_after'] <= 24000
print('PASS test_output_budget_retry_v6_6')
