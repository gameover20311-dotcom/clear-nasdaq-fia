#!/usr/bin/env python3
from pathlib import Path
import json,sys
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
from fia_brain.cases import read_jsonl
from fia_brain.evidence_genome import build
from fia_brain.regime_memory import fit
from fia_brain.benchmark import case_hash
from fia_brain.evidence import validate_ledger_integrity
from fia_brain.util import sha256_obj
cases=[]
for c in read_jsonl(ROOT/'benchmarks/cases.jsonl'):
    if str(c.get('split')).upper()!='TRAIN': continue
    if str(c.get('case_sha256'))!=case_hash(c): raise SystemExit('tampered TRAIN case: '+str(c.get('case_id')))
    ok,errs=validate_ledger_integrity(c.get('ledger') or {})
    if not ok: raise SystemExit('invalid TRAIN ledger: '+str(c.get('case_id'))+':'+','.join(errs))
    cases.append(c)
g=[c.get('evidence_genome') or build(c['ledger']) for c in cases]
profile=fit(g,30); profile['source_case_sha256s']=[c['case_sha256'] for c in cases]; profile['profile_sha256']=sha256_obj(profile)
(ROOT/'benchmarks/regime_profile.json').write_text(json.dumps(profile,indent=2),encoding='utf-8')
print('fit verified TRAIN-only regime profile',profile['n'])
