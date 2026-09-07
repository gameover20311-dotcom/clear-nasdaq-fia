from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
from fia_brain.evidence import project_prediction_time_payload,build_ledger,prediction_time_violations

raw={
    'ok':True,
    'generated_at':'2026-09-05T00:00:00+00:00',
    'live':{
        'snapshot':{'data':{'nq_structure':'BULLISH','dxy':97.5}},
        'forecast':{'direction':'BULLISH','bullish_probability':61.0},
    },
    'backtest':{
        'earnings_comparison':{
            'earnings_catalyst_days':{'4h':{'correct':12,'resolved':20},'8h':{'correct':11,'resolved':20}}
        }
    }
}
projected,meta=project_prediction_time_payload('/api/dashboard',raw)
assert set(projected)=={'ok','generated_at','live'},projected
assert 'backtest' not in projected
assert meta['policy']=='dashboard_live_only_v1'
assert 'backtest' in meta['excluded_top_level_keys']
snap={'snapshot_sha256':'x','payloads':{'/api/dashboard':projected}}
ledger=build_ledger(snap,max_records=200,max_chars=64000)
assert not any(r['path'].startswith('backtest') for r in ledger['records'])
assert prediction_time_violations(ledger)==[],prediction_time_violations(ledger)

# The projection must NOT suppress leakage inside the live branch.
raw2={'ok':True,'generated_at':'x','live':{'snapshot':{'target_close_8h':12345}} ,'backtest':{}}
projected2,_=project_prediction_time_payload('/api/dashboard',raw2)
ledger2=build_ledger({'snapshot_sha256':'y','payloads':{'/api/dashboard':projected2}},max_records=50,max_chars=64000)
viol=prediction_time_violations(ledger2)
assert any('target_close_8h' in x for x in viol),viol

# Non-dashboard atomic endpoints retain identity behavior.
obj={'x':1}
p3,m3=project_prediction_time_payload('/api/custom',obj)
assert p3 is obj and m3['policy']=='identity'
print('PASS test_prediction_dashboard_projection_v661')
