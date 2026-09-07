from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
o=(ROOT/'fia_brain/orchestrator.py').read_text(encoding='utf-8')
f=(ROOT/'fia_brain/final_three_brain.py').read_text(encoding='utf-8')
assert 'from .final_three_brain import run as run_final_three_brain' in o
assert 'run_final_three_brain(' in o
assert 'CLEAR NASDAQ FIA BRAIN V7.4 FINAL THREE-BRAIN' in o
# Independent role calls must precede freeze, and hardened advisory specialists must follow it.
i_roles=f.index('for horizon in HORIZONS:')
i_freeze=f.index('three_freeze=freeze_three_brain')
i_specialists=f.index('specialists={}')
assert i_roles < i_freeze < i_specialists
assert 'advisory=None' in f[:i_freeze]
assert 'same_model_agreement_is_independent_evidence' in f
assert 'final_by_horizon' in f and '"4h","8h"' in f
print('PASS test_three_brain_orchestrator_wiring_v74')
