# Phase 30 — Cognitive Evidence Intelligence Master Brain

Phase 30 adds a separate, auditable cognitive layer above the frozen FIA core.
It is research-only and contains no broker/order execution.

Implemented capabilities:

1. Verified evidence/provenance ledger with per-evidence checksum and optional hash-chain persistence.
2. Article-level news intelligence: source quality, official-domain detection, duplicate clustering, entity mapping, event type, novelty, surprise when available, observed market-reaction/priced-in logic, and NASDAQ impact weighting.
3. Fifteen specialist brains: structure, MTF trend, NQ/ES/SPX confirmation, mega caps, semis, breadth, rates, DXY, macro surprise, Fed communication, news, earnings, liquidity/session, volatility/options, and regime.
4. Independent bullish/bearish hypotheses, counter-case, autonomous evidence-importance ordering, and controlled investigation queue.
5. Independent critic with contradiction checks, missing-data challenges, correlated-evidence double-counting detection, and fail-closed research hold.
6. Point-in-time historical analogy retrieval. Only earlier historical outcomes already knowable by the target timestamp may be used.
7. Transparent regime-aware fusion with reliability weighting and correlation caps. Outcome labels never modify live weights.
8. Development-only Platt calibration with a separately reported holdout.
9. Rolling drift monitoring and mistake attribution. The system diagnoses errors before any learning proposal.
10. FRED/ALFRED vintage adapter, SEC EDGAR primary-source verifier, observed QQQ post-news reaction helper, and one bounded contradiction/reinvestigation loop.
11. Full one-year cognitive replay report: accuracy, Brier, log loss, calibration error, 95% Wilson intervals, monthly/regime tables, naive/momentum/base comparisons, and specialist ablation.
12. Acceptance gate. A sophisticated architecture is not labelled market-grade unless integrity and untouched validation pass.

## Validation commands

From `backend`:

```bash
python fia_backtest_phase30/phase30_integrity_test.py
python fia_backtest_phase30/phase30_cognitive_replay.py
```

## Live endpoints

- `GET /api/cognitive/forecast?deep=false&horizon=8h`
- `GET /api/cognitive/forecast?deep=true&horizon=8h`
- `GET /api/cognitive/status`

`deep=true` activates normalized article retrieval, observed QQQ reaction analysis when candles are available, and one bounded reinvestigation pass when the critic asks for it.

## Important truth rule

This phase implements the requested cognitive architecture. It does **not** promise future accuracy, and it does not claim that market regimes will never require future maintenance. Missing source data remains missing rather than being converted to a neutral vote.
