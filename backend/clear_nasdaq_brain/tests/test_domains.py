from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
from fia_brain.domains import partition
ledger={"records":[
{"evidence_id":"E1","source":"/api/forecast","path":"signals.US10Y","value":4.2},
{"evidence_id":"E2","source":"/api/x","path":"NVDA.relative_strength","value":1.2},
{"evidence_id":"E3","source":"/api/liquidity","path":"asia.sweep","value":True},
{"evidence_id":"E4","source":"/api/provider","path":"provider.freshness","value":"fresh"},
]}
p=partition(ledger)
assert any(r["evidence_id"]=="E1" for r in p["macro_rates"])
assert any(r["evidence_id"]=="E2" for r in p["tech_leadership"])
assert any(r["evidence_id"]=="E3" for r in p["market_liquidity"])
assert any(r["evidence_id"]=="E4" for r in p["catalyst_freshness"])
print("PASS test_domains")
