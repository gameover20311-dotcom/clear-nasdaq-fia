# UMSE MASTER — A-to-Z Theory Coverage Map

**Research source freeze:** `06b7ada5472a030378144fca55f5aa41482ae7bb`

This map records how the full UMSE discussion is represented in the research package. “Implemented” means an executable scientific contract, diagnostic or research primitive exists. It does **not** mean predictive edge has been established.

| Theory / mechanism | Implementation | Status | What it may claim now | What is still required |
|---|---|---|---|---|
| Causal event kernel | `events.py`, `contracts.py` | IMPLEMENTED_CONTRACT | timestamp/provenance eligibility and fail-closed causal slicing | real feed conformance |
| Data class truth | `contracts.py`, `adapters.py` | IMPLEMENTED_CONTRACT | L2/MBO/proxy/synthetic separation | vendor-specific adapters |
| Liquidity field L(p,t) | `liquidity.py` | IMPLEMENTED_DESCRIPTIVE | depth, weighted depth, gradient, curvature, thinness, replenish/cancel pressure | real MBO/L2 calibration |
| Queue survival / credibility | `events.py`, `liquidity.py` | NEEDS_REAL_MBO | exact queue metrics are blocked unless true order identity exists | genuine CME MBO |
| Aggression / urgency | `primitives.py`, `agents.py` | IMPLEMENTED_DESCRIPTIVE | causal imbalance and latent-pressure hypotheses | calibration/OOS |
| Cancellation / replenishment / sweeps / large trades | `events.py`, `primitives.py` | IMPLEMENTED_DESCRIPTIVE | causal event summaries | real event feed |
| Flow toxicity / adverse selection | `impact.py`, `hypotheses.py` | PLAUSIBLE_BUT_UNPROVEN | response-surprise research primitive | empirical calibration/OOS |
| Nonlinear impact ΔP=g(Q,L,V,R) | `impact.py` | IMPLEMENTED_RESEARCH_MODEL | explicit uncalibrated candidate impact function | fit/freeze on training data |
| Response surprise ε | `impact.py` | IMPLEMENTED_DESCRIPTIVE | observed minus expected response diagnostic | calibrated expectation model |
| “What failed to happen?” | `impact.py` | IMPLEMENTED_DESCRIPTIVE | failed-response score | unseen validation |
| Impact decay / recovery | `impact.py` | IMPLEMENTED_DESCRIPTIVE | half-life/recovery diagnostics | robust sampling |
| Hawkes event network | `hawkes.py` | IMPLEMENTED_RESEARCH_MODEL | exponential self/cross-excitation diagnostics | fit/stability/calibration on real events |
| Hawkes spectral radius | `hawkes.py`, `criticality.py` | PLAUSIBLE_BUT_UNPROVEN | candidate criticality component only | control for volatility/liquidity and OOS test |
| Critical transition index | `criticality.py` | IMPLEMENTED_CANDIDATE | combines rho, ACF, variance, recovery, elasticity as research index | statistical calibration; formula may be rejected |
| Dynamic information graph | `information.py` | IMPLEMENTED_PRIMITIVES | MI/CMI/TE edge diagnostics | sufficient samples, bias correction, robustness |
| Transfer entropy | `information.py` | IMPLEMENTED_PRIMITIVE | empirical TE calculation | significance/permutation and sample control |
| PID redundancy/synergy | `information.py` | HEURISTIC_IMPLEMENTED | I_MIN-style approximation only, explicitly not full PID | robust estimator / enough data |
| Shapley marginal information | `marginal_info.py` | IMPLEMENTED_RESEARCH_DIAGNOSTIC | exact empirical MI Shapley for small frozen feature sets | unseen stability, multiplicity control |
| Avoid evidence double counting | `fusion.py`, `information.py`, `marginal_info.py` | IMPLEMENTED_CONTRACT_AND_DIAGNOSTICS | redundancy-group discount + conditional information tools | learned reliability/calibration |
| Information geometry | `geometry.py` | IMPLEMENTED_DESCRIPTIVE | KL/JS/Wasserstein distribution-shift diagnostics | binning/estimator robustness |
| Path irreversibility / entropy | `irreversibility.py` | IMPLEMENTED_DESCRIPTIVE | forward/reverse transition asymmetry | regime-specific empirical validation |
| Latent agent urgency/inventory pressure | `agents.py` | IMPLEMENTED_HYPOTHESIS | latent pressure scores; never direct trader identity | real-data identifiability |
| Agent-mixture / mechanism competition | `mechanisms.py` | IMPLEMENTED_UNCALIBRATED | normalized hypothesis competition | calibration and falsification |
| Informed buy/sell | `mechanisms.py` | IMPLEMENTED_HYPOTHESIS | candidate mechanism weights | unseen evidence |
| Short covering / long liquidation | `mechanisms.py` | IMPLEMENTED_HYPOTHESIS | candidate mechanism weights | external/context evidence + OOS |
| Passive accumulation/distribution | `mechanisms.py` | IMPLEMENTED_HYPOTHESIS | candidate mechanism weights | real depth/MBO + OOS |
| Liquidity vacuum / absorption / noise | `mechanisms.py` | IMPLEMENTED_HYPOTHESIS | candidate mechanism weights | calibration/OOS |
| Market-state competition | `state.py` | IMPLEMENTED_UNCALIBRATED | state probability-like research weights | calibrated state model |
| Balanced Auction etc. | `contracts.py`, `state.py` | IMPLEMENTED_STATE_SET | explicit ten-state taxonomy | identifiability testing |
| Bayesian HMM/state space | `state_space.py` | IMPLEMENTED_CONTRACT | forward filter with supplied parameters | learned/frozen parameters from training data |
| Survival / hazard / metastability | `survival.py` | IMPLEMENTED_DESCRIPTIVE | KM/hazard/state-survival diagnostics | real state-duration samples |
| Cross-scale Micro→Meso→Session→4H→8H | `cross_scale.py` | IMPLEMENTED_GATE | micro signal blocked from long horizon unless survival gate passes | calibrated half-life/thresholds |
| Information velocity / half-life | `cross_scale.py`, `impact.py` | IMPLEMENTED_DESCRIPTIVE | candidate persistence and survival estimates | real multi-scale data |
| Fragility / susceptibility / resilience | `liquidity.py`, `criticality.py` | IMPLEMENTED_DESCRIPTIVE | liquidity/response proxies | calibration and factor deconfounding |
| Causal decontamination | `contracts.py`, `events.py`, `replay.py` | IMPLEMENTED_PROTOCOL | future availability/event time rejected; replay causal | vendor timestamp verification |
| Mechanistic expert fusion | `fusion.py` | IMPLEMENTED_UNCALIBRATED | reliability/data-quality pooling and redundancy discount | reliabilities learned only on proper training data |
| MST — Market State Tension | `mst.py` | SPECULATIVE_EXECUTABLE | original conceptual formula and stable alternative can be compared | must prove non-redundancy/OOS value or be killed |
| Complexity / MDL pressure | `complexity.py` | IMPLEMENTED_PROTOCOL_TOOL | BIC/bit penalty and sample/parameter warning | applied during real model selection |
| Self-falsifying hypothesis registry | `hypotheses.py` | IMPLEMENTED_PROTOCOL | explicit required data/falsification/promotion rules | execute against real data |
| Inverse game / IRL | `hypotheses.py` | SPECULATIVE_REGISTERED | nothing predictive | identifiability first; kill if unstable |
| Free energy / predictive coding | `hypotheses.py` | SPECULATIVE_REGISTERED | nothing predictive | prove it adds beyond response surprise |
| Topological state features | `hypotheses.py` | SPECULATIVE_REGISTERED | nothing predictive | large stable trajectory sample, multiplicity control |
| Historical replay | `replay.py` | IMPLEMENTED_PROTOCOL | causal diagnostic/calibration/untouched-test classes | actual historical data |
| Forward-OOS | `validation.py` + existing CLEAR NASDAQ protocol boundary | IMPLEMENTED_VALIDATION_PRIMITIVES | paired Brier, ECE, fixed-N gate | genuine future observations and preregistered campaign |
| BASE vs FIA+UMSE | `validation.py` | IMPLEMENTED_PROTOCOL_TOOL | same-sample paired evaluation | frozen candidate + unseen observations |
| 4H / 8H separation | `contracts.py`, `shadow_engine.py` | IMPLEMENTED_CONTRACT | distinct horizon estimates | predictive mapping/calibration |
| NO_UMSE_EDGE | `shadow_engine.py`, `pipeline.py` | IMPLEMENTED_FAIL_CLOSED | current system correctly refuses predictive edge | stays until edge is earned |
| MODEL/PROTOCOL/INFRA identities | `research_identity.py`, `spec/umse_identity_classification_v1.json` | IMPLEMENTED_FAIL_CLOSED | complete deterministic research fingerprints | re-freeze if prediction-relevant source changes |
| Full shadow orchestration | `pipeline.py` | IMPLEMENTED_RESEARCH_PIPELINE | causal research diagnostics, evidence hash, no production effect | real adapters/calibration/predictive freeze |

## Theory-completeness rule

All major concepts from the UMSE MASTER discussion now have one of three explicit homes:

1. an executable causal/descriptive/research implementation;
2. an executable validation/protocol boundary; or
3. an explicit speculative hypothesis with a kill rule.

No concept is promoted merely because mathematics or code exists. The decisive question remains:

`I(UMSE_t ; Y_future | FIA_t) > 0 ?`

Until unseen evidence answers that positively, `PREDICTIVE_EDGE = NOT_PROVEN`.
