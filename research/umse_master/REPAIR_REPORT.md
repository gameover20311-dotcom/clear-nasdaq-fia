# UMSE MASTER — Authorised Repair Pass

Repairs every GENUINE_BUG and blocking TEST_GAP proven by the Cloud AI hostile
audit. SCIENTIFIC_RISK and NON_IDENTIFIABLE findings are either repaired
scientifically or failed closed and explicitly marked.

No production file was touched. `backend/` remains byte-identical to `main`.

## Scientific status (unchanged by this pass)

```
SUCCESSOR_CAMPAIGN_STARTED        = false
ALPHA_SPENT                       = 0
PREDICTIVE_EDGE                   = NOT_PROVEN
FORWARD_OOS_EVIDENCE              = NOT_PROVEN
PRODUCTION_PROMOTION_ELIGIBILITY  = NO
```

Nothing here is calibration and nothing here is evidence of edge. Several
repairs make the engine report LESS than it did before, because what it
reported before was not supportable.

## Method

For every repair: an adversarial regression test was written first, its failure
on the pre-repair implementation was demonstrated, the smallest scientifically
correct repair was applied, and the regression was re-run. 13 of 14 headline
requirements failed on the pre-repair code.

## The decisive repair

The manifest named `I(UMSE_t;Y_future|FIA_t) > 0` as the ultimate test. That
criterion was satisfied by pure independent noise in 100% of trials, because a
plug-in entropy estimator is positively biased and no reference distribution
existed.

`significance.py` (new, PROTOCOL) supplies a conditional permutation null. X is
permuted WITHIN each stratum of Z, which preserves p(x|z) and p(y|z) while
enforcing X ⟂ Y | Z — the standard conditional permutation test, and a
materially harder null than a wholesale shuffle. A minimum-samples-per-cell
floor refuses under-powered tables, and a resolution guard raises when the
permutation count cannot resolve the requested alpha.

A correction to the audit is recorded rather than quietly dropped: the audit
said the `max(0.0, ...)` clamp hid negative fluctuations. That was imprecise.
Plug-in CMI is the CMI of the empirical distribution and is non-negative by
construction; over 3000 random trials the unclamped estimator never fell below
-4.5e-16. The clamp absorbs floating point error only. The defect was the
missing null, not the clamp.

A second audit prediction was also disproved by testing: the clamp in
`shapley_information` was expected to break the Shapley efficiency axiom. It
does not — plug-in MI is monotone under feature addition, so the clamp never
binds and efficiency held exactly. The real Shapley defect is estimator bias
(six noise features reported 0.78 of a maximum 0.99 bits), now screened by
`shapley_information_evidence`.

## Repairs

| Finding | Repair | Identity |
|---|---|---|
| F-01 information null | conditional permutation test, sample floor, alpha-resolution guard | PROTOCOL (new `significance.py`), MODEL (`information.py`, `marginal_info.py`) |
| F-02 chronology | price path sorted by `event_time_utc`; causal filter untouched | MODEL |
| F-03 Hawkes stability | Collatz-Wielandt two-sided bounds on a shifted primitive matrix; `subcritical` only when the guaranteed upper bound < 1 | MODEL |
| F-04 liquidity elasticity | requires a genuine temporal liquidity change; returns None instead of dividing by a floor | MODEL |
| F-05 promotion gate | preregistered `ConfirmatoryPlan`, circular block bootstrap, effective-block floor, degeneracy detection | PROTOCOL |
| F-06 book shape | OLS slope and quadratic coefficient replace telescoping differences | MODEL |
| F-07 impact decay | OLS on log|x| over the whole path with R²; poor fit reports unidentifiable | MODEL |
| F-08 irreversibility | Dirichlet smoothing, bounded Jensen-Shannon primary statistic, adequate-sample requirement | MODEL |
| F-09 MST wiring | components Optional with a `sources` map; refuses redundant sources and missing components | MODEL |
| F-10 fail-open paths | criticality components Optional with explicit status; survival separates OBSERVED from NOT_IDENTIFIABLE | MODEL |
| F-11 Shapley bias | null-calibrated screen, sample adequacy reported | MODEL |
| F-12 fusion | weight-normalised log pool (weighted geometric mean) | MODEL |
| F-13 mechanisms | `directional_identification` replaces non-monotone `concentration`; explicit softmax temperature | MODEL |
| F-14 cross-scale gate | persistence-hint fallback removed; a MEASURED half-life is required | MODEL |
| F-15 impact units | marked `UNCALIBRATED_NOT_PROMOTION_ELIGIBLE`; `direction_consistent` no longer true for a zero move | MODEL |
| F-16 geometry | Dirichlet smoothing; Wasserstein returns None unless an ordered support is asserted | MODEL |
| F-17 agents | identifiability floor 0.25 → 0.0 | MODEL |
| F-19 test quality | 136 tests; 16 of 16 destructive mutations detected | tests (outside identity scope) |
| F-21 staleness | age derived from timestamps; optional `max_age_seconds` policy on every contract | PROTOCOL, MODEL |

## Deliberately NOT repaired

* **F-18 identity layout.** `cross_scale.py` is MODEL-classified but contains
  the 4H/8H PROTOCOL gate, and `research_identity.py` is excluded from its own
  fingerprint scope. Both are layout revisions, not defects in behaviour, and a
  repair pass is the wrong place to move identity boundaries. OPEN.
* **MST remains UNAVAILABLE in the pipeline.** The construct needs nine
  independent observables; the engine can supply five. Reporting UNAVAILABLE is
  the correct outcome, not a gap to paper over.
* **No calibration constant was invented.** `eta` in the impact model,
  `max_age_seconds`, and the confirmatory N all remain caller-supplied.
  `MIN_EFFECTIVE_BLOCKS` is a structural floor on the bootstrap, not a power
  calculation, and is necessary but nowhere near sufficient.

## What still requires real data

Nothing in this pass can substitute for real NQ MBO/depth/trade data. The
impact model stays uncalibrated, the Hawkes kernel stays unfitted, the HMM
parameters stay supplied rather than estimated, and no confirmatory N can be
derived until a forward pilot exists.
