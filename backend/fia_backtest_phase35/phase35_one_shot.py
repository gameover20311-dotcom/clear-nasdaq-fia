from __future__ import annotations
import pathlib,sys,json,traceback
ROOT=pathlib.Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from fia.phase35_data_foundation import backfill
from fia.phase35_enrichment import enrich
from fia.phase35_replay_engine import replay

def main():
    print('='*72);print('PHASE 35 · ONE SHOT: DATA BACKFILL → PTI ENRICHMENT → FROZEN REPLAY');print('='*72)
    print('\n[1/3] Genuine data backfill...');a=backfill(force=False);print(json.dumps(a,indent=2))
    print('\n[2/3] Point-in-time enrichment...');b=enrich();print(json.dumps(b,indent=2))
    print('\n[3/3] Frozen development/untouched-holdout replay...');c=replay();print(json.dumps(c,indent=2))
    print('\n'+'='*72);print('PHASE 35 ONE-SHOT COMPLETE');print('='*72)
if __name__=='__main__':main()
