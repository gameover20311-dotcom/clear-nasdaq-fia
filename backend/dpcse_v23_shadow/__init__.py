"""DPCSE V2.3 zero-alpha shadow protocol.

This package is intentionally outside backend/fia so importing or testing the
candidate cannot silently change BASE_FIA's scientific MODEL/PROTOCOL identity.
"""
from .spec import SPEC_HASH, SPEC_VERSION
from .candidate import CandidateModelNotFrozen
from .decision import ShadowDecision, evaluate_shadow_decision
from .environment import EnvironmentState, environment_state

__all__ = [
    "SPEC_HASH",
    "SPEC_VERSION",
    "CandidateModelNotFrozen",
    "ShadowDecision",
    "evaluate_shadow_decision",
    "EnvironmentState",
    "environment_state",
]
