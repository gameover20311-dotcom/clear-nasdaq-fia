from __future__ import annotations
import json, pathlib, sys, math
ROOT=pathlib.Path(__file__).resolve().parents[1]; OUT=ROOT/'fia_backtest_phase34/results/phase34_full_replay_summary.json'
def main():
    p33=ROOT/'fia_backtest_phase33/results/phase33_full_replay_1y_summary.json'
    enrichment=ROOT/'fia_phase34/data/enriched_pti.jsonl'
    old=json.loads(p33.read_text()) if p33.exists() else {}
    enriched_rows=0
    if enrichment.exists(): enriched_rows=sum(1 for x in enrichment.read_text().splitlines() if x.strip())
    result={'ok':True,'phase':'PHASE 34 ALL-POINTS REPLAY','frozen_policy':True,'phase33_reference':old,'historical_enriched_rows':enriched_rows,'full_23_point_historical_replay_ready':enriched_rows>=100,'status':'READY_FOR_FULL_ENRICHED_REPLAY' if enriched_rows>=100 else 'BLOCKED_BY_MISSING_HISTORICAL_INSTITUTIONAL_INPUTS','no_fake_imputation':True,'note':'Code coverage is 23/23. A genuine full 23-point OOS replay requires timestamped PTI history for the data-dependent feeds; absent feeds are not replaced by zero/neutral. Existing Phase33 result remains the valid reference until that dataset exists.','broker_execution':False}
    OUT.parent.mkdir(parents=True,exist_ok=True); OUT.write_text(json.dumps(result,indent=2)); print(json.dumps(result,indent=2))
if __name__=='__main__': main()
