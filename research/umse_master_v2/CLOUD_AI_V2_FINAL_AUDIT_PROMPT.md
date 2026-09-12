# CLOUD AI — UMSE MASTER V2 FULL FINAL HOSTILE AUDIT

You are auditing **CLEAR NASDAQ FIA — UMSE MASTER V2 FULL**.

This is a hostile scientific/engineering audit, not a code-review formality. Do not reward complexity, test count, documentation quality, or ambition. Your job is to try to prove the system wrong, identify unsupported claims, delete redundant machinery, find leakage/identity/protocol defects, and determine whether the V2 research build is genuinely ready for real-data calibration and later Forward-OOS work.

## Scope

Repository: `gameover20311-dotcom/clear-nasdaq-fia`

Branch: `research/umse-master-v2-full`

Production base that must remain untouched: `1ab93b09d22b77e2bdce99fcfc1418395cbdf78d`

V2 source/identity checkpoint to audit first: `5a8104c314d52c45fed46a8aa647549b0e5403d9`

Dedicated V2 CI run: `34696256826`

Expected V2 identities at that checkpoint:

- MODEL: `0594b5ca955176e52ea6173072dab5d9234c5db0ed3ca7ca5773c8328e784afc`
- PROTOCOL: `9949ee06182ef679261c73aac3cd7d8e35774fbaf3b3f6affb878ff632add58c`
- INFRASTRUCTURE: `2f4d8ebff162cf719b23a137620ff5440b77154a1ed54b65179112a6c751b8cb`
- Classification manifest: `6209ec304e8f2789ba36434c2182d33cb247213153bf19958deacf055144f1d2`

Read:

- `research/umse_master_v2/UMSE_V2_FINAL_RESEARCH_REPORT.md`
- `research/umse_master_v2/UMSE_V2_BUILD_MANIFEST.json`
- all files under `research/umse_master_v2/src/umse_master_v2/`
- all files under `research/umse_master_v2/tests/`
- `.github/workflows/umse-v2-research.yml`
- relevant repaired V1 dependencies under `research/umse_master/src/umse_master/`

## Non-negotiable current scientific status

Do not upgrade these without actual unseen evidence:

- `SUCCESSOR_CAMPAIGN_STARTED=false`
- `ALPHA_SPENT=0`
- `PREDICTIVE_EDGE=NOT_PROVEN`
- `PRODUCTION_INTEGRATION=false`
- `PREDICTIVE_MAPPING_FROZEN=false`
- `REAL_MBO_CALIBRATION=NOT_DONE`
- `FORWARD_OOS_EDGE=NOT_PROVEN`

A green CI run proves engineering contracts only. It does not prove market skill.

## FIRST PASS MUST BE READ-ONLY

Do **not** modify files on the first pass.
Do **not** open a PR.
Do **not** repair anything yet.
Do **not** invent missing market data.
Do **not** reinterpret synthetic tests as predictive evidence.

Return findings first. Repairs happen only after findings are accepted.

## Audit objectives

### 1. Production isolation

Prove from Git history/diff, not assumption, that the branch does not alter production behavior outside the explicitly allowed research paths/workflow.

Challenge the workflow isolation grep and look for bypasses, symlinks, generated files, import side effects, packaging surprises, workflow changes, or path tricks.

### 2. MBO / L2 / market-data truth

Attack the MBO contract and queue-survival logic.

Check whether any aggregate L2, trades/quotes, proxy, reconstructed book, synthetic event, or incomplete sequence could accidentally gain order-by-order/MBO semantics.

Specifically challenge:

- order ID uniqueness assumptions
- sequence-domain completeness
- sequence resets/restarts
- multi-channel/multi-source sequence spaces
- modify/cancel/trade semantics
- partial fills
- reused order IDs
- price/side mutation assumptions
- session resets
- packet loss
- historical feed normalization
- hidden provider-specific semantics
- event-time vs available-time vs ingest-time
- stale data handling
- queue-position claims
- trader-identity claims

