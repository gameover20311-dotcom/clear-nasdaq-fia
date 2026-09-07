from dataclasses import dataclass


@dataclass(frozen=True)
class BacktestConfig:
    """Phase-1 configuration; no model optimization is allowed here."""

    start_date: str
    end_date: str
    timeframe: str = "15m"
    instrument: str = "QQQ"
    proxy_for: str = "NQ"
    horizons: tuple = ("4h", "8h")
    min_data_quality: float = 0.0
    allow_missing_inputs: bool = True
    prevent_lookahead: bool = True

    def validate(self):
        if not self.start_date or not self.end_date:
            raise ValueError("start_date and end_date are required")
        if not self.prevent_lookahead:
            raise ValueError("prevent_lookahead must remain enabled")
        if not self.horizons:
            raise ValueError("At least one horizon is required")
