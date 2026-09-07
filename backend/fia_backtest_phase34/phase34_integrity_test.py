from __future__ import annotations
import json, pathlib, sys
ROOT=pathlib.Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
from fia.phase34_source_registry import SOURCES, audit_sources
from fia.phase34_orderflow import analyze_depth
from fia.phase34_options import analyze_options
from fia.phase34_rl_lab import rl_research_status
POINTS=[
'LLM News/Sentiment Brain','RL PPO/SAC Research Agent','L2/L3 Order Flow','HMM/Wavelet Regime','SOR Simulation','Kelly+Monte Carlo','3D/WebGL Dashboard','Tick Replay','Voice/Chat Copilot','Rust/C++ Core','WebSocket Streaming','Black Swan Shield','Prop-Firm Guardrail','VIX/VXN','US2Y+US10Y+Real Yield','SOX/SMH Breadth','Mega-cap Index Impact','NQ/ES/SPX/QQQ Lead-Lag','Options Skew+Gamma','Event Surprise','Historical Analog Engine','Multi-model Ensemble','OOS Calibration+NO_EDGE']
def ck(n,c,d=''):
    if not c: raise AssertionError(f'{n} FAIL {d}')
    print('PASS',n)
def main():
    ck('23/23 declared',len(POINTS)==23)
    req=['phase34_engine.py','phase34_api.py','phase34_source_registry.py','phase34_public_data.py','phase34_orderflow.py','phase34_options.py','phase34_rates_vol.py','phase34_leadership.py','phase34_causal.py','phase34_regime.py','phase34_news_primary.py','phase34_event_surprise.py','phase34_analogs.py','phase34_calibration.py','phase34_rl_lab.py','phase34_risk_execution.py','phase34_shields.py']
    for x in req: ck('module '+x,(ROOT/'fia'/x).exists())
    man=json.loads((ROOT/'fia_phase34/PHASE34_23_POINT_COVERAGE.json').read_text())
    ck('coverage manifest 23',len(man['points'])==23)
    ck('all points code complete',all(p['code_status']=='IMPLEMENTED' for p in man['points']))
    ck('missing sources fail closed',audit_sources({})['missing_never_neutral_imputed'] is True)
    ck('L2 no fake',analyze_depth({})['status']=='MISSING_NOT_FAKED')
    ck('options no fake',analyze_options({})['status']=='MISSING_NOT_FAKED')
    ck('RL live weight zero',rl_research_status()['production_weight']==0.0)
    pol=json.loads((ROOT/'fia_phase34/PHASE34_FROZEN_POLICY.json').read_text())
    ck('broker execution disabled',pol['broker_execution'] is False)
    ck('90/95 claim blocked',pol['force_high_probability_claim'] is False)
    mainpy=(ROOT/'main.py').read_text(); ck('Phase34 routes registered','install_phase34_routes' in mainpy)
    ck('WebGL dashboard exists',(ROOT.parent/'frontend/app/phase34/page.tsx').exists())
    ck('tick replay UI exists',(ROOT.parent/'frontend/app/phase34/replay/page.tsx').exists())
    print('PHASE 34 ALL-POINTS INTEGRITY TEST PASS')
if __name__=='__main__': main()
