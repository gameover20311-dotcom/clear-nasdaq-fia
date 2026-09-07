from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
from fia_brain.evidence import build_ledger,validate_ledger_integrity
s={'snapshot_sha256':'S','payloads':{'/api/fia/dashboard':{'ok':True,'live':{'forecast':{'direction':'BULLISH'}}}}}
l=build_ledger(s,100,100000)
ok,e=validate_ledger_integrity(l); assert ok,e
l['records'][0]['value']='TAMPERED'
ok,e=validate_ledger_integrity(l); assert not ok and any('record_hash_mismatch' in x for x in e)
print('PASS test_ledger_integrity_v5')
