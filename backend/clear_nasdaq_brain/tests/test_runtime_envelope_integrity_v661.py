from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from fia_brain.orchestrator import FIABrain
from fia_brain.evidence import build_ledger
from fia_brain.util import sha256_obj

cfg={
 'ollama_base_url':'http://127.0.0.1:11434','model':'gpt-oss:20b','mode':'max',
 'timeout_seconds':1,'num_ctx':1024,'reasoning_effort':'low','num_predict':64,
}
brain=FIABrain(cfg)
snap={'snapshot_sha256':'SNAP','payloads':{'/locked':{'target_close_8h':123.0,'price':100.0}}}
ledger=build_ledger(snap,max_records=20,max_chars=4000)
out=brain.analyze_ledger(ledger,write_shadow=False)
assert out['status']=='FAIL_CLOSED',out
assert out['model']=='gpt-oss:20b',out
assert out['snapshot_sha256']=='SNAP',out
assert out.get('result_sha256'),out
h=out['result_sha256']
core={k:v for k,v in out.items() if k!='result_sha256'}
assert sha256_obj(core)==h,(sha256_obj(core),h)
print('PASS test_runtime_envelope_integrity_v661')
