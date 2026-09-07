from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
t=(ROOT/"scripts/freeze_benchmark.py").read_text(encoding="utf-8")
for s in ('ROOT/"fia_brain"','ROOT/"scripts"','ROOT/"config.json"','calibration_profile.json'):
    assert s in t
print("PASS test_freeze_scope_v5")
