from __future__ import annotations
from typing import Any, Dict, List
from .phase33_common import raw_snapshot, fnum, clamp

def event_surprise(snapshot: Any) -> Dict[str,Any]:
    raw=raw_snapshot(snapshot)
    ev=raw.get("macro_event") or raw.get("next_macro_event") or raw.get("event") or raw.get("earnings_event")
    if not isinstance(ev,dict): return {"status":"MISSING_NOT_FAKED","event":None,"surprise_score":None}
    actual=ev.get("actual"); estimate=ev.get("estimate",ev.get("consensus")); previous=ev.get("previous")
    if actual in (None,"") or estimate in (None,""):
        return {"status":"EVENT_PRESENT_NO_VERIFIED_SURPRISE","event":ev.get("name",ev.get("event")),"actual":actual,"estimate":estimate,"previous":previous,"surprise_score":None}
    a=fnum(actual); e=fnum(estimate); scale=max(abs(e),abs(fnum(previous)),1e-6); raw_surprise=(a-e)/scale
    # Sign-to-NQ mapping must come from verified event semantics; unknown events are not guessed.
    direction_map=ev.get("nq_surprise_sign")
    score=None if direction_map in (None,"") else clamp(raw_surprise*fnum(direction_map,0.0),-1,1)
    return {"status":"AVAILABLE","event":ev.get("name",ev.get("event")),"actual":a,"estimate":e,"previous":previous,"raw_surprise":round(raw_surprise,4),"surprise_score":round(score,4) if score is not None else None,"mapping":"VERIFIED_EVENT_SIGN_REQUIRED"}
