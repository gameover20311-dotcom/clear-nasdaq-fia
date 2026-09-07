from pathlib import Path
import tempfile,json,sys
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
from fia_brain.benchmark import evaluate
from fia_brain.util import sha256_obj
from fia_brain.cases import bind_output
from fia_brain.evidence import build_ledger
final={"direction":"BULLISH","bullish_probability":60,"bearish_probability":40,"confidence":60,"thesis":"x","evidence_ids":["E0001"],"counter_evidence_ids":[],"unknowns":[],"failure_conditions":[]}
with tempfile.TemporaryDirectory() as d:
 d=Path(d); ledger=build_ledger({'snapshot_sha256':'S','payloads':{'/api/fia/dashboard':{'direction':'BULLISH'}}},100,10000)
 c={"case_id":"C1","split":"HOLDOUT","ledger_sha256":ledger['ledger_sha256'],"ledger":ledger}; c["case_sha256"]=sha256_obj(c)
 row=bind_output(c,{"final":final,"status":"OK","model":"x"})
 for name,obj in (("c",c),("l",row),("t",row)): (d/name).write_text(json.dumps(obj)+"\n")
 x=evaluate(d/"l",d/"t",d/"c",None,"HOLDOUT"); assert not x['complete_cohort'] and x['excluded'][0]['reason']=='v6_reasoning_signature_missing'
print('PASS test_holdout_reasoning_required_v6')
