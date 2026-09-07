from __future__ import annotations
import importlib.util
from typing import Any, Dict

def rl_research_status()->Dict[str,Any]:
    sb3=importlib.util.find_spec('stable_baselines3') is not None
    torch=importlib.util.find_spec('torch') is not None
    return {'status':'OFFLINE_RESEARCH_ONLY','ppo_adapter':'AVAILABLE' if sb3 else 'OPTIONAL_DEPENDENCY_MISSING','sac_adapter':'AVAILABLE' if sb3 else 'OPTIONAL_DEPENDENCY_MISSING','torch':torch,'production_weight':0.0,'self_modify_live_weights':False,'promotion_policy':'DEV -> WALK_FORWARD -> UNTOUCHED_OOS -> ACCEPT_OR_REJECT'}
def make_env_contract()->Dict[str,Any]:
    return {'observation':'timestamped PTI state vector','actions':['BULLISH_RESEARCH','BEARISH_RESEARCH','ABSTAIN'],'reward':'future outcome research label minus false-positive/risk cost','broker_orders':False}
