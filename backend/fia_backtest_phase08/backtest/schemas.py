from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class SignalRecord:
    timestamp: str
    horizon: str
    signal: str
    direction: Optional[str] = None
    signal_score: Optional[float] = None
    probability: Optional[float] = None
    return_pct: Optional[float] = None
    correct: Optional[bool] = None
    metadata: dict = field(default_factory=dict)

    def to_dict(self):
        return {
            "timestamp": self.timestamp,
            "horizon": self.horizon,
            "signal": self.signal,
            "direction": self.direction,
            "signal_score": self.signal_score,
            "probability": self.probability,
            "return_pct": self.return_pct,
            "correct": self.correct,
            "metadata": self.metadata,
        }
