# SIMONS SHADOW LAB V2 HYBRID — FINAL READINESS

Status date: 2026-09-11

## Verdict

**RESEARCH INFRASTRUCTURE: READY**

This verdict is intentionally limited to the research infrastructure. It is not a claim of predictive edge, profitability, trading readiness, or replication of Renaissance Technologies / Medallion.

- Predictive edge: **NOT PROVEN**
- Profitability: **NOT PROVEN**
- Automatic production promotion: **DISABLED**
- Production mutation by the lab: **FORBIDDEN**
- Proprietary Renaissance / Medallion replication: **NOT CLAIMED**

## What V2 Hybrid combines

V2 Hybrid was built on the real-project-integrated Shadow Lab V1 and independently reimplemented the strongest scientific-control ideas observed in the separate Cloud AI package.

### Retained from our real-project V1

- Actual CLEAR NASDAQ Forward-OOS event model: `FORECAST_LOCK`, `RESOLUTION_4H`, `RESOLUTION_8H`.
- Verification of event sequence, previous-event hash, event SHA256, duplicate locks/resolutions and source head.
- SELECT-only Render/Postgres durable reader using transaction-level read-only mode.
- Actual 4H/8H bullish/bearish probability representation used by the project.
- Immutable snapshots and candidate records.
- Discovery-row exclusion and post-freeze-only forward validation.
- Separate immutable decision and later resolution events.
- Lock-time NQ structure, DXY, US10Y, mega-cap, semiconductor, participation/breadth, news, macro and earnings/guidance research features when present.
- Same-model agreement explicitly not treated as independent evidence.
- State signatures and state-transition research.
- Brier score, log loss, ECE/calibration, climatology comparison and regime diagnostics.
- Explicit assumed-friction reporting separated from statistical evidence.

### Added / strengthened from the independent Cloud design

- Structural `LockTimeRowView` leakage barrier; `.get()` cannot access outcome/resolution/future fields.
- Recursive blocking of post-outcome/future-like fields.
- Actual-schema probability validation; no synthetic neutral-probability field was imported.
- Full declared-grid multiplicity accounting and deterministic grid SHA256.
- Benjamini-Hochberg and Bonferroni corrections.
- Search-wide permutation null that prices the best result obtainable by chance across the whole declared search.
- Primary parametric comparison against the actual unconditional bullish/bearish base rate for the horizon, not only a 50% coin-flip null.
- Search-space budget fail-closed behaviour rather than silently truncating tests.
- Wilson confidence intervals.
- Statistical power/sample-size planning context instead of treating a fixed 30/50 observations as universally sufficient.
- Permutation-calibrated decay/regime-break diagnostic.
- Hash-chained experiment registry with origin, search family, full search-space SHA256, correction method and preregistered acceptance criteria.
- Whole production-tree SHA256 seal and a defense-in-depth Python write barrier covering `builtins.open`, `io.open`, `os.open`, delete, rename/replace, mkdir/rmdir, chmod and utime.
- Causally correct durable `as-of` snapshots that exclude events occurring after the snapshot cutoff.
- Machine-readable contract exclusions; missing/malformed required evidence is excluded rather than imputed.

## Actual-schema decision

The independent Cloud package was not copied blindly. Its proposed schema was built without the real CLEAR NASDAQ installation and included assumptions that do not match the current production row contract. V2 Hybrid therefore uses the project's actual 4H/8H two-way bullish/bearish probabilities and preserves missing fields as missing.

No neutral probability, proxy evidence or synthetic production row is invented by the hybrid adapter.

## CI evidence

GitHub Actions run `34563122789`, job `103149747079`, on hybrid head `b5a5998c3c07703fc3ee37199cb0fbfa752d5cc0` verified:

- Compilation: **PASS**
- Real test-discovery guard: **PASS**
- `DISCOVERED_TESTS = 41`
- `Ran 41 tests in 0.190s`
- **41/41 PASS**

The suite includes all prior V1 regressions plus V2 tests for structural leakage blocking, outcome-invariant features, actual probability contract validation, whole-grid multiplicity, search-wide permutation determinism, actual direction baseline, search-budget fail-closed, drift calibration, statistical power floor, production write blocking, tree-seal change detection, experiment metadata sealing, as-of future-resolution exclusion, timestamp regression rejection and explicit contract exclusions.

## Real durable Forward-OOS truth at final implementation check

A read-only Render Postgres query on 2026-09-11 found:

- `CLEAR-NASDAQ-FORWARD-OOS-V5-V662`: one real `ABSTENTION_OBSERVATION`.
- `CLEAR-NASDAQ-FORWARD-OOS-V6-V672`: one real `FORECAST_LOCK`.
- V6 real `RESOLUTION_4H`: **0**.
- V6 real `RESOLUTION_8H`: **0**.

Therefore no real V6 candidate performance, calibration, predictive edge or profitability can currently be inferred. This is an evidence limitation, not a software failure.

## Remaining scientific limitations

1. The Python write barrier is defense in depth, not a kernel security boundary. The production tree should still be mounted/readable under filesystem permissions that deny lab writes where practical.
2. Multiple testing inside each declared search is accounted for. Repeated testing across many separately initiated future searches is a higher-level research-governance problem and must remain visible in the experiment registry.
3. Correlation/redundancy among candidate rules is not yet modeled as portfolio-independent evidence.
4. Capacity, order-book market impact and latency sensitivity are not modeled. No sizing or execution claim is made.
5. MFE/MAE can only be evaluated if genuine source data provides them causally; V2 does not synthesize them.
6. More complex Bayesian, regularized, clustering or survival models are not automatically superior on the present tiny genuine sample. They should only be added with a declared search budget and adequate unseen evidence.
7. Historical/state-transition findings remain discovery until frozen and evaluated on genuinely new post-freeze observations.

## Final scientific rule

**FIA predicts -> Forward-OOS locks reality -> Shadow Lab discovers hypotheses -> candidate freezes -> only genuinely new post-freeze observations validate -> human research review only.**

Engineering success never upgrades `NOT PROVEN` to predictive edge.