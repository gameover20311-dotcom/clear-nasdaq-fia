from pydantic import BaseModel, Field
from typing import Optional, Dict, List

class Signal(BaseModel):
    name: str
    score: float = Field(ge=-1, le=1)
    weight: float = Field(ge=0)
    detail: str = ''
    freshness: str = 'unknown'

class Forecast(BaseModel):
    symbol: str = 'NQ'
    horizon_hours: int = 8
    direction: str
    bullish_probability: float
    bearish_probability: float
    confidence: float
    regime: str
    status: str
    score: float
    signals: List[Signal]
    invalidation: List[str]
    generated_at: str
    data_coverage: float
    source_status: Dict[str,str]

    # Intelligence Layer
    thesis: str = ""
    bullish_evidence: List[str] = []
    bearish_evidence: List[str] = []
    intelligence_coverage: float = 0.0
