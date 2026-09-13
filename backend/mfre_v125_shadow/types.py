from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
import hashlib, json, math
from typing import Any, Mapping, Tuple

class ActionKind(str, Enum):
    ACQUIRE="A_acq"; COMPUTE="A_comp"; STOP="A_stop"
class RandomnessOwnership(str, Enum):
    EXTERNAL_PROVIDER="EXTERNAL_PROVIDER"; ENGINE_OWNED="ENGINE_OWNED"; NONE_DETERMINISTIC="NONE_DETERMINISTIC"
@dataclass(frozen=True)
class PrimitiveSpec:
    action_id:str; kind:ActionKind; cost:float; budget_name:str; randomness_ownership:RandomnessOwnership
    def __post_init__(self):
        if not self.action_id.strip(): raise ValueError("action_id must be non-empty")
        if not math.isfinite(float(self.cost)) or float(self.cost)<0: raise ValueError("cost must be finite and non-negative")
        if not self.budget_name.strip(): raise ValueError("budget_name must be non-empty")
        if self.kind is ActionKind.STOP and self.randomness_ownership is not RandomnessOwnership.NONE_DETERMINISTIC: raise ValueError("A_stop must be NONE_DETERMINISTIC in this integration shell")
@dataclass(frozen=True)
class DeclarationBundle:
    primitives:Tuple[PrimitiveSpec,...]; compute_budget:int; acquisition_budget:int; selection_budget:int; gamma_theta_id:str; phi_id:str; delta_stop_id:str; bellman_policy_id:str
    def __post_init__(self):
        if not self.primitives: raise ValueError("at least one primitive is required")
        ids=[p.action_id for p in self.primitives]
        if len(ids)!=len(set(ids)): raise ValueError("action_id values must be unique")
        if not any(p.kind is ActionKind.STOP for p in self.primitives): raise ValueError("an always-available A_stop primitive is required")
        for name,value in (("compute_budget",self.compute_budget),("acquisition_budget",self.acquisition_budget),("selection_budget",self.selection_budget)):
            if isinstance(value,bool) or int(value)<0: raise ValueError(f"{name} must be a non-negative integer")
        for name,value in (("gamma_theta_id",self.gamma_theta_id),("phi_id",self.phi_id),("delta_stop_id",self.delta_stop_id),("bellman_policy_id",self.bellman_policy_id)):
            if not str(value).strip(): raise ValueError(f"{name} must be declared")
    def canonical_payload(self)->Mapping[str,Any]:
        return {"primitives":[{"action_id":p.action_id,"kind":p.kind.value,"cost":float(p.cost),"budget_name":p.budget_name,"randomness_ownership":p.randomness_ownership.value} for p in sorted(self.primitives,key=lambda x:x.action_id)],"compute_budget":int(self.compute_budget),"acquisition_budget":int(self.acquisition_budget),"selection_budget":int(self.selection_budget),"gamma_theta_id":self.gamma_theta_id,"phi_id":self.phi_id,"delta_stop_id":self.delta_stop_id,"bellman_policy_id":self.bellman_policy_id}
    @property
    def protocol_identity(self)->str:
        raw=json.dumps(self.canonical_payload(),sort_keys=True,separators=(",",":"),allow_nan=False).encode(); return hashlib.sha256(raw).hexdigest()
@dataclass(frozen=True)
class ControlState:
    history:Tuple[Tuple[str,str],...]=(); compute_remaining:int=0; acquisition_remaining:int=0; selection_remaining:int=0
    def append(self,*,action_id:str,output_digest:str,kind:ActionKind)->"ControlState":
        c,a,s=self.compute_remaining,self.acquisition_remaining,self.selection_remaining
        if kind is ActionKind.COMPUTE:
            if c<=0: raise RuntimeError("MFRE_COMPUTE_BUDGET_EXHAUSTED")
            c-=1
        elif kind is ActionKind.ACQUIRE:
            if a<=0: raise RuntimeError("MFRE_ACQUISITION_BUDGET_EXHAUSTED")
            a-=1
        elif kind is not ActionKind.STOP: raise RuntimeError("MFRE_UNKNOWN_ACTION_KIND")
        return ControlState(self.history+((action_id,output_digest),),c,a,s)
