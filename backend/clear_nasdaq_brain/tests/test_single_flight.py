from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
from fia_brain.orchestrator import FIABrain
cfg={'ollama_base_url':'http://127.0.0.1:11434','model':'gpt-oss:20b','timeout_seconds':10,'num_ctx':4096,'reasoning_effort':'high',
'fia_base_url':'http://127.0.0.1:8001','endpoints':['/api/forecast'],'http_timeout_seconds':1,'max_evidence_records':20,'max_evidence_chars':4000,'max_fact_cards':20,
'minimum_endpoint_coverage':.5,'critical_endpoints':['/api/forecast'],'mode':'fast','shadow_ledger':str(ROOT/'data/shadow/test.jsonl'),'calibration_profile':''}
b=FIABrain(cfg); assert b._analysis_lock.acquire(blocking=False)
try:
 out=b.analyze(write_shadow=False); assert out['status']=='BUSY_FAIL_CLOSED'
finally: b._analysis_lock.release()
print('PASS test_single_flight')
