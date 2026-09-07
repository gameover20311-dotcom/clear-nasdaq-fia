from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
from fia_brain.domains import record_domains
assert 'tech_leadership' not in record_domains({'source':'x','path':'metadata.state','value':'ok'})
assert 'tech_leadership' not in record_domains({'source':'x','path':'cumulative_volume.value','value':1})
assert 'macro_rates' not in record_domains({'source':'x','path':'transmission_mechanism.value','value':'x'})
assert 'tech_leadership' in record_domains({'source':'x','path':'stocks.META.change_pct','value':1})
assert 'macro_rates' in record_domains({'source':'x','path':'macro.ISM.actual','value':50})
print('PASS test_adversarial_domain_tokens_v661')
