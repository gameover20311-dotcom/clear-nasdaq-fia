from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Mapping, Protocol, Tuple

_SHA256 = re.compile(r"^[0-9a-f]{64}$")

class CandidateModelNotFrozen(RuntimeError):
    pass

class FrozenDirect8HLaw(Protocol):
    model_id: str
    model_fingerprint: str
    predictive_state_schema_hash: str
    def predict_8h(self, predictive_state: Mapping[str, float]) -> Tuple[float, float]: ...

@dataclass(frozen=True)
class CandidateIdentity:
    model_id: str
    model_fingerprint: str
    predictive_state_schema_hash: str
    def __post_init__(self) -> None:
        if not self.model_id.strip():
            raise ValueError("model_id must be non-empty")
        for name, value in (("model_fingerprint", self.model_fingerprint), ("predictive_state_schema_hash", self.predictive_state_schema_hash)):
            if not _SHA256.fullmatch(str(value)):
                raise ValueError(f"{name} must be a lowercase SHA256 hex digest")

class UnfrozenCandidate:
    model_id = "DPCSE_V23_CANDIDATE_NOT_FROZEN"
    model_fingerprint = ""
    predictive_state_schema_hash = ""
    def predict_8h(self, predictive_state: Mapping[str, float]) -> Tuple[float, float]:
        raise CandidateModelNotFrozen("DPCSE_V23_CANDIDATE_MODEL_NOT_FROZEN: freeze predictive-state schema and Direct-8H model artifact before arming the shadow campaign")
