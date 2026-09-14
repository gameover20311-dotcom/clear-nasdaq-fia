from __future__ import annotations

from dataclasses import dataclass
import math
from .environment import EnvironmentAssessment, EnvironmentState
from .spec import DIRECTIONAL_MARGIN_MIN

@dataclass(frozen=True)
class ShadowDecision:
    decision: str
    p_bull: float
    p_bear: float
    directional_margin: float
    availability_integrity_pass: bool
    environment_state: str
    environment_gate_pass: bool
    directional_gate_pass: bool
    reason: str
    @property
    def committed_directional(self) -> bool:
        return self.decision in {"BULL", "BEAR"}

def validate_binary_probabilities(p_bull: float, p_bear: float) -> tuple[float, float]:
    bull, bear = float(p_bull), float(p_bear)
    if not (math.isfinite(bull) and math.isfinite(bear)):
        raise ValueError("probabilities must be finite")
    if not (0.0 <= bull <= 1.0 and 0.0 <= bear <= 1.0):
        raise ValueError("probabilities must be in [0,1]")
    if abs((bull + bear) - 1.0) > 1e-12:
        raise ValueError("DPCSE V2.3 binary probabilities must sum to one")
    return bull, bear

def evaluate_shadow_decision(*, p_bull: float, p_bear: float, availability_integrity_pass: bool, environment: EnvironmentAssessment) -> ShadowDecision:
    bull, bear = validate_binary_probabilities(p_bull, p_bear)
    margin = abs(bull - bear)
    env_pass = environment.state is EnvironmentState.VALID
    directional_pass = margin + 1e-15 >= DIRECTIONAL_MARGIN_MIN
    if not availability_integrity_pass:
        decision, reason = "NO_EDGE", "NO_EDGE_UNAVAILABLE_OR_INTEGRITY"
    elif not env_pass:
        decision, reason = "NO_EDGE", f"NO_EDGE_ENVIRONMENT_{environment.state.value}"
    elif not directional_pass:
        decision, reason = "NO_EDGE", "NO_EDGE_AMBIGUOUS"
    else:
        decision, reason = ("BULL" if bull > bear else "BEAR"), "DIRECTIONAL_GATE_PASS"
    return ShadowDecision(decision, bull, bear, margin, bool(availability_integrity_pass), environment.state.value, env_pass, directional_pass, reason)
