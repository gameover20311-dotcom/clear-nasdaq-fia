from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
from fia_brain.domains import record_domains
assert 'market_liquidity' not in record_domains({'source':'/api/dashboard','path':'live.snapshot.data.price','value':716.25})
assert 'market_liquidity' in record_domains({'source':'/api/dashboard','path':'live.snapshot.data.liquidity.session_sweep','value':'NY'})
assert 'macro_rates' in record_domains({'source':'/api/dashboard','path':'live.snapshot.data.us10y','value':4.75})
assert 'tech_leadership' in record_domains({'source':'/api/dashboard','path':'live.snapshot.data.mega_cap.NVDA.signal','value':0.5})
print('PASS test_domain_precision_v6_2')
