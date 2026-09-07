from datetime import datetime, timezone
from uuid import uuid4

from .config import BacktestConfig
from .schemas import BacktestRun
from .status import get_status


class BacktestRunner:
    """Phase-1 runner. It creates validated runs but deliberately does not replay FIA yet."""

    def __init__(self, storage):
        self.storage = storage

    def create_run(self, config: BacktestConfig, engine_version="unknown"):
        config.validate()
        run = BacktestRun(
            run_id=f"bt_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}_{uuid4().hex[:8]}",
            start_date=config.start_date,
            end_date=config.end_date,
            timeframe=config.timeframe,
            horizons=config.horizons,
            instrument=config.instrument,
            proxy_for=config.proxy_for,
            engine_version=engine_version,
            metadata={
                "lookahead_protection": config.prevent_lookahead,
                "min_data_quality": config.min_data_quality,
                "allow_missing_inputs": config.allow_missing_inputs,
            },
        )
        self.storage.append("backtest_runs", run.to_dict())
        return run

    @staticmethod
    def status():
        return get_status()
