# SIMONS SHADOW LAB V2 HYBRID — FINAL READINESS

Status date: 2026-09-11

## Verdict

**RESEARCH INFRASTRUCTURE: READY**

This verdict is intentionally limited to research infrastructure. It is not a claim of predictive edge, profitability, trading readiness, or replication of Renaissance Technologies / Medallion.

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

### Added / strengthened in V2 Hybrid

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

## Finalized negative-control harness

`negative_controls.py` adds a deterministic scrambled-label pipeline diagnostic.

- Resolved bullish/bearish labels are shuffled **within each horizon**.
- Exact bullish/bearish marginal counts are preserved.
- Unresolved-row locations are preserved.
- Every lock-time feature is verified unchanged before the control search runs.
- The same declared discovery machinery is re-run on scrambled labels.
- A broken pipeline that continues to produce robust discoveries on scrambled labels is explicitly failed.
- A PASS requires at least **100 control trials** and the **95% Wilson upper bound** of the false-discovery trial rate to be <= the declared alpha.
- Fewer trials cannot produce a PASS.
- Passing negative controls never upgrades predictive edge to proven.
- If real resolved data are insufficient, the harness returns `INSUFFICIENT_REAL_RESOLUTIONS`; it does not synthesize observations.

This is a pipeline falsification test, not proof of market edge.

## Finalized sequential alpha spending

`sequential_testing.py` prevents repeated peeking at the same forward hypothesis from silently spending alpha over and over.

- Information fractions must be pre-registered, strictly increasing, and end at `1.0`.
- Family alpha is Bonferroni-allocated across the pre-registered hypothesis family first.
- Each hypothesis then receives an O'Brien-Fleming-shaped cumulative spending schedule.
- Ordinary p-values are compared only with the **incremental alpha budget** for that look.
- By the union bound, the sum of the repeated-look Type-I budgets is bounded by the pre-allocated hypothesis alpha even when look statistics are dependent.
- The implementation explicitly does **not** claim to reproduce exact canonical Lan-DeMets group-sequential boundaries.
- The plan is immutable and SHA256-sealed before the first look.
- Look events are append-only and hash-chained.
- Duplicate/out-of-order looks are rejected.
- Once a sequential threshold is crossed, later peeking is blocked and the status is only `STOP_FOR_STATISTICAL_REVIEW` / `SEQUENTIAL_THRESHOLD_MET_REQUIRES_REVIEW`.
- Threshold crossing never auto-promotes a candidate and never sets predictive edge to proven.

This is deliberately conservative: scientific validity is preferred over squeezing maximum power from tiny samples.

## Actual-schema decision

The independent Cloud package was not copied blindly. Its proposed schema was built without the real CLEAR NASDAQ installation and included assumptions that do not match the current production row contract. V2 Hybrid therefore uses the project's actual 4H/8H two-way bullish/bearish probabilities and preserves missing fields as missing.

No neutral probability, proxy evidence or synthetic production row is invented by the hybrid adapter.

## Final CI evidence

Final branch-head GitHub Actions run `34588890948`, job `103229361907`, on head `474b52119abb875ad111d71a0d72a73122780366` verified:

- Compilation: **PASS**
- Real test-discovery guard: **PASS**
- `DISCOVERED_TESTS = 50`
- `Ran 50 tests in 1.391s`
- **50/50 PASS**

The nine added control tests cover:

1. Total sequential alpha never exceeds the family-allocated hypothesis budget.
2. Invalid/non-final information schedules fail closed.
3. Early looks use incremental alpha rather than reusing the full 0.05.
4. The immutable sequential ledger rejects duplicate/out-of-order looks and stops after threshold crossing.
5. Scrambled outcomes preserve class marginals and all lock-time features.
6. Negative controls fail closed when genuine resolved observations are insufficient.
7. A deliberately broken search that always finds a fake edge is detected and failed.
8. Too few negative-control trials cannot produce a PASS.
9. A clean control can PASS only after the strict 100-trial/Wilson gate is satisfied.

All prior V1/V2 regressions continue to pass in the same suite.

## Real durable Forward-OOS truth at final implementation check

A fresh read-only Render Postgres query on 2026-09-11 found:

- `CLEAR-NASDAQ-FORWARD-OOS-V5-V662`: one real `ABSTENTION_OBSERVATION`.
- `CLEAR-NASDAQ-FORWARD-OOS-V6-V672`: one real `FORECAST_LOCK`.
- No production `RESOLUTION_4H` event.
- No production `RESOLUTION_8H` event.

Therefore the **real-data negative-control gate is not yet statistically runnable** for V6. Its correct present state is `INSUFFICIENT_REAL_RESOLUTIONS`, not PASS or FAIL.

Likewise, no sequential alpha plan is frozen for a real candidate yet because no scientifically accepted candidate exists. Creating a plan now for an invented candidate would be fake pre-registration.

Therefore no real V6 candidate performance, calibration, predictive edge or profitability can currently be inferred. This is an evidence limitation, not a software failure.

## Production isolation at final compare

Relative to production `main` (`ebaadf876e5e78ce6ced2b99936aa3eac209d588`), the hybrid branch is **61 commits ahead, 0 behind**. The compare contains **31 changed files and every one is ADDED**. Existing production files modified: **0**. Existing production files deleted: **0**.

## Remaining scientific limitations

1. The Python write barrier is defense in depth, not a kernel security boundary. Filesystem permissions remain the stronger boundary.
2. Sequential alpha spending controls repeated looks **after a family is pre-registered**. Starting new hypothesis families indefinitely is still a research-governance problem and must remain visible in the experiment registry.
3. Negative controls can reveal a broken pipeline but cannot prove the market contains an exploitable signal.
4. Correlation/redundancy among candidate rules is not yet modeled as portfolio-independent evidence.
5. Capacity, order-book market impact and latency sensitivity are not modeled. No sizing or execution claim is made.
6. MFE/MAE can only be evaluated if genuine source data provides them causally; V2 does not synthesize them.
7. More complex Bayesian, regularized, clustering or survival models are not automatically superior on the present tiny genuine sample. They should only be added with a declared search budget and adequate unseen evidence.
8. Historical/state-transition findings remain discovery until frozen and evaluated on genuinely new post-freeze observations.

## Final scientific rule

**FIA predicts -> Forward-OOS locks reality -> Shadow Lab characterizes/calibrates -> negative controls challenge the pipeline -> hypotheses are preregistered -> candidate freezes -> sequential alpha plan freezes -> only genuinely new post-freeze observations validate -> human research review only.**

Engineering success never upgrades `NOT PROVEN` to predictive edge.
