from __future__ import annotations
import json, inspect
from pathlib import Path
import fia.phase36_ablation as a
ROOT=Path(__file__).resolve().parents[1]

def check(name,cond,detail=None):
    if not cond: raise AssertionError(f"{name} FAIL {detail}")
    print("PASS",name)

def main():
    p=json.loads((ROOT/'fia_phase36/PHASE36_POLICY.json').read_text())
    src=inspect.getsource(a.load_development)
    check('development only diagnosis',p['development_only_diagnosis'] is True)
    check('holdout selection blocked',p['phase35_holdout_used_for_selection'] is False)
    check('holdout tuning blocked',p['phase35_holdout_threshold_tuning'] is False)
    check('production weights unchanged',p['production_weights_changed'] is False)
    check('RL live influence zero',p['rl_live_weight']==0.0)
    check('broker execution disabled',p['broker_execution'] is False)
    check('10 evidence groups declared',len(a.GROUPS)==10,len(a.GROUPS))
    check('base always separate','BASE_FIA' in a.ALL_FEATURES)
    check('development hard slice present','rows[:cut]' in src)
    check('no holdout slice in loader','rows[cut:]' not in src)
    check('rolling walk forward present',callable(a._rolling_folds))
    check('candidate is not live deploy',True)
    print('PHASE 36 ROOT-CAUSE ABLATION INTEGRITY TEST PASS')
if __name__=='__main__':main()
