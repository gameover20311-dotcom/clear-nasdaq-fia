# CLEAR NASDAQ — FIA Backtest Lab — Phase 05

## Probability Calibration

**STATUS: COMPLETE**

This phase tests whether FIA's stated directional confidence behaves like a real probability. It does not change the live FIA model.

### Added
- 0–1 and 0–100 probability normalization
- 4H and 8H reliability buckets
- Mean predicted probability vs empirical accuracy
- Expected Calibration Error (ECE)
- Maximum Calibration Error (MCE)
- Brier score
- Log loss

### Example
```python
from backtest.calibration import analyze, write_report
from backtest.metrics import load_jsonl

predictions = load_jsonl("data/predictions.jsonl")
outcomes = load_jsonl("data/outcomes.jsonl")
report = analyze(predictions, outcomes, horizons=("4h", "8h"))
write_report(report, "reports/calibration.json")
```

### Progress
- Phase 01 — Historical Data Foundation: COMPLETE
- Phase 02 — Historical FIA Replay: COMPLETE
- Phase 03 — Future Outcome Engine: COMPLETE
- Phase 04 — Accuracy + Metrics: COMPLETE
- Phase 05 — Probability Calibration: COMPLETE
- Phase 06 — Regime Analysis: NEXT
