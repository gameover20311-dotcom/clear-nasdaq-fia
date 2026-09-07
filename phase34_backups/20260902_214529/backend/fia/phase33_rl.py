from __future__ import annotations
from typing import Any, Dict


def rl_live_gate() -> Dict[str,Any]:
    available=False; detail="stable_baselines3_not_required_for_live_runtime"
    try:
        import stable_baselines3  # noqa
        available=True; detail="PPO/SAC research library available"
    except Exception: pass
    return {"research_lab":"PPO_SAC_OFFLINE_ONLY","library_available":available,"production_weight":0.0,"self_modify_daily":False,"oos_approval_required":True,"broker_execution":False,"detail":detail}
