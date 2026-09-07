from dataclasses import dataclass
from typing import Optional


@dataclass
class RegimeRecord:
    timestamp: str
    horizon: str
    regime: str
    direction: Optional[str] = None
    probability: Optional[float] = None
    return_pct: Optional[float] = None
    correct: Optional[bool] = None

    def to_dict(self):
        return {
            "timestamp": self.timestamp,
            "horizon": self.horizon,
            "regime": self.regime,
            "direction": self.direction,
            "probability": self.probability,
            "return_pct": self.return_pct,
            "correct": self.correct,
        }
