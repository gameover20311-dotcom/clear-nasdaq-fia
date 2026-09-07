#!/usr/bin/env python3
from pathlib import Path
import hashlib,json
ROOT=Path(__file__).resolve().parents[1]
EXACT_EXCLUDE={'MANIFEST.json','SHA256SUMS.txt','RELEASE_REPORT_V6.json'}
EXCLUDE_PARTS={'__pycache__'}

def in_scope(p:Path)->bool:
    rel=p.relative_to(ROOT)
    if rel.as_posix() in EXACT_EXCLUDE:return False
    if any(x in rel.parts for x in EXCLUDE_PARTS):return False
    if p.suffix in {'.pyc','.pyo'}:return False
    # Mutable runtime ledgers/outputs are state, not immutable release code.
    if rel.parts[:2]==('data','shadow') and p.suffix in {'.jsonl','.lock','.json'}:return False
    if rel.parts[:2]==('data','memory') and p.suffix in {'.jsonl','.lock','.json'}:return False
    return p.is_file()

def sha(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()
files=[]
for p in sorted(ROOT.rglob('*')):
    if in_scope(p):files.append({'path':p.relative_to(ROOT).as_posix(),'size':p.stat().st_size,'sha256':sha(p)})
test_count=len(list((ROOT/'tests').glob('test_*.py')))
python_count=len([p for p in ROOT.rglob('*.py') if '__pycache__' not in p.parts])
obj={'name':'CLEAR NASDAQ — FIA BRAIN V7.4 FINAL THREE-BRAIN (V6.6.2 hardened base)','version':'7.4.0-final-three-brain','release_status':'ENGINEERING_RELEASE_GATE_PASS__REAL_E2E_REQUIRED_FOR_PRODUCTION','tests_expected':test_count,'python_files_checked':python_count,'invariants':{'zero_paid_api':True,'loopback_only':True,'local_model':'gpt-oss:20b','atomic_evidence_endpoint':'/api/dashboard','strict_output_schema':True,'directional_grounding_required':True,'correlation_aware_ensemble':True,'future_outcome_boundary':True,'failure_memory_external_head_anchor':True,'three_brain_pre_reconciliation_freeze':True,'separate_4h_8h_pipelines':True,'same_model_agreement_is_independent_evidence':False,'advisory_layers_post_freeze':True,'validator_evidence_window_is_superset_of_citations':True,'model_digest_pinned':True,'not_live_status_fails_closed':True,'freshness_measures_data_not_response':True,'timeout_aware_retry_ladder':True,'forward_oos_history_preservation_required':True,'base_fia_modified':False,'forward_oos_modified':False},'scope_note':'Hashes immutable release files; mutable runtime shadow/failure ledgers and release metadata files are excluded by design.','files':files}
(ROOT/'MANIFEST.json').write_text(json.dumps(obj,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
lines=[f"{x['sha256']}  {x['path']}" for x in files]
(ROOT/'SHA256SUMS.txt').write_text('\n'.join(lines)+'\n',encoding='utf-8')
print('manifest_files',len(files))
