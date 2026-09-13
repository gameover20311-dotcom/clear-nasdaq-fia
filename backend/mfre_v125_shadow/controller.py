from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from typing import Optional
from .adapters import MFREInputFrame
from .contract import INTEGRATION_BINDING_HASH, IMPLEMENTATION_SCOPE, PRODUCTION_AUTHORIZED
from .types import ControlState, DeclarationBundle
class ShadowRunStatus(str,Enum):
    INERT_DECLARATIONS_MISSING="INERT_DECLARATIONS_MISSING"; INERT_UPSTREAM_NOT_READY="INERT_UPSTREAM_NOT_READY"; READY_SHADOW="READY_SHADOW"
@dataclass(frozen=True)
class ShadowRunResult:
    status:ShadowRunStatus; implementation_scope:str; production_authorized:bool; integration_binding_hash:str; protocol_identity:Optional[str]; control_state:Optional[ControlState]; reasons:tuple[str,...]; directional_override:None=None
class MFREShadowController:
    def __init__(self,declarations:DeclarationBundle|None=None): self._declarations=declarations
    def assess(self,frame:MFREInputFrame)->ShadowRunResult:
        if self._declarations is None:
            return ShadowRunResult(ShadowRunStatus.INERT_DECLARATIONS_MISSING,IMPLEMENTATION_SCOPE,PRODUCTION_AUTHORIZED,INTEGRATION_BINDING_HASH,None,None,("MFRE_DECLARATION_BUNDLE_NOT_FROZEN",))
        upstream=frame.upstream_reasons_not_ready()
        if upstream:
            return ShadowRunResult(ShadowRunStatus.INERT_UPSTREAM_NOT_READY,IMPLEMENTATION_SCOPE,PRODUCTION_AUTHORIZED,INTEGRATION_BINDING_HASH,self._declarations.protocol_identity,None,upstream)
        state=ControlState((),self._declarations.compute_budget,self._declarations.acquisition_budget,self._declarations.selection_budget)
        return ShadowRunResult(ShadowRunStatus.READY_SHADOW,IMPLEMENTATION_SCOPE,PRODUCTION_AUTHORIZED,INTEGRATION_BINDING_HASH,self._declarations.protocol_identity,state,())
