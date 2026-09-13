from __future__ import annotations
from dataclasses import dataclass
from typing import Mapping, Tuple
@dataclass(frozen=True)
class ShadowHypothesisView:
    available:bool; hypotheses:Tuple[str,...]; source_digest:str; note:str=""
@dataclass(frozen=True)
class UMSEView:
    available:bool; integrity_pass:bool; state_label:str; mechanisms:Tuple[str,...]; source_digest:str; note:str=""
@dataclass(frozen=True)
class DPCSEView:
    status:str; candidate_model_frozen:bool; decision:str; p_bull:float|None; p_bear:float|None; locked_rows:int; source_digest:str; predictive_edge:str="NOT_PROVEN"
    @property
    def armed(self)->bool: return self.status in {"ARMED_N0","RUNNING_SHADOW"}
@dataclass(frozen=True)
class MFREInputFrame:
    shadow:ShadowHypothesisView; umse:UMSEView; dpcse:DPCSEView; context:Mapping[str,str]
    def upstream_reasons_not_ready(self)->Tuple[str,...]:
        reasons=[]
        if not self.shadow.available: reasons.append("SHADOW_LAB_UNAVAILABLE")
        if not self.umse.available: reasons.append("UMSE_UNAVAILABLE")
        elif not self.umse.integrity_pass: reasons.append("UMSE_INTEGRITY_FAIL")
        if not self.dpcse.candidate_model_frozen: reasons.append("DPCSE_CANDIDATE_NOT_FROZEN")
        if not self.dpcse.armed: reasons.append("DPCSE_NOT_ARMED")
        if self.dpcse.predictive_edge!="NOT_PROVEN": reasons.append("DPCSE_EDGE_STATUS_UNEXPECTED")
        return tuple(reasons)
