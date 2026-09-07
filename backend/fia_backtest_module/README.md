# CLEAR NASDAQ — FIA Backtest Lab

## Build Status

**Phase 01 — Historical Data Foundation**  
**State: IN PROGRESS**

### Working now
- Backtest run manifest
- Historical observation schema
- FIA prediction schema
- Future outcome schema
- Provider/data-quality tracking
- Look-ahead-bias protection configuration
- JSONL/CSV persistence foundation

### Not active yet
- Historical FIA replay
- 4H/8H outcome calculation
- Accuracy
- Probability calibration
- Regime/session analysis
- Signal attribution/ablation
- Walk-forward testing
- Dashboard

### Next
**Phase 02 — Historical FIA Replay**

The replay engine must use the same FIA forecast logic as live mode and only
feed information that was available at each historical timestamp.
