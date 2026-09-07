# Phase 11 — Out-of-Sample Validation

Phase 11 creates a final chronological holdout period.

Design:
- records are sorted chronologically;
- the final N observations become the holdout;
- earlier observations remain development data;
- holdout observations are never used in the development split.

The holdout is evaluated using:
- observation count;
- start/end timestamp;
- accuracy;
- average realized return.

Important:
This implementation evaluates already-generated historical records.
It does not retrain the FIA model.

The holdout should remain untouched until all model-development decisions
are complete.

This phase does not modify live FIA weights or forecast logic.
