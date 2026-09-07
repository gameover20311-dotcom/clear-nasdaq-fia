from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from fia_brain.evidence import build_ledger,prediction_time_violations

snap={
    'snapshot_sha256':'S',
    'payloads':{
        '/api/dashboard':{
            'ok':True,
            'generated_at':'2026-09-04T06:00:00Z',
            'live':{
                'snapshot':{'data':{'macro':{'cpi':{'actual':2.9}},'fed':{'target_rate':5.25},'realized_volatility':0.21}},
                'forecast':{'direction':'BULLISH','bullish_probability':99.0},
                'cognitive':{'direction':'BEARISH','historical_analogy':{'correct':99}},
                'liquidity':{'asia_high':100.0},
                'liquidity_groups':{'NQ':{'current_price':99.0}},
                'upcoming_earnings':{'available':True,'events':[]},
            },
            'backtest':{'earnings_comparison':{'earnings_catalyst_days':{'4h':{'correct':20,'resolved':30}}}},
        }
    }
}
ledger=build_ledger(snap,max_records=500,max_chars=200000)
paths=[r['path'] for r in ledger['records']]
assert not any(p.startswith('backtest') for p in paths),paths
assert not any(p.startswith('live.forecast') for p in paths),paths
assert not any(p.startswith('live.cognitive') for p in paths),paths
assert any(p=='live.snapshot.data.macro.cpi.actual' for p in paths),paths
assert any(p=='live.snapshot.data.fed.target_rate' for p in paths),paths
assert any(p=='live.snapshot.data.realized_volatility' for p in paths),paths
assert any(p.startswith('live.liquidity') for p in paths),paths
assert prediction_time_violations(ledger)==[],prediction_time_violations(ledger)

# The projection must NOT hide a forbidden future field if it appears in an allowed\n# live/raw branch.  The semantic boundary still has to fail closed.
snap['payloads']['/api/dashboard']['live']['snapshot']['data']['target_close_8h']=123.0
ledger2=build_ledger(snap,max_records=500,max_chars=200000)
viol=prediction_time_violations(ledger2)
assert any('target_close_8h' in p for p in viol),viol
print('PASS test_prediction_time_dashboard_projection_v661')
