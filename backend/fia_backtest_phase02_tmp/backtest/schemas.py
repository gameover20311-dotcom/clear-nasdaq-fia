from dataclasses import dataclass, asdict, field
from typing import Any, Dict, Optional


@dataclass
class BacktestRun:
    run_id: str
    start_date: str
    end_date: str
    timeframe: str = "15m"
    horizons: tuple = ("4h", "8h")
    instrument: str = "QQQ"
    proxy_for: str = "NQ"
    engine_version: str = "unknown"
    status: str = "created"
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self):
        data = asdict(self)
        data["horizons"] = list(self.horizons)
        return data


@dataclass
class HistoricalObservation:
    timestamp: str
    price: Optional[float]
    instrument: str
    data: Dict[str, Any]
    data_quality_score: Optional[float] = None
    provider_status: Optional[Dict[str, Any]] = None
    source: Optional[str] = None

    def to_dict(self):
        return asdict(self)


@dataclass
class PredictionRecord:
    run_id: str
    timestamp: str
    price: Optional[float]
    bullish_probability: Optional[float]
    bearish_probability: Optional[float]
    fia_score: Optional[float]
    components: Dict[str, Any] = field(default_factory=dict)
    regime: Optional[str] = None
    data_quality_score: Optional[float] = None
    provider_status: Optional[Dict[str, Any]] = None

    def to_dict(self):
        return asdict(self)


@dataclass
class OutcomeRecord:
    prediction_id: str
    timestamp: str
    horizon: str
    entry_price: Optional[float]
    future_price: Optional[float]
    return_pct: Optional[float]
    direction: Optional[str]
    mfe_pct: Optional[float] = None
    mae_pct: Optional[float] = None

    def to_dict(self):
        return asdict(self)