Any exact queue claim that cannot survive real CME/Rithmic/NinjaTrader semantics must be downgraded.

### 3. Causal integrity / future leakage

Try to inject future information into every path.

Audit all uses of:

- `event_time_utc`
- `available_time_utc`
- `ingested_time_utc`
- decision time
- outcome time
- horizon resolution time
- state-point eligibility
- book snapshots
- shocks
- cross-market lead/lag
- replay/validation

Check whether sorting, normalization, standardization, state geometry, topology, or any batch computation uses observations that would not have existed at the historical decision time.

### 4. Information velocity / lead-lag nulls

Challenge whether the lead/lag methods can report significance from:

- shared market clock
- autocorrelation
- repeated shocks
- event clustering
- exchange/feed latency asymmetry
- duplicated events
- deterministic periodicity
- common-driver effects
- multiple testing
- parameter search over lag windows
- circular-shift artifacts

Confirm that a significant screen cannot become calibration, causal evidence, a forecast probability, or promotion evidence.

### 5. Queue lifetime / survival analysis

Attack censoring semantics and survival estimates.

Check:

- all-censored behavior
- informative censoring
- session-end censoring
- partial-order survival
- competing risks (cancel vs trade)
- time-varying covariates
- sequence gaps
- minimum sample behavior
- misuse of median/restricted mean survival

Do not accept a persistence claim if the observation process itself explains it.

### 6. Order-book memory

Challenge conversion of snapshot-step autocorrelation into physical time.

Check:

- irregular sampling
- missing snapshots
- bursty updates
- stale books
- duplicate snapshots
- session breaks
- nonstationarity
- normalization leakage

If half-life cannot be defended in seconds, the cross-scale gate must remain closed.

### 7. Resistance field

Try to prove that the field is merely a transformed depth imbalance or silently assumes unavailable flow.

Check whether provision/depletion semantics are provider-correct, whether missing components become zeros, whether scores are bounded only cosmetically, and whether any directional interpretation exceeds the evidence.

### 8. Latent mechanism competition

This is a high-risk area for storytelling.

Challenge every mechanism score:

- informed buying/selling
- short covering
- long liquidation
- passive accumulation/distribution
- liquidity vacuum up/down
- bid/ask absorption
- balanced/noise

Determine whether different mechanisms are observationally distinguishable with the stated inputs. Identify redundant hypotheses and mechanisms that should be marked `NOT_IDENTIFIABLE_WITH_CURRENT_DATA`.

Verify that softmax weights are never described or consumed as calibrated posterior probabilities.

Verify no trader identity or strategic equilibrium is inferred from MBO order identity.

### 9. Counterfactual layer

Attack the observational counterfactual design.

Check:

- overlap/positivity
- post-treatment conditioning
- collider bias
- unmeasured confounding
- endogenous treatment assignment
- regime-dependent selection
- treatment definition stability
- SUTVA/interference violations in a market
- temporal dependence

If the design cannot support causal language, force it to stay falsification/diagnostic only.

### 10. Topological regime layer

Challenge the 0D persistence/MST interpretation.

Check:

- standardization leakage
- window dependence
- sample-size dependence
- distance metric sensitivity
- duplicate/near-duplicate states
- arbitrary fragmentation thresholds
- relation to simpler clustering/variance metrics

Try to show the topology layer is redundant. If a simpler statistic contains the same information, say so and recommend deletion unless incremental information is demonstrated.

### 11. Cross-scale transport

Attack the idea that microstructure evidence can survive into 4H/8H.

Check whether transport gates genuinely require measured persistence and whether any fallback/default opens them without empirical support.

No micro signal should influence 4H/8H merely because it is intuitively plausible.

### 12. Complexity/model competition

Try to make the complex model win by construction.

Challenge:

- parameter counting
- effective degrees of freedom
- feature selection leakage
- repeated experimentation
- data reuse
- tiny sample sizes
- in-sample fit masquerading as information

Confirm the complexity result remains diagnostic and never becomes predictive proof.

### 13. V2 paired Forward-OOS validation

