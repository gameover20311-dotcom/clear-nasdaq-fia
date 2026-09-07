from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
from fia_brain.domains import record_domains
from fia_brain.evidence_genome import build

assert "market_structure" in record_domains({"source":"/api/dashboard","path":"live.snapshot.data.price_action.events.QQQ.timeframes.5m.trend","value":"inside"})
assert "market_liquidity" not in record_domains({"source":"/api/dashboard","path":"live.snapshot.data.price_action.events.QQQ.timeframes.5m.trend","value":"inside"})
assert "volatility" in record_domains({"source":"/api/dashboard","path":"live.snapshot.data.vix","value":14.8})
assert "market_liquidity" not in record_domains({"source":"/api/dashboard","path":"live.snapshot.data.vix","value":14.8})
assert "market_liquidity" in record_domains({"source":"/api/dashboard","path":"live.snapshot.data.liquidity.session_sweep","value":"NY"})

recs=[
 {"evidence_id":"E0001","source":"/api/dashboard","path":"live.snapshot.data.price_action.trend","value":"inside","record_hash":"x"},
 {"evidence_id":"E0002","source":"/api/dashboard","path":"live.snapshot.data.vix","value":14.8,"record_hash":"y"},
 {"evidence_id":"E0003","source":"/api/dashboard","path":"live.snapshot.data.liquidity.session_sweep","value":"NY","record_hash":"z"},
]
g=build({"records":recs,"ledger_sha256":"L"})
assert g["vector"]["domain_market_structure"]>0
assert g["vector"]["domain_volatility"]>0
assert g["vector"]["domain_market_liquidity"]>0
print("PASS test_genome_semantic_split_v6_3")
