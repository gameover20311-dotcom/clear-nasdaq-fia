# Phase 13 — Historical Prediction + Outcome Dataset Integration

This phase establishes the standardized dataset interface required by the
FIA Backtest Lab.

Required fields include:

- prediction_id
- timestamp
- horizon
- symbol
- direction
- bullish_probability
- bearish_probability
- confidence
- entry_price
- future_price
- return_pct
- outcome_direction
- correct

The integration layer:
1. reads the real historical CSV;
2. validates required fields;
3. rejects invalid datasets;
4. writes a validated copy only when records are valid.

No historical predictions or outcomes are fabricated.

No live FIA weights or forecast logic are modified.

Place the real dataset at:

`fia_backtest_phase13/data/historical_predictions.csv`
