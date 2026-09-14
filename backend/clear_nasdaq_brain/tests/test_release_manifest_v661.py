# CLEAR NASDAQ BRAIN — release manifest integrity (v661, revision 3)
#
# Revision 1 was historically defective and remains recorded below.
# Revision 2 repaired that defect, but later authorized hosted-GPT-OSS runtime
# recovery commits changed fia_brain/cloud_llm.py without refreshing the release
# integrity record. Revision 3 advances ONLY the engineering release metadata to
# the bytes that are actually shipped. It does not rewrite model semantics,
# Forward-OOS, protected scientific artifacts, historical evidence, or outcomes.
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
# Both earlier defects/stale records must remain visible. A regeneration that
# drops history fails rather than silently presenting an old manifest as valid.
assert obj['manifest_revision'] == 3, obj.get('manifest_revision')
history = obj['manifest_revision_history']
assert isinstance(history, list) and history, 'revision history must not be empty'

# Revision 1: original Groq-adapter omission/misdescription.
r1s = [h for h in history if h['revision'] == 1]
assert len(r1s) == 1, 'revision 1 must be recorded exactly once'
r1 = r1s[0]
assert r1['status'] == 'SUPERSEDED_DEFECTIVE', r1['status']
assert r1['manifest_sha256'] == (
    '016441a7db498a024da0f718f39886717c0130d1ed7f11e7cf43b99b1d04c483'), r1['manifest_sha256']
assert r1['recorded_by_commit'].startswith('258cd9c'), r1['recorded_by_commit']
assert r1['correction_reason']
assert r1['superseded_at_utc']
assert r1['superseded_by_commit']

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
    assert listed[rel]['size'] == actual, rel
    assert listed[rel]['sha256'] == mis[rel]['actual_sha256'], rel

assert 'fia_brain/cloud_llm.py' in r1['entries_omitted'], r1['entries_omitted']
assert 'tests/test_release_manifest_v661.py' in r1['entries_changed_by_this_correction']

# Revision 2: once-correct bookkeeping became stale after three explicitly
# identified hosted-runtime recovery commits. This is metadata provenance, not a
# claim that those commits were scientifically validated by the manifest.
r2s = [h for h in history if h['revision'] == 2]
assert len(r2s) == 1, 'revision 2 must be recorded exactly once'
r2 = r2s[0]
assert r2['status'] == 'SUPERSEDED_STALE_BOOKKEEPING', r2['status']
assert r2['manifest_sha256'] == (
    '564b43d0a116021a10f6380fb325b358fd57b50e7abb63fe7b6408dc1842a093'), r2['manifest_sha256']
assert r2['manifest_size'] == 32017, r2['manifest_size']
assert r2['stale_entry']['path'] == 'fia_brain/cloud_llm.py'
assert r2['stale_entry']['recorded_size'] == 7738
assert r2['stale_entry']['recorded_sha256'] == (
    '7fbd5b278a74a6cceff0fbefc3e7eac97ad99fd77f98d01e58e1cab71ab3c31e')
assert r2['stale_entry']['actual_size'] == 13351
assert r2['stale_entry']['actual_sha256'] == (
    'd85828ee3960b5c072e650af18f6d82f8da03e7f6207922c793a513bc7361e69')
expected_commits = {
    '369652fcfc2a0d54b4184ac0689058ae498a88ab',
    'a3684086e7192896448aaee89eaa53acad4a177b',
    'bd3c2e9fd2c5a333c2db28a003863cd53e8a6d84',
}
assert set(r2['later_runtime_recovery_commits']) == expected_commits
assert r2['correction_reason']
assert r2['superseded_at_utc']

# Revision 3 must describe the actual hosted adapter bytes now in the tree.
assert 'fia_brain/cloud_llm.py' in listed
assert listed['fia_brain/cloud_llm.py']['size'] == 13351
assert listed['fia_brain/cloud_llm.py']['sha256'] == (
    'd85828ee3960b5c072e650af18f6d82f8da03e7f6207922c793a513bc7361e69')

# ------------------------------------------------------- hygiene -----------
_ALLOWED_HIDDEN = set()
_hidden = [p.name for p in ROOT.iterdir()
           if p.is_dir() and p.name.startswith('.') and p.name not in _ALLOWED_HIDDEN]
assert not _hidden, 'hidden backup/state dirs must not ship in the release: %r' % (_hidden,)
_stale = [p.name for p in ROOT.iterdir()
          if p.is_dir() and ('backup' in p.name.lower() or '_bak' in p.name.lower())]
assert not _stale, 'stale backup dirs must not ship in the release: %r' % (_stale,)

print('PASS test_release_manifest_v661 (manifest r3; r1+r2 provenance retained)')
