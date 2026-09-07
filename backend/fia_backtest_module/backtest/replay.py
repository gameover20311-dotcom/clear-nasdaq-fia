"""Historical FIA replay placeholder for Phase 2.

This file intentionally refuses to run a fake backtest. Phase 2 will connect
historical observations to the existing FIA forecast engine.
"""


class HistoricalReplay:
    def __init__(self, *args, **kwargs):
        self.ready = False

    def run(self, *args, **kwargs):
        raise RuntimeError(
            "Historical FIA Replay is Phase 2. Phase 1 only establishes the "
            "validated data foundation; no accuracy is calculated yet."
        )
