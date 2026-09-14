from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
t = (ROOT / 'fia_brain/prompts.py').read_text(encoding='utf-8')

# Commit 49646b2 strengthened the old one-line complement instruction into a
# four-step arithmetic contract. Test the current semantic contract rather than
# the superseded literal wording.
for required in (
    'PERCENTAGES from 0 to 100',
    'ARITHMETIC CONTRACT — NON-NEGOTIABLE:',
    'Set bearish_probability = 100.00 - bullish_probability EXACTLY.',
    'recompute bullish_probability + bearish_probability and verify it equals exactly 100.00',
    'use 50.00 and 50.00 rather than violating the arithmetic contract',
):
    assert required in t, required

print('PASS test_probability_prompt_contract_v6_4 (strengthened complement contract)')
