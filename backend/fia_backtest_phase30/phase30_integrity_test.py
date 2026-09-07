#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))

from fia.cognitive.calibration import fit_platt, apply_calibration
from fia.cognitive.critic import run_critic
from fia.cognitive.hypotheses import build_hypotheses
from fia.cognitive.models import SpecialistView, RegimeView
from fia.cognitive.provenance import build_evidence_ledger
from fia.cognitive.specialists import build_specialists

SUMMARY=ROOT/'fia_backtest_phase30/results/phase30_cognitive_replay_1y_summary.json'


def check(name, condition):
    if not condition: raise AssertionError(name)
    print('PASS',name)


def main():
    forecast={
        'direction':'BULLISH','bullish_probability':62,'bearish_probability':38,'confidence':66,'regime':'TREND','score':.2,
        'generated_at':'2026-01-15T17:00:00+00:00','data_coverage':.8,'intelligence_coverage':.7,'source_status':{},
        'signals':[
            {'name':'NQ structure','score':.4,'weight':.2,'detail':'synthetic','freshness':'live'},
            {'name':'SPX confirmation','score':.2,'weight':.1,'detail':'synthetic','freshness':'live'},
            {'name':'DXY','score':.4,'weight':.08,'detail':'synthetic','freshness':'live'},
            {'name':'US10Y','score':.3,'weight':.07,'detail':'synthetic','freshness':'live'},
            {'name':'Mega-cap leadership','score':.3,'weight':.2,'detail':'synthetic','freshness':'live'},
            {'name':'Semiconductors','score':.2,'weight':.12,'detail':'synthetic','freshness':'live'},
            {'name':'Breadth','score':.1,'weight':.08,'detail':'synthetic','freshness':'live'},
            {'name':'News','score':-.2,'weight':.07,'detail':'synthetic','freshness':'live'},
            {'name':'Macro calendar','score':0,'weight':.04,'detail':'Awaiting provider data','freshness':'missing'},
            {'name':'Earnings/guidance','score':0,'weight':.04,'detail':'Awaiting provider data','freshness':'missing'},
        ]
    }
    snapshot={'data':{'macro_status':'missing','dxy_source':'Yahoo Finance DX-Y.NYB','us10y_source':'Yahoo Finance ^TNX'},'provider':'synthetic','timestamp':'2026-01-15T17:00:00+00:00'}
    ledger=build_evidence_ledger(snapshot,forecast,[])
    specs=build_specialists(snapshot,forecast,ledger,{}, {})
    by={x.name:x for x in specs}
    check('15 specialist brains present',len(specs)==15)
    check('missing macro remains MISSING',by['Macro Surprise AI'].direction=='MISSING' and by['Macro Surprise AI'].reliability==0)
    check('DXY translated to inverse NQ impact',by['Genuine Dollar/DXY AI'].score<0)
    check('US10Y translated to inverse NQ impact',by['Rates & Yield AI'].score<0)
    regime=RegimeView(primary='CONFLICTED',secondary=[],confidence=.7,reasons=[],risk_state='CONFLICT')
    hypotheses=build_hypotheses(specs,regime)
    check('bullish and bearish hypotheses generated',bool(hypotheses['bullish_hypothesis']) and bool(hypotheses['bearish_hypothesis']))
    critic=run_critic(specs,regime,hypotheses,72,.8,.65,{})
    check('independent critic challenges conflicted decisiveness',critic.score>0 and len(critic.objections)>0)
    model=fit_platt([35,40,45,55,60,65]*8,[0,0,0,1,1,1]*8)
    check('calibration model fits development sample',model.get('available') is True)
    check('calibration output bounded',0<=apply_calibration(70,model)<=100)
    check('evidence ledger traceable',ledger.get('record_count')==len(forecast['signals']) and bool(ledger.get('ledger_digest')))

    check('Phase30 validation summary exists',SUMMARY.exists())
    summary=json.loads(SUMMARY.read_text())
    check('holdout excluded from calibration fitting',summary['calibration_models']['dataset_split']['holdout_used_for_fitting'] is False)
    check('known future leakage gate enabled',summary['integrity']['no_known_future_leakage'] is True)
    check('market-grade claim fail-closes when evidence is insufficient',summary['acceptance']['status'] in {'PASS','WITHHELD'})
    check('broker execution disabled',summary.get('broker_execution') is False)
    print('PHASE 30 COGNITIVE INTEGRITY TEST PASS')

if __name__=='__main__': main()
