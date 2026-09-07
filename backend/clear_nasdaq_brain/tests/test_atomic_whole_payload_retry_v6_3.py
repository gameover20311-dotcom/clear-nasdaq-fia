from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
import fia_brain.evidence as e

calls=[]
def fake(url,timeout=8,max_bytes=4_000_000):
    calls.append(url)
    if url.endswith('/api/dashboard') and sum(x.endswith('/api/dashboard') for x in calls)==1:
        raise TimeoutError('synthetic busy backend')
    if url.endswith('/api/dashboard'):
        return 200,{
            'ok':True,
            'generated_at':'2026-09-03T15:00:00+00:00',
            # V7.4: the prediction projection whitelists evidence-bearing live branches,
            # so the retry probe must live inside a real one (snapshot).
            'live':{'snapshot':{'marker':'SECOND_WHOLE_PAYLOAD'}},
            'backtest':{'marker':'MUST_NOT_ENTER_PREDICTION_LEDGER','actual_8h':'BULLISH'},
        }
    return 200,{'ok':True,'provider_health':{'overall':'LIVE','score':66.7}}

old=e.http_json
e.http_json=fake
try:
    s=e.collect_atomic('http://127.0.0.1:8001','/api/dashboard',['/api/provider/health'],1)
finally:
    e.http_json=old

assert s['endpoint_health']['/api/dashboard']['ok']
assert s['endpoint_health']['/api/dashboard']['attempts']==2
assert s['payloads']['/api/dashboard']['live']['snapshot']['marker']=='SECOND_WHOLE_PAYLOAD'
assert 'backtest' not in s['payloads']['/api/dashboard']
assert s['prediction_projection']['policy']=='dashboard_live_only_v1'
assert 'backtest' in s['prediction_projection']['excluded_top_level_keys']
assert sum(x.endswith('/api/dashboard') for x in calls)==2
print('PASS test_atomic_whole_payload_retry_v6_3')
