# UMSE MASTER SCIENTIFIC SPEC V1

Status: DRAFT FOR PHASE-0 FREEZE

This specification defines an isolated Shadow-Lab candidate. It does not alter BASE_FIA, production forecasts, current Forward-OOS seals, or production identities.

## 1. Purpose

UMSE is a latent market-state inference engine for NQ. It is not a retail order-flow indicator and it is not assumed to possess edge merely because its internal model is sophisticated.

Primary scientific question:

`I(UMSE_t ; Y_future | FIA_t) > 0 ?`

Operational question:

Does FIA+UMSE improve on BASE_FIA on the same genuinely unseen observations, while preserving calibration and abstention discipline?

## 2. Latent state

Initial state vector:

`Z_t = [P, L, A, I, R, C, S]`

All components are bounded research variables with explicit uncertainty. No latent variable may be treated as directly observed.

### P — directional pressure
Net directional pressure inferred from signed flow, price response, cross-market agreement and persistence. P must not be a renamed price return.

### L — liquidity state
State of displayed/observable liquidity and its dynamics: depth, depletion, replenishment, spread/availability proxies, liquidity field geometry and queue survival where true MBO supports it.

### A — aggression / urgency
Estimated urgency of active buyers/sellers from event intensity, sweep behaviour, signed trade imbalance and acceleration. Aggression is distinct from directional success.

### I — information asymmetry
Degree to which observed response patterns are more consistent with informed activity than ordinary auction/noise, represented probabilistically rather than as a label.

### R — resilience
Ability of liquidity/price to recover after shocks: replenishment speed, impact decay and restoration of normal auction conditions.

### C — criticality / cascade susceptibility
Candidate transition/cascade risk. May use event-network intensity, spectral-radius-style quantities, variance, autocorrelation, recovery time and liquidity elasticity only after calibration. It is not a validated crash predictor.

### S — structural regime
Probability distribution over discrete/continuous market states, never a forced single label when uncertainty is high.

## 3. Candidate market mechanisms

Mechanism posterior may allocate probability across:

- informed buying
- informed selling
- short covering
- long liquidation
- passive accumulation
- passive distribution
- liquidity vacuum
- absorption
- balanced/noise auction

Mechanisms compete probabilistically. Multiple mechanisms may coexist.

## 4. Candidate market states

- BALANCED_AUCTION
- INFORMED_ACCUMULATION
- DISTRIBUTION
- LIQUIDITY_VACUUM
- SHORT_COVERING
- FORCED_LIQUIDATION
- DIRECTIONAL_CASCADE
- ABSORPTION
- TRANSITION
- CHAOS_UNCERTAIN

State output is a probability distribution plus uncertainty/confidence, not merely one string.

## 5. Causal information contract

Every input observation must carry:

- `event_time_utc`
- `available_time_utc`
- `ingested_time_utc`
- `source`
- `instrument`
- `data_class`
- `quality_state`
- `is_proxy`
- `provenance_id`

Eligibility at decision time `T` requires:

`available_time_utc <= T`

and the source-specific staleness rule must pass.

A later-revised value is not eligible as though the revision existed earlier.

If availability time cannot be proven, the datum is ineligible for scientific validation.

## 6. Data classes

- `REAL_LIVE_MBO`
- `REAL_HISTORICAL_MBO`
- `REAL_L2_DEPTH`
- `REAL_TRADES_QUOTES`
- `REAL_CROSS_MARKET`
- `PROXY_RESEARCH`
- `SYNTHETIC_TEST`

Synthetic data may validate software behaviour only. It can never contribute to claimed predictive evidence.

Proxy research data must be clearly identified and may not silently inherit MBO-level semantics.

## 7. Data-quality states

- FRESH
- STALE
- MISSING
- DEGRADED
- PROXY
- INELIGIBLE

Fail-closed principle: missing or scientifically ineligible inputs reduce confidence or yield `NO_UMSE_EDGE`; they are never imputed with future/current values solely to keep the model producing a signal.

## 8. Core research modules

### 8.1 Liquidity field

Represent observable liquidity as a field `L(p,t)` when source granularity supports it. Candidate derived quantities:

- local depth
- gradient
- curvature
- depletion rate
- replenishment rate
- persistence
- queue survival / cancellation hazard where true order identity exists

Do not claim queue survival from aggregated L2 that cannot identify individual orders.

### 8.2 Flow engine

Candidate observables:

- signed aggressive volume
- buy/sell event intensity
- sweep count/intensity
- cancellation intensity
- replenishment intensity
- large-trade events
- flow toxicity candidates

### 8.3 Impact and response surprise

Candidate impact model:

`ΔP = g(Q, L, V, R)`

Candidate residual:

`ε_t = ΔP_observed - E[ΔP | Q,L,V,R]`

UMSE must model both:

- what happened
- what should have happened but did not

Candidate observation surprise:

`Surprise_t = -log P(O_t | Z_{t-1})`

Large surprise does not automatically imply direction; it indicates model-state mismatch requiring mechanism update.

### 8.4 Event interaction network

Candidate marked multivariate Hawkes-style event system over:

- buy aggression
- sell aggression
- cancellations
- replenishment
- sweeps
- large trades
- cross-market shocks

Spectral radius is classified `PLAUSIBLE_BUT_UNPROVEN` until calibrated and shown useful out of sample.

### 8.5 Information graph

Candidate nodes:

- NQ
- ES/SPX
- QQQ
- mega caps
- semiconductors
- US10Y
- DXY

