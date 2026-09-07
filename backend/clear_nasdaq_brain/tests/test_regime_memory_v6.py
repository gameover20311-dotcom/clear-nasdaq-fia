from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from fia_brain.regime_memory import fit,score
g=[{'vector':{'domain_macro_rates':.2,'domain_tech_leadership':.2,'domain_market_liquidity':.2,'domain_catalyst_freshness':.2,'domain_general':.2,'fresh_fresh':.3,'fresh_aging':0,'fresh_stale':0,'fresh_unknown':.7,'numeric_ratio':.3,'nullish_ratio':0,'independence_ratio':.8}} for _ in range(30)]
p=fit(g); q=score({'vector':{**g[0]['vector'],'domain_macro_rates':1.0,'independence_ratio':0.0}},p); assert q['enabled'] and q['confidence_cap']<=70
print('PASS test_regime_memory_v6')
