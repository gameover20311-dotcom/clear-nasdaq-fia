# V6 benchmark governance

- TRAIN only: calibration, regime-profile fitting, teacher distillation.
- DEV only: architecture iteration and feature ablation.
- HOLDOUT: full code/config/cases frozen before local or Sol outputs; first-write immutable; complete-cohort scoring.
- Forward-OOS: prediction committed before future outcome; later result and autopsy are immutable.
- Failure-memory lookup is chronological: only rows with `resolved_at_utc < forecast_as_of_utc` may affect a forecast.
- Market-edge evidence and Sol-behavioral-parity are separate metrics and must never be conflated.
