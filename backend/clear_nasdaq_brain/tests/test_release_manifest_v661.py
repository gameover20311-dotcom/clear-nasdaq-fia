# CLEAR NASDAQ BRAIN — release manifest integrity (v661, revision 3)
#
# r1 was historically defective. r2 repaired r1, but the current baseline later
# diverged from r2 in three runtime files; the release-manifest test entry itself
# is also misdescribed at the current baseline. r3 advances only integrity
# bookkeeping to the exact shipped bytes and preserves both earlier revisions.
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


listed = {x['path']: x for x in obj['files']}
for rel, x in listed.items():
    p = ROOT / rel
    assert p.is_file(), rel
    assert p.stat().st_size == x['size'], rel
    assert sha(p) == x['sha256'], rel

for p in ROOT.rglob('*.py'):
    if '__pycache__' not in p.parts:
        rel = p.relative_to(ROOT).as_posix()
        assert rel in listed, rel

assert obj['manifest_revision'] == 3, obj.get('manifest_revision')
history = obj['manifest_revision_history']
assert isinstance(history, list) and history

r1s = [h for h in history if h['revision'] == 1]
assert len(r1s) == 1
r1 = r1s[0]
assert r1['status'] == 'SUPERSEDED_DEFECTIVE'
assert r1['manifest_sha256'] == '016441a7db498a024da0f718f39886717c0130d1ed7f11e7cf43b99b1d04c483'
assert r1['recorded_by_commit'].startswith('258cd9c')
assert r1['correction_reason']
assert r1['superseded_at_utc']
assert r1['superseded_by_commit']
mis = {e['path']: e for e in r1['entries_misdescribed']}
for rel, recorded, actual in (
    ('fia_brain/config.py', 8582, 9720),
    ('fia_brain/orchestrator.py', 22080, 24219),
    ('fia_brain/sidecar.py', 3630, 3715),
):
    assert rel in mis
    assert mis[rel]['recorded_size'] == recorded
    assert mis[rel]['actual_size'] == actual
    assert mis[rel]['recorded_sha256'] != mis[rel]['actual_sha256']
    assert listed[rel]['size'] == actual
    assert listed[rel]['sha256'] == mis[rel]['actual_sha256']
assert 'fia_brain/cloud_llm.py' in r1['entries_omitted']

r2s = [h for h in history if h['revision'] == 2]
assert len(r2s) == 1
r2 = r2s[0]
assert r2['status'] == 'SUPERSEDED_STALE_BOOKKEEPING'
assert r2['manifest_sha256'] == '564b43d0a116021a10f6380fb325b358fd57b50e7abb63fe7b6408dc1842a093'
assert r2['manifest_size'] == 32017
r2mis = {e['path']: e for e in r2['entries_misdescribed_at_baseline']}
expected = {
    'fia_brain/cloud_llm.py': (
        7738, '7fbd5b278a74a6cceff0fbefc3e7eac97ad99fd77f98d01e58e1cab71ab3c31e',
        13351, 'd85828ee3960b5c072e650af18f6d82f8da03e7f6207922c793a513bc7361e69'),
    'fia_brain/final_three_brain.py': (
        15606, '2cf9797876298ac1ac81ea320449a3fdb2c0add072c656d7d8ad791fd4efbf60',
        16052, 'a47ed83b209ceb495d0f3e483fe875e23e9a6e66c2cd1c9cc322428771f65e7f'),
    'fia_brain/prompts.py': (
        7106, '43e03f3a630b6f04033494a857f23e0c3e87204e2bcd89f1444b87f7fd70e3ea',
        7501, '723f0e68052b1af97e80523a3fd62b597fb4a3e77bf593712883045d4f157c2a'),
    'tests/test_release_manifest_v661.py': (
        5411, '09a4e47d7bfee6e5e239254fbd6c709697aacf9ef97f0f2eaa08bee61bf427a5',
        4574, '207c8fa63882a008381c8e375572498be96311237618153930a995177dca0dbe'),
}
assert set(r2mis) == set(expected)
for rel, values in expected.items():
    rec = r2mis[rel]
    assert (rec['recorded_size'], rec['recorded_sha256'],
            rec['baseline_actual_size'], rec['baseline_actual_sha256']) == values

assert set(r2['known_runtime_commits_after_r2']) == {
    '369652fcfc2a0d54b4184ac0689058ae498a88ab',
    'a3684086e7192896448aaee89eaa53acad4a177b',
    'bd3c2e9fd2c5a333c2db28a003863cd53e8a6d84',
    'f1e75651db6056eb4a87c990f368e852c6168b7a',
    '49646b2ea5f6e005d54a3c76cad0eedeab565b69',
}
assert r2['correction_reason']
assert r2['superseded_at_utc']

for rel, size, digest in (
    ('fia_brain/cloud_llm.py', 13351, 'd85828ee3960b5c072e650af18f6d82f8da03e7f6207922c793a513bc7361e69'),
    ('fia_brain/final_three_brain.py', 16052, 'a47ed83b209ceb495d0f3e483fe875e23e9a6e66c2cd1c9cc322428771f65e7f'),
    ('fia_brain/prompts.py', 7501, '723f0e68052b1af97e80523a3fd62b597fb4a3e77bf593712883045d4f157c2a'),
):
    assert listed[rel]['size'] == size
    assert listed[rel]['sha256'] == digest

_ALLOWED_HIDDEN = set()
_hidden = [p.name for p in ROOT.iterdir()
           if p.is_dir() and p.name.startswith('.') and p.name not in _ALLOWED_HIDDEN]
assert not _hidden, 'hidden backup/state dirs must not ship in the release: %r' % (_hidden,)
_stale = [p.name for p in ROOT.iterdir()
          if p.is_dir() and ('backup' in p.name.lower() or '_bak' in p.name.lower())]
assert not _stale, 'stale backup dirs must not ship in the release: %r' % (_stale,)

print('PASS test_release_manifest_v661 (manifest r3; r1+r2 provenance retained)')
