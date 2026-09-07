from pathlib import Path
from tempfile import TemporaryDirectory
from datetime import datetime, timezone
import json,sys
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
from fia_final_cockpit import api

def write_valid(root:Path):
    p=root/'data/shadow/brain_v6.jsonl'; p.parent.mkdir(parents=True,exist_ok=True)
    payload={'generated_at_utc':datetime.now(timezone.utc).isoformat(),'status':'OK','final':{'direction':'BULLISH','bullish_probability':60,'bearish_probability':40,'confidence':55},'result_sha256':'abc'}
    row={'created_at_utc':datetime.now(timezone.utc).isoformat(),'prev_hash':'0'*64,'payload':payload}
    row['record_hash']=api._shadow_sha256_obj(row)
    p.write_text(json.dumps(row,sort_keys=True,separators=(',',':'))+'\n',encoding='utf-8')
    anchor={'rows':1,'head_hash':row['record_hash']}; anchor['anchor_sha256']=api._shadow_sha256_obj(anchor)
    p.with_suffix(p.suffix+'.head.json').write_text(json.dumps(anchor,sort_keys=True,separators=(',',':')),encoding='utf-8')
    return p

with TemporaryDirectory() as d:
    root=Path(d); p=write_valid(root)
    x=api._latest_shadow(root)
    assert x and x.get('status')=='OK' and x.get('_ledger_integrity_ok') is True,x
    row=json.loads(p.read_text())
    row['payload']['final']['bullish_probability']=99
    p.write_text(json.dumps(row,sort_keys=True,separators=(',',':'))+'\n',encoding='utf-8')
    y=api._latest_shadow(root)
    assert y and y.get('status')=='INTEGRITY_ERROR' and y.get('_ledger_integrity_ok') is False,y
print('PASS test_sol56_shadow_integrity')
