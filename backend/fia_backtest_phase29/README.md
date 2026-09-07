# Phase 29 — Authenticity Foundation

This batch makes four evidence-integrity upgrades without changing FIA forecast
weights:

1. `False` outcomes remain in every accuracy denominator. The previous Phase 28
   100% report is rejected; it was caused by dropping all losing rows.
2. Entry, 4H and 8H outcomes use completed Massive NQ 5-minute bars from one
   entry-time frozen futures contract. Yahoo is no longer the outcome oracle.
3. Historical OB, FVG, liquidity, SMT and execution features are detected before
   and independently of the FIA forecast direction.
4. Hard replay gates now require source provenance, at least 95% outcome
   resolution, non-perfect-result review, deterministic tests and declared
   runtime dependencies.

Run the local, dependency-free validation from `backend`:

```bash
python fia_backtest_phase29/phase29_truth_test.py
python fia_backtest_phase29/phase29_revalidate_predictions.py
```

The Phase 29 revalidation preserves every frozen Phase 28 prediction and only
replaces its outcome oracle. It is marked `OUTCOME_REVALIDATED_CORE_ONLY`, not
market-grade, because an entirely new one-year replay is still required after
the independent chart change.

Research only. No broker connection or order execution is included.
