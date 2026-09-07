from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
t=(ROOT/'scripts/freeze_benchmark.py').read_text(); assert 'regime_profile.json' in t and 'failure_memory.jsonl' in t and 'V6 FULL REASONING + STATE' in t
print('PASS test_freeze_state_v6')
