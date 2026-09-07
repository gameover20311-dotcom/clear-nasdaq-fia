from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
t=(ROOT/'fia_brain/prompts.py').read_text(encoding='utf-8')
assert 'PERCENTAGES from 0 to 100' in t
assert 'MUST equal exactly 100.00' in t
print("PASS test_probability_prompt_contract_v6_4")
