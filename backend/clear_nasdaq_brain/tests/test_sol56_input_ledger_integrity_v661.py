from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
from fia_brain.orchestrator import FIABrain
from fia_brain.evidence import validate_ledger_integrity

cfg={
    'ollama_base_url':'http://127.0.0.1:11434','model':'gpt-oss:20b','mode':'fast',
    'novelty_gate':False,'failure_memory_gate':False,'market_twin_gate':False,
    'scenario_entropy_gate':False,'num_ctx':4096,'num_predict':512,
    'reasoning_effort':'low','timeout_seconds':1,'max_fact_cards':10,
}
b=FIABrain(cfg)
b.client.health=lambda:{'ok':True,'model_present':True}
ledger={
    'snapshot_sha256':'x','record_count':1,
    'records':[{'evidence_id':'E0001','source':'/api/dashboard','path':'live.snapshot.data.nq_structure','value':'BULLISH','record_hash':'0'*64}],
    'ledger_sha256':'0'*64,
}
ok,errors=validate_ledger_integrity(ledger)
assert not ok and errors
called={'n':0}
def sentinel(*a,**k):
    called['n']+=1
    raise AssertionError('model must not be called for invalid ledger')
b._ask_analysis=sentinel
out=b.analyze_ledger(ledger,write_shadow=False)
assert out.get('status')=='FAIL_CLOSED',out
assert 'evidence_ledger_integrity_failed' in str(out.get('error')),out
assert called['n']==0,called
print('PASS test_sol56_input_ledger_integrity_v661')
