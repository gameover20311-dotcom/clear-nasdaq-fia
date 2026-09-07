from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
from fia_brain.domains import record_domains
assert record_domains({'source':'x','path':'metadata.info','value':'foo'})=={'general'}
assert 'tech_leadership' not in record_domains({'source':'x','path':'cumulative_volume','value':1})
assert 'macro_rates' not in record_domains({'source':'x','path':'transmission_mechanism','value':'foo'})
assert 'tech_leadership' in record_domains({'source':'x','path':'stocks.meta.change_pct','value':1})
print('PASS SOL56 domain semantic boundaries')
