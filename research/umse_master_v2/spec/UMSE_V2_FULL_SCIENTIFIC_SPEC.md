# UMSE MASTER V2 FULL — Scientific Specification

## 1. Scope

UMSE V2 FULL extends the repaired UMSE V1 research baseline without altering production CLEAR NASDAQ. V1 remains the parent baseline; V2 must prove incremental value rather than inherit it by assertion.

The V2 research question is:

`I(V2_t ; Y_future | FIA_t, UMSE_V1_t) > 0 ?`

This is a statistical research question, not an edge claim. A positive raw estimator is never sufficient evidence. Any later implementation must use an explicit null/reference distribution, adequate sample size, causal availability and prospective validation.

## 2. V2 scientific layers

### A. Microstructure truth layer

Inputs may include genuine CME MBO/order-by-order data, L2 depth, trades/quotes and cross-market observations, but semantics are never interchangeable.

Exact order-lifecycle or queue-survival claims require:

1. genuine MBO-class data;
2. stable exchange/order identity;
3. event sequence integrity;
4. no missing lineage required by the metric;
5. causally available records only.

Order identity does **not** identify a trader, institution or strategy.

### B. Queue survival and order-book memory

Candidate measurements include order lifetime, cancellation hazard, execution hazard, replenishment persistence and depth-memory decay. Censored orders must remain censored. Missing lifecycle history cannot be silently repaired.

### C. Market-resistance field

V2 may model a descriptive resistance/support field from depth, replenishment and cancellation behavior. It is not literal physical force and is not calibrated predictive evidence until tested. Weighting parameters must be explicit and fingerprinted.

### D. Information velocity and propagation

V2 may test whether information shocks propagate from NQ-related instruments/nodes with measurable delay and survival. Source timestamps and availability timestamps remain separate. Cross-market lead/lag claims require a null and must survive latency controls.

### E. Latent agent/game competition

V2 may infer competing latent mechanisms such as informed demand, liquidation, covering, passive absorption or inventory rebalancing. It must not claim direct participant identity. Inverse-game or IRL-style models remain weakly identifiable unless real observables support them.

### F. Causal/counterfactual mechanism tests

Counterfactual claims require an explicit structural model and assumptions. Descriptive residuals are not counterfactual evidence. Interventions unavailable in observational data must be marked NOT_IDENTIFIABLE.

### G. Structural/topological regime diagnostics

Topology/geometry may summarize regime shape or transition structure, but no topological statistic is assumed predictive. Persistence or geometry is useful only if stable, reproducible and incrementally informative beyond simpler baselines.

### H. Renormalized cross-scale transport

Microstructure evidence may reach Session/4H/8H only when measured persistence and state transport support it. V2 must not allow a high-frequency feature to affect long horizons merely because it exists.

### I. Model competition and complexity control

Every advanced module competes against simpler alternatives. MDL/BIC/Bayesian evidence or equivalent complexity controls should favor deletion when extra structure does not add reproducible information.

## 3. Data truth hierarchy

`REAL_LIVE_MBO` and `REAL_HISTORICAL_MBO` may support order-lifecycle research when identity/sequence integrity is proven.

`REAL_L2_DEPTH` may support aggregate depth research but never exact queue/order survival.

`REAL_TRADES_QUOTES` may support trade/quote response research but cannot reconstruct missing order identity.

`REAL_CROSS_MARKET` may support causal cross-market tests only with point-in-time availability.

`PROXY_RESEARCH` and `SYNTHETIC_TEST` cannot become predictive-validation evidence.

## 4. Fail-closed statuses

V2 modules must be able to return:

- `OBSERVED`
- `DEGRADED`
- `NOT_IDENTIFIABLE`
- `INSUFFICIENT_DATA`
- `PROTOCOL_INELIGIBLE`
- `UNCALIBRATED`

Unknown is not zero. Missing is not neutral. Censored is not survived forever.

## 5. Validation hierarchy

1. software/unit/adversarial tests;
2. causal historical debugging on designated training/calibration data;
3. untouched historical diagnostic slice if legitimately available;
4. zero-alpha prospective pilot;
5. frozen candidate, protocol and sample-size rule;
6. paired prospective BASE_FIA vs FIA+UMSE_V1 vs FIA+UMSE_V1+V2 on the same unseen observations;
7. promote only if preregistered incremental criteria are met.

Engineering correctness cannot promote the model.

## 6. Frozen safety flags during build

`SUCCESSOR_CAMPAIGN_STARTED = false`

`ALPHA_SPENT = 0`

`PREDICTIVE_EDGE = NOT_PROVEN`

`FORWARD_OOS_EVIDENCE = NOT_PROVEN`

`PRODUCTION_INTEGRATION = false`
