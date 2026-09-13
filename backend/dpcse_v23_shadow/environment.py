from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Sequence

from .spec import ENV_ARM_MIN_RESOLVED, ENV_CURRENT_WINDOW, ENV_MAX_STALENESS_CHECKPOINTS, ENV_REFERENCE_WINDOW

class EnvironmentState(str, Enum):
    WARMUP = "WARMUP"
    VALID = "VALID"
    SHIFT_DETECTED = "SHIFT_DETECTED"
    STALE = "STALE"

@dataclass(frozen=True)
class ResolvedTopLabel:
    checkpoint_index: int
    top_label_correct: bool
    def __post_init__(self) -> None:
        if isinstance(self.checkpoint_index, bool) or int(self.checkpoint_index) < 0:
            raise ValueError("checkpoint_index must be a non-negative integer")

@dataclass(frozen=True)
class EnvironmentAssessment:
    state: EnvironmentState
    n_resolved: int
    reference_errors: int | None
    current_errors: int | None
    integer_alarm: bool
    latest_resolved_checkpoint_index: int | None
    current_checkpoint_index: int

def relative_error_alarm(reference_errors: int, current_errors: int) -> bool:
    """Exact V2.3 integer alarm: c >= 7 AND 2*c - r >= 7."""
    r, c = int(reference_errors), int(current_errors)
    if not (0 <= r <= ENV_REFERENCE_WINDOW):
        raise ValueError("reference_errors outside 20-row window")
    if not (0 <= c <= ENV_CURRENT_WINDOW):
        raise ValueError("current_errors outside 10-row window")
    return c >= 7 and (2 * c - r) >= 7

def environment_state(resolved_rows: Sequence[ResolvedTopLabel], *, current_checkpoint_index: int) -> EnvironmentAssessment:
    idx = int(current_checkpoint_index)
    if isinstance(current_checkpoint_index, bool) or idx < 0:
        raise ValueError("current_checkpoint_index must be a non-negative integer")
    rows = tuple(resolved_rows)
    if any(rows[i].checkpoint_index >= rows[i + 1].checkpoint_index for i in range(len(rows) - 1)):
        raise ValueError("resolved rows must be strictly increasing by checkpoint_index")
    n = len(rows)
    latest = rows[-1].checkpoint_index if rows else None
    if n < ENV_ARM_MIN_RESOLVED:
        return EnvironmentAssessment(EnvironmentState.WARMUP, n, None, None, False, latest, idx)
    if latest is None or idx < latest:
        raise ValueError("current checkpoint cannot precede latest resolved checkpoint")
    if idx - latest > ENV_MAX_STALENESS_CHECKPOINTS:
        return EnvironmentAssessment(EnvironmentState.STALE, n, None, None, False, latest, idx)
    window = rows[-(ENV_REFERENCE_WINDOW + ENV_CURRENT_WINDOW):]
    reference, current = window[:ENV_REFERENCE_WINDOW], window[ENV_REFERENCE_WINDOW:]
    r = sum(1 for row in reference if not row.top_label_correct)
    c = sum(1 for row in current if not row.top_label_correct)
    alarm = relative_error_alarm(r, c)
    state = EnvironmentState.SHIFT_DETECTED if alarm else EnvironmentState.VALID
    return EnvironmentAssessment(state, n, r, c, alarm, latest, idx)
