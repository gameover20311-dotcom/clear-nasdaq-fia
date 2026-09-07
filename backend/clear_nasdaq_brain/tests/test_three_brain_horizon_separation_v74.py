from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
from fia_brain import prompts
for role in ('BULL','BEAR','DISCONFIRMING_CRITIC'):
    p4=prompts.THREE_BRAIN_INSTRUCTION(role,4)
    p8=prompts.THREE_BRAIN_INSTRUCTION(role,8)
    assert 'HORIZON=4H' in p4 and 'HORIZON=8H' in p8 and p4!=p8
    assert 'Same-model agreement is never independent market evidence' in p4
c4=prompts.CHIEF_THREE_BRAIN(4); c8=prompts.CHIEF_THREE_BRAIN(8)
assert 'ONLY the frozen 4H' in c4 and "do not borrow the other horizon's probability" in c4
assert 'ONLY the frozen 8H' in c8 and "do not borrow the other horizon's probability" in c8
assert 'agreement is NOT independent evidence' in c4 and 'agreement is NOT independent evidence' in c8
print('PASS test_three_brain_horizon_separation_v74')
