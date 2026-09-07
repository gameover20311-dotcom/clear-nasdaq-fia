from __future__ import annotations
from copy import deepcopy
from typing import Any, Dict, Mapping
from .util import sha256_obj

ROLES=("BULL","BEAR","DISCONFIRMING_CRITIC")
HORIZONS=(4,8)
_REQUIRED={"direction","bullish_probability","bearish_probability","confidence","thesis","evidence_ids","counter_evidence_ids","unknowns","failure_conditions"}


def _validate_analysis(obj: Mapping[str,Any]) -> Dict[str,Any]:
    if not isinstance(obj,Mapping):
        raise ValueError("three-brain cell must be an analysis object")
    if not _REQUIRED.issubset(set(obj)):
        raise ValueError("three-brain cell missing required analysis fields")
    out=deepcopy(dict(obj))
    p=float(out["bullish_probability"]); q=float(out["bearish_probability"]); c=float(out["confidence"])
    if not (0.0 <= p <= 100.0 and 0.0 <= q <= 100.0 and 0.0 <= c <= 100.0):
        raise ValueError("three-brain probability/confidence outside [0,100]")
    if abs((p+q)-100.0) > 0.05:
        raise ValueError("three-brain probabilities must sum to 100")
    return out


def freeze(outputs: Mapping[str,Any], ledger_sha256: str, model: str) -> Dict[str,Any]:
    cells: Dict[str,Any]={}
    for horizon in HORIZONS:
        hk=f"{horizon}h"; src=outputs.get(hk) if isinstance(outputs,Mapping) else None
        if not isinstance(src,Mapping):
            raise ValueError(f"missing three-brain horizon {hk}")
        cells[hk]={}
        for role in ROLES:
            analysis=_validate_analysis(src.get(role))
            cell={"role":role,"horizon_hours":horizon,"analysis":analysis}
            cell["cell_sha256"]=sha256_obj(cell)
            cells[hk][role]=cell
    frozen={
        "schema":"CLEAR_NASDAQ_THREE_BRAIN_PRE_RECONCILIATION_FREEZE_V1",
        "ledger_sha256":str(ledger_sha256 or ""),
        "model":str(model or ""),
        "same_model_agreement_is_independent_evidence":False,
        "independent_evidence_basis":"prediction_time_source_clusters_only",
        "cells":cells,
    }
    frozen["freeze_sha256"]=sha256_obj(frozen)
    return frozen


def verify(frozen: Mapping[str,Any]) -> bool:
    if not isinstance(frozen,Mapping): return False
    obj=deepcopy(dict(frozen)); supplied=str(obj.pop("freeze_sha256", ""))
    if not supplied or sha256_obj(obj)!=supplied: return False
    cells=obj.get("cells")
    if not isinstance(cells,Mapping): return False
    try:
        for horizon in HORIZONS:
            hk=f"{horizon}h"
            for role in ROLES:
                cell=deepcopy(dict(cells[hk][role])); h=str(cell.pop("cell_sha256", ""))
                if not h or sha256_obj(cell)!=h: return False
                _validate_analysis(cell["analysis"])
    except Exception:
        return False
    return True


def horizon_candidates(frozen: Mapping[str,Any], horizon_hours: int):
    if not verify(frozen): raise ValueError("three-brain freeze integrity failed")
    hk=f"{int(horizon_hours)}h"
    return [deepcopy(frozen["cells"][hk][role]["analysis"]) for role in ROLES]


def model_independence_metadata(frozen: Mapping[str,Any]) -> Dict[str,Any]:
    if not verify(frozen): raise ValueError("three-brain freeze integrity failed")
    return {
        "model":frozen.get("model"),
        "pipeline_count":len(ROLES)*len(HORIZONS),
        "role_count":len(ROLES),
        "horizons_hours":list(HORIZONS),
        "same_model_agreement_is_independent_evidence":False,
        "independent_evidence_basis":"prediction_time_source_clusters_only",
        "policy":"agreement among Bull/Bear/Critic is model-consensus metadata only; it never creates an extra evidence cluster",
    }
