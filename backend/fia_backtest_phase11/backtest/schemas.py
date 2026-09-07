from dataclasses import dataclass
from typing import Optional


@dataclass
class OOSResult:
    development_observations: int
    holdout_observations: int
    holdout_start: Optional[str]
    holdout_end: Optional[str]
    holdout_accuracy: Optional[float]
    holdout_average_return_pct: Optional[float]

    def to_dict(self):
        return {
            "development_observations": self.development_observations,
            "holdout_observations": self.holdout_observations,
            "holdout_start": self.holdout_start,
            "holdout_end": self.holdout_end,
            "holdout_accuracy": self.holdout_accuracy,
            "holdout_average_return_pct": self.holdout_average_return_pct,
        }
