from dataclasses import dataclass
from typing import Optional


@dataclass
class AblationResult:
    signal_removed: str
    horizon: str
    baseline_observations: int
    ablated_observations: int
    baseline_accuracy: Optional[float]
    ablated_accuracy: Optional[float]
    accuracy_delta: Optional[float]
    baseline_return_pct: Optional[float]
    ablated_return_pct: Optional[float]
    return_delta_pct: Optional[float]

    def to_dict(self):
        return {
            "signal_removed": self.signal_removed,
            "horizon": self.horizon,
            "baseline_observations": self.baseline_observations,
            "ablated_observations": self.ablated_observations,
            "baseline_accuracy": self.baseline_accuracy,
            "ablated_accuracy": self.ablated_accuracy,
            "accuracy_delta": self.accuracy_delta,
            "baseline_return_pct": self.baseline_return_pct,
            "ablated_return_pct": self.ablated_return_pct,
            "return_delta_pct": self.return_delta_pct,
        }
