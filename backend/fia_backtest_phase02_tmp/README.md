# CLEAR NASDAQ — FIA Backtest Lab — Phase 02

## Status
**IN PROGRESS — Historical FIA Replay**

### Working now
- Loads historical FIA snapshots from JSONL/CSV.
- Sorts observations chronologically.
- Rejects future-dated observations/source timestamps.
- Runs the supplied FIA forecast function against each historical snapshot.
- Produces timestamped `PredictionRecord` objects.
- Carries data-quality and provider-evidence fields into each prediction.

### Important integrity rule
Phase 02 does **not** call the live `ProviderHub.snapshot()` during replay.
That would use today's/latest provider data and create look-ahead bias. The
replay engine requires timestamped historical inputs.

### Not active yet
- Automatic historical data acquisition
- 4H/8H outcomes
- Accuracy/calibration metrics
- Regime/session analysis
- Walk-forward testing
- Dashboard

### Next
**Phase 03 — Future Outcome Engine**

Phase 03 will join each prediction to later NQ/price candles and calculate
4H/8H returns, direction, MFE and MAE.
