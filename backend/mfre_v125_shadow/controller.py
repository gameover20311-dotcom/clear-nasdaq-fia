from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from typing import Optional
from .adapters import MFREInputFrame
from .contract import INTEGRATION_BINDING_HASH, IMPLEMENTATION_SCOPE, PRODUCTION_AUTHORIZED
from .types import ControlState, DeclarationBundle


class ShadowRunStatus(str, Enum):
    INERT_DECLARATIONS_MISSING = "INERT_DECLARATIONS_MISSING"
    INERT_DECLARATIONS_UNFROZEN = "INERT_DECLARATIONS_UNFROZEN"
    INERT_UPSTREAM_NOT_READY = "INERT_UPSTREAM_NOT_READY"
    READY_SHADOW_CONTRACT_ONLY = "READY_SHADOW_CONTRACT_ONLY"


@dataclass(frozen=True)
class ShadowRunResult:
    status: ShadowRunStatus
    implementation_scope: str
    production_authorized: bool
    integration_binding_hash: str
    protocol_identity: Optional[str]
    control_state: Optional[ControlState]
    reasons: tuple[str, ...]
    directional_override: None = None


class MFREShadowController:
    """Fail-closed MFRE integration controller shell.

    It does not execute Bellman search yet. `READY_SHADOW_CONTRACT_ONLY` means the
    preregistered declaration record and upstream scientific dependencies are fit
    to hand to a separately audited execution engine. It does NOT mean MFRE has
    produced a market decision.
    """

    def __init__(self, declarations: DeclarationBundle | None = None):
        self._declarations = declarations

    def assess(self, frame: MFREInputFrame) -> ShadowRunResult:
        if self._declarations is None:
            return ShadowRunResult(
                ShadowRunStatus.INERT_DECLARATIONS_MISSING,
                IMPLEMENTATION_SCOPE,
                PRODUCTION_AUTHORIZED,
                INTEGRATION_BINDING_HASH,
                None,
                None,
                ("MFRE_DECLARATION_BUNDLE_MISSING",),
            )
        if not self._declarations.scientifically_frozen:
            return ShadowRunResult(
                ShadowRunStatus.INERT_DECLARATIONS_UNFROZEN,
                IMPLEMENTATION_SCOPE,
                PRODUCTION_AUTHORIZED,
                INTEGRATION_BINDING_HASH,
                None,
                None,
                tuple("MFRE_UNFROZEN:" + item for item in self._declarations.unresolved_fields),
            )
        upstream = frame.upstream_reasons_not_ready()
        if upstream:
            return ShadowRunResult(
                ShadowRunStatus.INERT_UPSTREAM_NOT_READY,
                IMPLEMENTATION_SCOPE,
                PRODUCTION_AUTHORIZED,
                INTEGRATION_BINDING_HASH,
                self._declarations.protocol_identity,
                None,
                upstream,
            )
        state = ControlState(
            (),
            self._declarations.compute_budget,
            self._declarations.acquisition_budget,
            self._declarations.selection_budget,
        )
        return ShadowRunResult(
            ShadowRunStatus.READY_SHADOW_CONTRACT_ONLY,
            IMPLEMENTATION_SCOPE,
            PRODUCTION_AUTHORIZED,
            INTEGRATION_BINDING_HASH,
            self._declarations.protocol_identity,
            state,
            ("MFRE_EXECUTION_ENGINE_NOT_YET_BOUND",),
        )
