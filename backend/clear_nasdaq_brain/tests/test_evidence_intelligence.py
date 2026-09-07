from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
from fia_brain.evidence_intelligence import build_fact_cards,cluster_correlated
ledger={"records":[
 {"evidence_id":"E1","source":"/a","path":"US10Y.yield","value":4.2},
 {"evidence_id":"E2","source":"/a","path":"US10Y.yield_copy","value":4.2},
 {"evidence_id":"E3","source":"/b","path":"NVDA.strength","value":1.3},
]}
x=build_fact_cards(ledger,10)
assert len(x["cards"])==3
assert x["cluster_count"]>=1
print("PASS test_evidence_intelligence")
