from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
t=(ROOT/'scripts/run_dev_ablation.py').read_text(encoding='utf-8'); assert "Ablation is DEV-only" in t and "a.split.upper()!='DEV'" in t
print('PASS test_ablation_guard_v6')
