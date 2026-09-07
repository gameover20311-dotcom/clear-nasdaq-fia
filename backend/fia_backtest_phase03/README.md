# CLEAR NASDAQ — FIA Backtest Lab — Phase 03

## Status
**IN PROGRESS — Future Outcome Engine**

### Working now
- Loads historical OHLC candles from JSONL/CSV.
- Matches every FIA prediction to later historical prices.
- Calculates 1H, 4H and 8H forward returns.
- Classifies the actual outcome as bullish, bearish or flat.
- Calculates MFE and MAE over the forward window.
- Uses stable prediction IDs for reproducible joins.
- Gracefully marks outcomes unavailable when future candles are missing.

### Integrity rule
The outcome engine only reads candles whose timestamps are after the prediction timestamp. Future prices are used **only to label the outcome**, never to create the original FIA prediction.

### Not active yet
- Accuracy / precision metrics
- Probability calibration / Brier score
- Regime and session analysis
- Signal attribution / ablation testing
- Walk-forward validation
- Final dashboard

### Next
**Phase 04 — Accuracy and Metrics**
