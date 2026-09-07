from __future__ import annotations
import pathlib,sys,json
ROOT=pathlib.Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))

def check(n,c):
    if not c:raise AssertionError(n)
    print('PASS',n)
def main():
    from fia.phase35_data_foundation import PUBLIC_SYMBOLS,FRED_SERIES,_licensed_manifest
    from fia.phase35_replay_engine import feature_votes
    check('public market universe declared', all(x in PUBLIC_SYMBOLS for x in ['VIX','VXN','QQQ','SPY','SMH','SOX','NVDA','AAPL','MSFT']))
    check('rates real-yield universe declared',all(x in FRED_SERIES for x in ['US2Y','US10Y','REAL_YIELD']))
    check('licensed L2 options flow delta fail closed',all(v['status'] in {'MISSING_NOT_FAKED','AVAILABLE','ERROR'} for v in _licensed_manifest().values()))
    fake={'base':{'bullish_probability':'60'},'crossasset_riskon':.004,'mega_impact_ret_1h':.004,'semi_breadth_ret_1h':.004,'vix_ret_1h':-.02,'vxn_ret_1h':-.02,'us2y_change':-.03,'us10y_change':-.03,'real_yield_change':-.02,'news_sentiment':.4,'news_novelty':.8,'earnings_surprise':.2,'futures_basis_proxy':.001,'licensed':{}}
    v=feature_votes(fake);names={x[0] for x in v}
    check('cross asset vote present','CROSS_ASSET' in names);check('volatility votes present',{'VIX','VXN'}<=names);check('rates votes present',{'US2Y','US10Y','REAL_YIELD'}<=names);check('leadership semis present',{'MEGA_CAP','SEMIS'}<=names);check('news novelty present','NEWS_NOVELTY' in names);check('earnings surprise present','EARNINGS_SURPRISE' in names)
    policy=json.loads((ROOT/'fia_phase35/PHASE35_FROZEN_POLICY.json').read_text())
    check('policy frozen',policy['frozen_before_replay'] is True);check('holdout tuning blocked',policy['holdout_threshold_tuning'] is False);check('RL live influence zero',policy['rl_live_weight']==0.0);check('broker execution disabled',policy['broker_execution'] is False);check('90 95 claim blocked',policy['force_90_95_probability'] is False)
    print('PHASE 35 ONE-SHOT DATA + REPLAY INTEGRITY TEST PASS')
if __name__=='__main__':main()