Candidate methods:

- conditional mutual information
- transfer entropy where sample size supports it
- redundancy/synergy analysis
- PID only where statistically identifiable

Correlated inputs must not be counted as independent evidence merely because they arrive from different feeds.

### 8.6 State transition engine

Estimate transition probabilities between latent market states. Transition evidence must include uncertainty and data quality.

### 8.7 Survival / cross-scale propagation

Micro evidence contributes to 4H/8H only through an explicit persistence/propagation model.

Conceptual ladder:

`Micro -> Meso -> Session -> 4H -> 8H`

Candidate quantities:

- state survival probability
- hazard of state termination
- information half-life
- propagation probability
- resilience decay

Short-lived microstructure bursts must not automatically move long-horizon forecasts.

## 9. Market State Tension (MST)

MST is retained only as a research hypothesis.

Current conceptual structure:

`MST = (P*C*F*I*S) / (1 + H + R_d + U + D)`

This is NOT production mathematics. Phase 0 requires each term to be identifiable, non-duplicative and causally observable. A simpler model is preferred if the proposed terms are redundant or unstable.

Classification: `SPECULATIVE` until identified and validated.

## 10. Probability versus confidence

Probability describes the modelled distribution over future outcomes/states.

Confidence describes evidence sufficiency/reliability and must depend on:

- source quality
- freshness
- missingness
- posterior concentration
- model disagreement
- identifiability
- regime support

High directional probability with poor evidence quality must not be reported as high confidence.

## 11. 4H and 8H contracts

UMSE must produce independent research objects for 4H and 8H.

No 8H result may be mechanically copied from 4H or vice versa.

Each horizon object must include:

- state probabilities
- mechanism probabilities
- directional contribution candidate
- confidence
- data-quality summary
- propagation probability
- invalidation/rejection reasons
- provenance hash

The 8H horizon remains the primary confirmatory horizon under the existing FIA methodology unless a future protocol amendment explicitly changes that before outcomes.

## 12. Shadow-only output

Required top-level states:

- `SHADOW_ESTIMATE`
- `NO_UMSE_EDGE`
- `INSUFFICIENT_DATA`
- `PROTOCOL_INELIGIBLE`

No Phase-0/Phase-1 output may alter BASE_FIA production probabilities.

## 13. Historical replay rules

Historical replay may be used for:

- software debugging
- parameter estimation
- calibration
- falsification
- robustness checks

It must not be described as prospective validation.

Any period used to tune parameters is training/calibration and cannot simultaneously be an untouched test set.

## 14. Forward-OOS rules

Before Forward-OOS begins, freeze:

- code identity
- scientific protocol identity
- data eligibility rules
- feature definitions
- probability mapping
- abstention rules
- horizons
- BASE comparison
- primary endpoint

Each forecast must be locked before the move with timestamp and evidence/provenance hash. Outcomes are attached later without mutating the lock.

## 15. Evaluation against BASE_FIA

UMSE is not judged by standalone hit rate.

Required paired evaluation on the same unseen observations:

- Brier-loss difference
- calibration
- confidence reliability
- NO_EDGE selectivity
- regime-wise performance
- 4H and 8H separately

Primary conceptual paired quantity remains:

`Δ_t = L_BASE,t - L_FIA+UMSE,t`

Positive mean improvement is necessary but not sufficient; uncertainty and preregistered decision rules matter.

## 16. Kill switch

Return/reject as `NO_UMSE_EDGE` or reject the module if any of the following persists:

- no incremental information beyond FIA
- duplicated FIA evidence masquerades as new evidence
- only in-sample gains
- worse calibration
- increased false confidence
- future leakage
- unreproducible features
- dependence on unavailable production data
- unstable parameter estimates
- effect disappears under plausible regime split

Complexity is not success.

## 17. Module hostile classification

### ESSENTIAL
- causal timestamp/provenance contract
- data-quality contract
- liquidity/flow/impact primitives
- state uncertainty
- 4H/8H separation
- cross-scale persistence gate
- BASE comparison
- abstention/kill switch
- shadow isolation

### PLAUSIBLE_BUT_UNPROVEN
- Hawkes event network
- response surprise
- state survival/hazard
- transfer entropy
- information geometry
- critical-transition composite

### REDUNDANT_RISK
- multiple highly correlated breadth/mega-cap variants
- duplicate flow imbalance measures
- multiple volatility proxies without conditional-value testing
- same evidence repeated across mechanism experts

### SPECULATIVE
- MST closed-form formula
- free-energy/IRL/topological extensions
- any universal cascade threshold

### NOT_IDENTIFIABLE_WITH_CURRENT_DATA
Until genuine MBO/order identity is available:
- exact queue position
- individual-order survival
- true order-level cancellation lineage

These must not be faked from aggregate L2.

## 18. Phase-0 freeze decision criteria

Phase 0 is freeze-ready only when:

1. every input has causal availability semantics;
2. every latent variable has observable support and uncertainty;
3. proxy/synthetic data cannot masquerade as real validation data;
4. 4H/8H are independent contracts;
5. shadow output cannot alter BASE_FIA;
6. historical replay and Forward-OOS are explicitly separated;
7. incremental BASE comparison is defined;
8. kill-switch is binding;
9. unavailable MBO semantics are marked not identifiable;
10. implementation scaffold enforces these contracts.

Current decision after specification draft: `UMSE_PHASE_0_SPEC_FREEZE_READY = PENDING_IMPLEMENTATION_CONTRACT_TESTS`
