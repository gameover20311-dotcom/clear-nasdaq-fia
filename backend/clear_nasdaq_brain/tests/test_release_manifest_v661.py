from pathlib import Path
import sys,json,hashlib
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
obj=json.loads((ROOT/'MANIFEST.json').read_text(encoding='utf-8'))
assert obj['version']=='7.4.0-final-three-brain'
assert obj['invariants']['atomic_evidence_endpoint']=='/api/dashboard'
listed={x['path']:x for x in obj['files']}
def sha(p):
 h=hashlib.sha256();h.update(p.read_bytes());return h.hexdigest()
for rel,x in listed.items():
 p=ROOT/rel;assert p.is_file(),rel;assert p.stat().st_size==x['size'],rel;assert sha(p)==x['sha256'],rel
# Every active Python source/test/script must be represented.
for p in ROOT.rglob('*.py'):
 if '__pycache__' not in p.parts:
  rel=p.relative_to(ROOT).as_posix();assert rel in listed,rel
# V6.6.2: the guard used to reject only '.v6_*'. Four hidden backup trees named
# '.ledger_integrity_runtime_repair_backup_*', '.real_e2e_runtime_fix_backup_*' and
# '.runtime_probability_hotfix_backup_*' therefore sealed straight into the release,
# one of them holding a pre-fix orchestrator with no ledger-integrity gate.
# Reject ANY hidden directory that is not an explicitly allowed runtime dir.
_ALLOWED_HIDDEN=set()
_hidden=[p.name for p in ROOT.iterdir()
         if p.is_dir() and p.name.startswith('.') and p.name not in _ALLOWED_HIDDEN]
assert not _hidden, 'hidden backup/state dirs must not ship in the release: %r' % (_hidden,)
_stale=[p.name for p in ROOT.iterdir()
        if p.is_dir() and ('backup' in p.name.lower() or '_bak' in p.name.lower())]
assert not _stale, 'stale backup dirs must not ship in the release: %r' % (_stale,)
print('PASS test_release_manifest_v661')
