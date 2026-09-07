from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
o=(ROOT/'fia_brain/orchestrator.py').read_text(encoding='utf-8'); s=(ROOT/'fia_brain/sidecar.py').read_text(encoding='utf-8')
assert 'V7.4 FINAL THREE-BRAIN' in o and 'V7.4 FINAL THREE-BRAIN SIDECAR' in s
print('PASS test_version_labels_v74')
