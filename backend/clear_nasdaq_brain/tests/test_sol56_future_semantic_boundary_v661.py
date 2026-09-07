from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
from fia_brain.evidence import prediction_time_violations

def ledger(path):
    return {'records':[{'evidence_id':'E0001','source':'/api/dashboard','path':path,'value':1}]}

blocked=[
    'payload.target_close_8h',
    'payload.realized_return_4h',
    'payload.next_close_8h',
    'payload.actual_direction_4h',
    'payload.result.future_return_8h',
]
for p in blocked:
    assert prediction_time_violations(ledger(p))==[p],(p,prediction_time_violations(ledger(p)))

allowed=[
    'payload.macro.cpi.actual',
    'payload.fed.target_rate',
    'payload.market.realized_volatility',
    'payload.earnings.actual_eps',
]
for p in allowed:
    assert prediction_time_violations(ledger(p))==[],(p,prediction_time_violations(ledger(p)))
print('PASS test_sol56_future_semantic_boundary_v661')
