# CLOUD AI — UMSE MASTER FINAL HOSTILE AUDIT PROMPT

Audit only. **Do not modify the repository in the first pass.**

Target branch: `research/umse-master-v1`

Treat `UMSE_MASTER_BUILD_MANIFEST.json` as a claim to verify, not as truth. Independently inspect every scientific and code path under `research/umse_master/` and compare the branch against production `main`.

Your objective is to find genuine defects, overclaims, leakage, mathematical mistakes, non-identifiability, vacuous tests, accidental production coupling and research designs that cannot survive real data—not to force PASS.

Required audit areas:

- future leakage and event/availability timestamp semantics
- stale/missing/proxy/synthetic fail-closed behavior
- L2 versus true MBO and queue/order-identity semantics
- liquidity field, gradients, curvature, credibility and resilience mathematics
- impact model, response surprise and “failed response” logic
- Hawkes orientation, integrated kernels, spectral radius and stability
- criticality construction and arbitrary-normalization risk
- transfer entropy / CMI / PID estimator bias and sample instability
- Shapley marginal information and double counting
- KL/JS/Wasserstein implementation and silent-regime claims
- path irreversibility
- latent agent/inventory inference and identifiability
- mechanism competition and state normalization
- HMM/filter assumptions
- survival/hazard/metastability
- cross-scale half-life and 4H/8H propagation gates
- MST formula redundancy/sensitivity
- reliability fusion and correlated-expert handling
- Brier/calibration/bootstrap/fixed-N validation logic
- replay contamination and prospective-proof labeling
- research MODEL/PROTOCOL/INFRA identities and fail-closed classification
- test quality, mutation risk, vacuous assertions and uncovered boundary cases
- proof that production BASE_FIA is untouched

Classify each finding as:

`GENUINE_BUG`, `SCIENTIFIC_RISK`, `NON_IDENTIFIABLE`, `SPECULATIVE_BUT_CONTAINED`, `TEST_GAP`, `DOCUMENTATION_OVERCLAIM`, or `NO_ISSUE`.

For every genuine finding provide file/line evidence, why it matters, and the smallest scientifically correct repair. Do not propose cosmetic expansion.

Finish with separate verdicts:

- `ENGINEERING_CORRECTNESS = PASS/FAIL`
- `SCIENTIFIC_IDENTIFIABILITY = PASS/CONDITIONAL/FAIL`
- `DATA_READINESS = READY/CONDITIONAL/NOT_READY`
- `HISTORICAL_DIAGNOSTIC_VALUE = READY/CONDITIONAL/NOT_READY`
- `FORWARD_OOS_EVIDENCE = PROVEN/NOT_PROVEN`
- `PRODUCTION_PROMOTION_ELIGIBILITY = YES/NO`

Do not convert engineering correctness into an edge claim. Current edge status must remain `NOT_PROVEN` unless genuine unseen evidence exists.

Stop after the audit report. Do not repair until the owner explicitly authorizes the repair pass.
