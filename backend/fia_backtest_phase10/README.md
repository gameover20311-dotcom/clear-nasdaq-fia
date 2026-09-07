# Phase 10 — Walk-Forward Validation

Phase 10 creates chronological rolling train/validation windows.

Design:
- historical observations are sorted by timestamp;
- training data always precedes validation data;
- validation observations are never included in the earlier training window;
- train size, validation size, and step size are configurable.

The current implementation evaluates already-generated historical records.
It does not retrain or refit the live FIA model inside every window.

Therefore this phase provides walk-forward evaluation infrastructure,
not proof of model robustness by itself.

It does not modify live FIA weights or forecast logic.

Actual conclusions require real historical prediction/outcome records.
