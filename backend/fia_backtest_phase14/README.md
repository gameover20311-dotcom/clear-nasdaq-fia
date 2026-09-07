# Phase 14 — Historical Prediction Recorder

This phase creates the standardized recorder required to preserve FIA
predictions for future backtesting.

Each prediction can store:

- prediction_id
- timestamp
- horizon
- symbol
- direction
- bullish_probability
- bearish_probability
- confidence
- entry_price

The outcome layer can later attach:

- future_price
- return_pct
- outcome_direction
- correct

Important:
The test deliberately does NOT write sample data into the real historical
dataset.

The recorder does not modify FIA forecast calculations, weights, or live
decision logic.

Next step:
Connect this recorder to the existing FIA forecast endpoint.