This is critical.

Audit:

- fixed-N enforcement
- preregistration time strictly before first forecast
- MODEL fingerprint match
- PROTOCOL fingerprint match
- evidence hash presence
- duplicate forecast IDs
- horizon separation
- outcome not resolved early
- 8H primary endpoint
- 4H separate secondary endpoint
- no optional stopping
- no alpha reuse
- no historical data entering confirmation
- block bootstrap adequacy
- degeneracy handling
- calibration metrics
- same-sample BASE vs candidate comparison

Try to construct adversarial records that bypass the gate.

### 14. Identity/fingerprint system

Recompute identities independently.

Challenge:

- self-inclusive infrastructure fingerprint behavior
- manifest completeness
- files excluded from scope
- unclassified source files
- source files able to change scientific behavior while fingerprint class remains unchanged
- docs/config/workflow that should actually be protocol identity

A commit hash alone is not scientific identity.

### 15. Tests

Do not count tests. Attack them.

Look for:

- tautological assertions
- tests that only confirm constants
- synthetic scenarios that are too easy
- missing negative/adversarial cases
- non-determinism
- false-green mocks
- tests disconnected from real provider semantics
- tests that certify statistical gates using hand-designed perfect outcomes

Classify each important test family as:

- STRONG CONTRACT TEST
- USEFUL BUT SYNTHETIC
- WEAK / TAUTOLOGICAL
- MISSING REALITY TEST

### 16. Mathematical correctness

Re-derive or challenge the mathematics used in:

- queue survival
- Kaplan-Meier/restricted survival summaries
- information/lead-lag nulls
- cross-scale exponential survival
- complexity penalty
- Brier difference
- circular block bootstrap
- 0D persistence/MST equivalence
- mechanism weighting
- observational stratified counterfactual contrast

Report any mathematically valid calculation whose interpretation is still scientifically invalid.

### 17. Incremental value / redundancy

The ultimate research question is not whether UMSE V2 is sophisticated. It is:

`I(UMSE_t ; Y_future | FIA_t) > 0 ?`

Try to show every V2 feature is redundant with existing FIA information.

Require marginal/incremental evidence before retaining complexity. Recommend deleting modules that add no independently testable information.

## Required finding format

For every finding, classify it as exactly one of:

- `CRITICAL_GENUINE_BUG`
- `HIGH_GENUINE_BUG`
- `MEDIUM_GENUINE_BUG`
- `LOW_GENUINE_BUG`
- `SCIENTIFIC_IDENTIFIABILITY_LIMIT`
- `DATA_READINESS_GAP`
- `TEST_GAP`
- `REDUNDANT_COMPLEXITY`
- `DOCUMENTATION_OR_CLAIM_ISSUE`
- `ALREADY_DEFENDED_CORRECTLY`

For each genuine defect provide:

1. exact file/function/line or smallest precise location
2. why it is wrong
3. a concrete adversarial example
4. scientific/engineering consequence
5. minimum defensible repair
6. required regression test

Do not propose speculative rewrites when a smaller repair is sufficient.

## Mandatory final verdict table

Return separate verdicts for:

- Engineering correctness
- Production isolation
- Causal integrity
- MBO semantic integrity
- Mathematical correctness
- Statistical-screen integrity
- Mechanism identifiability
- Counterfactual validity
- Topological layer usefulness
- Cross-scale transport validity
- Identity/fingerprint integrity
- Test strength
- Real-data readiness
- Historical diagnostic readiness
- Forward-OOS protocol readiness
- Predictive edge evidence
- Production promotion eligibility

Allowed verdict words:

- `PASS`
- `CONDITIONAL_PASS`
- `FAIL`
- `NOT_TESTED`
- `NOT_ESTABLISHED`
- `NOT_APPLICABLE`

## Final required statement

Unless genuine unseen market evidence exists that is not currently in this branch, the predictive conclusion must remain exactly:

`PREDICTIVE_EDGE = NOT_PROVEN`

Stop after the audit report. Do not modify code until explicitly authorized.
