from dataclasses import dataclass
from typing import Optional


@dataclass
class HistoricalRecord:
    prediction_id: str
    timestamp: str
    horizon: str
    symbol: str
    direction: Optional[str]
    bullish_probability: Optional[float]
    bearish_probability: Optional[float]
    confidence: Optional[float]
    entry_price: Optional[float]
    future_price: Optional[float]
    return_pct: Optional[float]
    outcome_direction: Optional[str]
    correct: Optional[bool]
    mfe_pct: Optional[float] = None
    mae_pct: Optional[float] = None

    def to_dict(self):
        return {
            "prediction_id": self.prediction_id,
            "timestamp": self.timestamp,
            "horizon": self.horizon,
            "symbol": self.symbol,
            "direction": self.direction,
            "bullish_probability": self.bullish_probability,
            "bearish_probability": self.bearish_probability,
            "confidence": self.confidence,
            "entry_price": self.entry_price,
            "future_price": self.future_price,
            "return_pct": self.return_pct,
            "outcome_direction": self.outcome_direction,
            "correct": self.correct,
            "mfe_pct": self.mfe_pct,
            "mae_pct": self.mae_pct,
        }
