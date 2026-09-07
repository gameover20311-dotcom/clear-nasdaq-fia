from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
t=(ROOT/'fia_brain/orchestrator.py').read_text(encoding='utf-8')
assert 'direct_liquidity_provider_available' in t
assert 'DIRECT_PROVIDER_MISSING__DERIVED_DASHBOARD_EVIDENCE_ONLY' in t
print("PASS test_evidence_availability_v6_4")
