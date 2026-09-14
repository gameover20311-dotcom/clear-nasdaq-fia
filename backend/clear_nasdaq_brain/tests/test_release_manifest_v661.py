# CLEAR NASDAQ BRAIN — release manifest integrity (v661, revision 4)
#
# r1 was defective; r2 repaired it but later became stale after named hosted
# GPT-OSS recovery commits; r3 repaired that bookkeeping. The full baseline
# suite then exposed one previously masked stale TEST expectation: commit
# 49646b2 intentionally strengthened the probability complement prompt from an
# old literal sentence into a four-step arithmetic contract, while the test
# still searched for the removed wording. r4 updates TEST/manifest bookkeeping
# only. Runtime prompt/model logic is not changed by this repair.
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

# Every active Python source/test/script in the release tree must be represented.
for p in ROOT.rglob('*.py'):
    if '__pycache__' not in p.parts:
        rel = p.relative_to(ROOT).as_posix()
        assert rel in listed, rel

assert obj['manifest_revision'] == 4, obj.get('manifest_revision')
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
assert 'fia_brain/cloud_llm.py' in r1['entries_omitted']

r2s = [h for h in history if h['revision'] == 2]
assert len(r2s) == 1
r2 = r2s[0]
assert r2['status'] == 'SUPERSEDED_STALE_BOOKKEEPING'
assert r2['manifest_sha256'] == '564b43d0a116021a10f6380fb325b358fd57b50e7abb63fe7b6408dc1842a093'
assert r2['manifest_size'] == 32017
r2mis = {e['path']: e for e in r2['entries_misdescribed_at_baseline']}
assert set(r2mis) == {
    'fia_brain/cloud_llm.py',
    'fia_brain/final_three_brain.py',
    'fia_brain/prompts.py',
    'tests/test_release_manifest_v661.py',
}
assert set(r2['known_runtime_commits_after_r2']) == {
    '369652fcfc2a0d54b4184ac0689058ae498a88ab',
    'a3684086e7192896448aaee89eaa53acad4a177b',
    'bd3c2e9fd2c5a333c2db28a003863cd53e8a6d84',
    'f1e75651db6056eb4a87c990f368e852c6168b7a',
    '49646b2ea5f6e005d54a3c76cad0eedeab565b69',
}
assert r2['correction_reason']
assert r2['superseded_at_utc']

r3s = [h for h in history if h['revision'] == 3]
assert len(r3s) == 1
r3 = r3s[0]
assert r3['status'] == 'SUPERSEDED_STALE_TEST_EXPECTATION'
assert r3['manifest_sha256'] == 'cedfa8da6e33c474107d65f74ac8bd079ede6d522502fafbe49006feb6703cd9'
assert r3['manifest_size'] == 34514
assert r3['correction_reason']
assert r3['superseded_at_utc']
changed = {e['path']: e for e in r3['entries_changed_for_revision4']}
assert set(changed) == {
    'tests/test_probability_prompt_contract_v6_4.py',
    'tests/test_release_manifest_v661.py',
}
for rel, rec in changed.items():
    assert rec['recorded_size'] != rec['actual_size'] or rec['recorded_sha256'] != rec['actual_sha256']
    assert listed[rel]['size'] == rec['actual_size']
    assert listed[rel]['sha256'] == rec['actual_sha256']

# The strengthened runtime prompt itself must remain exactly the pre-repair byte
# identity. This prevents a stale-test repair from silently changing model logic.
prompt = listed['fia_brain/prompts.py']
assert prompt['size'] == 7501
assert prompt['sha256'] == '723f0e68052b1af97e80523a3fd62b597fb4a3e77bf593712883045d4f157c2a'

_ALLOWED_HIDDEN = set()
_hidden = [p.name for p in ROOT.iterdir()
           if p.is_dir() and p.name.startswith('.') and p.name not in _ALLOWED_HIDDEN]
assert not _hidden, 'hidden backup/state dirs must not ship in the release: %r' % (_hidden,)
_stale = [p.name for p in ROOT.iterdir()
          if p.is_dir() and ('backup' in p.name.lower() or '_bak' in p.name.lower())]
assert not _stale, 'stale backup dirs must not ship in the release: %r' % (_stale,)

print('PASS test_release_manifest_v661 (manifest r4; r1+r2+r3 provenance retained)')
