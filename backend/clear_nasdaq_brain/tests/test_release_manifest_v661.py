# CLEAR NASDAQ BRAIN — release manifest integrity (v661, revised for manifest r2)
#
# WHY THIS FILE CHANGED
# --------------------
# MANIFEST.json revision 1 did not describe its own payload. Commit 258cd9c
# ("Add Groq GPT-OSS 20B cloud brain adapter") edited three shipped files and
# added a fourth without refreshing the manifest, so the release shipped an
# integrity record that disagreed with the bytes it claimed to cover:
#
#   fia_brain/config.py        recorded 8582   actual 9720
#   fia_brain/orchestrator.py  recorded 22080  actual 24219
#   fia_brain/sidecar.py       recorded 3630   actual 3715
#   fia_brain/cloud_llm.py     not recorded at all
#
# Revision 2 records the payload as it actually is. The correction is NOT
# retroactive and revision 1 is NOT forgotten: the manifest carries an explicit
# supersession record naming revision 1's own SHA-256, the commit that produced
# it, every entry it misdescribed and the entry it omitted. This check enforces
# that the audit trail stays present, so the defect cannot be quietly erased by
# a later regeneration.
#
# SCOPE: this is engineering release metadata only. It is not a Forward-OOS
# campaign seal, not a protected scientific artifact, and not historical
# evidence. Nothing here reseals, backfills or re-registers anything.
from pathlib import Path
import sys, json, hashlib

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
obj = json.loads((ROOT / 'MANIFEST.json').read_text(encoding='utf-8'))

assert obj['version'] == '7.4.0-final-three-brain'
assert obj['invariants']['atomic_evidence_endpoint'] == '/api/dashboard'


def sha(p):
    h = hashlib.sha256()
    h.update(p.read_bytes())
    return h.hexdigest()


# ---------------------------------------------------------------- payload ---
# Every recorded entry must describe the bytes actually present.
listed = {x['path']: x for x in obj['files']}
for rel, x in listed.items():
    p = ROOT / rel
    assert p.is_file(), rel
    assert p.stat().st_size == x['size'], rel
    assert sha(p) == x['sha256'], rel

# Every active Python source/test/script must be represented.
for p in ROOT.rglob('*.py'):
    if '__pycache__' not in p.parts:
        rel = p.relative_to(ROOT).as_posix()
        assert rel in listed, rel

# ------------------------------------------------------- supersession trail --
# The defect must remain visible in the shipped manifest. A future regeneration
# that drops this record fails here rather than passing quietly.
assert obj['manifest_revision'] == 2, obj.get('manifest_revision')
history = obj['manifest_revision_history']
assert isinstance(history, list) and history, 'revision history must not be empty'

r1 = [h for h in history if h['revision'] == 1]
assert len(r1) == 1, 'revision 1 must be recorded exactly once'
r1 = r1[0]
assert r1['status'] == 'SUPERSEDED_DEFECTIVE', r1['status']
# Revision 1's own hash, so the superseded state is identifiable forever.
assert r1['manifest_sha256'] == (
    '016441a7db498a024da0f718f39886717c0130d1ed7f11e7cf43b99b1d04c483'), r1['manifest_sha256']
assert r1['recorded_by_commit'].startswith('258cd9c'), r1['recorded_by_commit']
assert r1['correction_reason']
assert r1['superseded_at_utc']
assert r1['superseded_by_commit']

# The exact entries revision 1 got wrong, with both the recorded and the real
# values, so the size of the discrepancy stays auditable without a git archive.
mis = {e['path']: e for e in r1['entries_misdescribed']}
for rel, recorded, actual in (
    ('fia_brain/config.py', 8582, 9720),
    ('fia_brain/orchestrator.py', 22080, 24219),
    ('fia_brain/sidecar.py', 3630, 3715),
):
    assert rel in mis, rel
    assert mis[rel]['recorded_size'] == recorded, rel
    assert mis[rel]['actual_size'] == actual, rel
    assert mis[rel]['recorded_sha256'] != mis[rel]['actual_sha256'], rel
    # Revision 2 must agree with reality for the same entry.
    assert listed[rel]['size'] == actual, rel
    assert listed[rel]['sha256'] == mis[rel]['actual_sha256'], rel

assert 'fia_brain/cloud_llm.py' in r1['entries_omitted'], r1['entries_omitted']
assert 'fia_brain/cloud_llm.py' in listed, 'the omitted file must now be recorded'

# This test file changed alongside the correction; that is disclosed too rather
# than folded silently into the payload.
assert 'tests/test_release_manifest_v661.py' in r1['entries_changed_by_this_correction']

# ------------------------------------------------------- hygiene (v6.6.2) ---
# The guard used to reject only '.v6_*'. Four hidden backup trees named
# '.ledger_integrity_runtime_repair_backup_*', '.real_e2e_runtime_fix_backup_*'
# and '.runtime_probability_hotfix_backup_*' therefore sealed straight into the
# release, one of them holding a pre-fix orchestrator with no ledger-integrity
# gate. Reject ANY hidden directory that is not an explicitly allowed runtime dir.
_ALLOWED_HIDDEN = set()
_hidden = [p.name for p in ROOT.iterdir()
           if p.is_dir() and p.name.startswith('.') and p.name not in _ALLOWED_HIDDEN]
assert not _hidden, 'hidden backup/state dirs must not ship in the release: %r' % (_hidden,)
_stale = [p.name for p in ROOT.iterdir()
          if p.is_dir() and ('backup' in p.name.lower() or '_bak' in p.name.lower())]
assert not _stale, 'stale backup dirs must not ship in the release: %r' % (_stale,)

print('PASS test_release_manifest_v661 (manifest r2, r1 recorded as superseded)')
