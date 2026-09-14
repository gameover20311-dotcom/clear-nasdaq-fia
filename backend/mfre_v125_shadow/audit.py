from __future__ import annotations
from dataclasses import dataclass
import hashlib, json
from typing import Any, Mapping, Optional, Tuple
from .types import RandomnessOwnership
_EXTERNAL_REQUIRED=("event_time","available_time","provider_identity","sequence_id","raw_source_hash","receive_time")
@dataclass(frozen=True)
class AuditEvent:
    action_id:str; observed_output_digest:str; ownership:RandomnessOwnership; fresh_xi:float; eta_if_owned:Optional[float]=None; provenance:Optional[Mapping[str,Any]]=None
    def __post_init__(self):
        if not self.action_id.strip() or not self.observed_output_digest.strip(): raise ValueError("audit event requires action and output digest")
        if not 0.0<=float(self.fresh_xi)<=1.0: raise ValueError("fresh_xi must be in [0,1]")
        if self.ownership is RandomnessOwnership.EXTERNAL_PROVIDER:
            if self.eta_if_owned is not None: raise ValueError("MFRE_EXTERNAL_PROVIDER_ETA_MUST_NOT_BE_RECORDED")
            p=dict(self.provenance or {}); missing=[k for k in _EXTERNAL_REQUIRED if p.get(k) in (None,"")]
            if missing: raise ValueError("MFRE_EXTERNAL_PROVENANCE_MISSING:"+",".join(missing))
        elif self.ownership is RandomnessOwnership.ENGINE_OWNED:
            if self.eta_if_owned is None: raise ValueError("MFRE_ENGINE_OWNED_ETA_REQUIRED")
            if not 0.0<=float(self.eta_if_owned)<=1.0: raise ValueError("eta_if_owned must be in [0,1]")
        elif self.ownership is RandomnessOwnership.NONE_DETERMINISTIC and self.eta_if_owned is not None: raise ValueError("MFRE_DETERMINISTIC_PRIMITIVE_HAS_NO_ETA")
    def hashed_payload(self)->Mapping[str,Any]:
        p={k:v for k,v in dict(self.provenance or {}).items() if k not in {"hostname","cwd","path","generated_utc"}}
        return {"action_id":self.action_id,"observed_output_digest":self.observed_output_digest,"ownership":self.ownership.value,"fresh_xi":round(float(self.fresh_xi),12),"eta_if_owned":None if self.eta_if_owned is None else round(float(self.eta_if_owned),12),"provenance":p}
    @property
    def evidence_hash(self)->str:
        raw=json.dumps(self.hashed_payload(),sort_keys=True,separators=(",",":"),ensure_ascii=True,allow_nan=False).encode(); return hashlib.sha256(raw).hexdigest()
@dataclass(frozen=True)
class AuditLog:
    events:Tuple[AuditEvent,...]=()
    def append(self,event:AuditEvent)->"AuditLog": return AuditLog(self.events+(event,))
