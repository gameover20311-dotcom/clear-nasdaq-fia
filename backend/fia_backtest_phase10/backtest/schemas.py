from dataclasses import dataclass
from typing import Optional


@dataclass
class WalkForwardWindow:
    window_id: int
    train_start: str
    train_end: str
    validation_start: str
    validation_end: str
    train_observations: int
    validation_observations: int
    validation_accuracy: Optional[float] = None
    validation_return_pct: Optional[float] = None

    def to_dict(self):
        return {
            "window_id": self.window_id,
            "train_start": self.train_start,
            "train_end": self.train_end,
            "validation_start": self.validation_start,
            "validation_end": self.validation_end,
            "train_observations": self.train_observations,
            "validation_observations": self.validation_observations,
            "validation_accuracy": self.validation_accuracy,
            "validation_return_pct": self.validation_return_pct,
        }
