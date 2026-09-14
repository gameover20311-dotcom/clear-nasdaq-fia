from __future__ import annotations

"""Zero-alpha descriptive pilot diagnostics; never a promotion/edge verdict."""
from dataclasses import dataclass
import math
from typing import Sequence

@dataclass(frozen=True)
class Paired8HRow:
    base_p_bull: float
    candidate_p_bull: float
    outcome_bull: bool
    integrity_eligible: bool = True
    candidate_decision: str = "NO_EDGE"
    def __post_init__(self) -> None:
        for value in (self.base_p_bull, self.candidate_p_bull):
            if not math.isfinite(float(value)) or not 0.0 <= float(value) <= 1.0:
                raise ValueError("probabilities must be finite in [0,1]")

@dataclass(frozen=True)
class PilotDiagnostics:
    n_all_eligible: int
    n_directional_committed: int
    base_mean_brier: float | None
    candidate_mean_brier: float | None
    mean_paired_delta: float | None
    directional_gate_pass_rate: float | None
    confirmatory: bool = False
    promotion_eligible: bool = False
    predictive_edge: str = "NOT_PROVEN"

def binary_brier(p_bull: float, outcome_bull: bool) -> float:
    p = float(p_bull)
    if not math.isfinite(p) or not 0.0 <= p <= 1.0: raise ValueError("p_bull must be finite in [0,1]")
    y = 1.0 if outcome_bull else 0.0
    return (p - y) ** 2 + ((1.0 - p) - (1.0 - y)) ** 2

def pilot_diagnostics(rows: Sequence[Paired8HRow]) -> PilotDiagnostics:
    eligible = [row for row in rows if row.integrity_eligible]
    committed = [row for row in eligible if str(row.candidate_decision).upper() in {"BULL", "BEAR"}]
    n = len(eligible)
    if not n: return PilotDiagnostics(0, 0, None, None, None, None)
    base_losses = [binary_brier(r.base_p_bull, r.outcome_bull) for r in eligible]
    candidate_losses = [binary_brier(r.candidate_p_bull, r.outcome_bull) for r in eligible]
    base_mean, candidate_mean = sum(base_losses) / n, sum(candidate_losses) / n
    return PilotDiagnostics(n, len(committed), base_mean, candidate_mean, base_mean - candidate_mean, len(committed) / n)
