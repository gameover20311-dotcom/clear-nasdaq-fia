from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
from fia_brain.evidence import prediction_time_violations
from fia_brain import __version__
for path in ['phase35.nq_4h','x.move_8h_pct','results.actual_4h','future_price','x.mfe_pct']:
 assert prediction_time_violations({'records':[{'path':path}]})==[path],path
assert prediction_time_violations({'records':[{'path':'live.forecast.horizon_hours'}]})==[]
assert __version__=='6.6.1'
print('PASS test_future_boundary_and_version_v661')
