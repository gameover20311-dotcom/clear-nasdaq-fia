from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
from fia_brain.regime_memory import FEATURE_NAMES,fit
assert 'domain_market_structure' in FEATURE_NAMES
assert 'domain_volatility' in FEATURE_NAMES
g=[]
for i in range(30): g.append({'vector':{k:(i%3)/10 for k in FEATURE_NAMES}})
p=fit(g);assert 'domain_market_structure' in p['features'] and 'domain_volatility' in p['features']
print('PASS test_novelty_dimensions_v661')
