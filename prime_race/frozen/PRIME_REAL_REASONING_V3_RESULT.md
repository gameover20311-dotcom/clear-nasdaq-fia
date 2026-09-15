# PRIME REAL REASONING V3 — FROZEN RESULT

Status: DEVELOPMENT EVIDENCE ONLY
Promotion decision: DO_NOT_PROMOTE
External opponent promotion: BLOCKED

## Identity

- Branch: `prime-real-reasoning-repair-v2`
- Evaluated commit: `6b94221184b40a8c76846c675154091375b3dbdb`
- Workflow run: `35012118630`
- Artifact: `prime-real-reasoning-v3-evidence`
- Artifact digest: `sha256:37b049501d9745aa2082ca9a5721dfa4c879a3778bed33ffe80e74d0a06e81a2`
- Policy: `PRIME_REAL_REASONING_V3`
- Model: `HuggingFaceTB/SmolLM2-360M-Instruct`
- Taskset: `PRIME_V3_UNSEEN_26091521_105`
- Task count: 105
- Taskset SHA-256: `57f804594569815880f387883d92d0bd0b43f9ce46316e4b3babba55ba5bba07`
- Answer-key SHA-256: `2367f10baecb19746d6daac13f7cbd82b0bdbd9c17fa9848c14c138aaab83306`
- Locked-output SHA-256: `e8d50b4331eb0710b348313da44a3d54f63afd98a6147e0ef166b0fe9783e748`
- Result bundle SHA-256: `95817697a259207c82c5dc5811b3843d6a98a34ef7968424907a6a03aaf80159`
- API cost: $0
- BASE calls: 420
- NEW calls: 420
- Legacy deterministic-verifier coverage: 0 / 105
- Lane A deterministic answer override: false

## Unseen scores

- Frozen BASE final: 18 / 105 = 17.1429%
- NEW Draft only: 23 / 105 = 21.9048%
- NEW Attack A: 24 / 105 = 22.8571%
- NEW Attack B: 25 / 105 = 23.8095%
- NEW Draft + Attack A + Attack B aggregate: 24 / 105 = 22.8571%
- NEW full AI pipeline after Final Judge: 20 / 105 = 19.0476%
- Hybrid system: 20 / 105 = 19.0476%

Hybrid equals AI-only because the legacy verifier covered 0 / 105 tasks.

## Paired BASE vs NEW full AI pipeline

- NEW wins: 6
- BASE wins: 4
- Ties: 95
- Discordant pairs: 10
- Exact two-sided paired p-value: 0.75390625

The numeric +2 correct answers is weak evidence and does not establish a reliable reasoning improvement.

## Marginal-stage evidence

- Attack A agreements with Draft: 99
- Attack A disagreements: 6
- Attack A rescues: 2
- Attack A harms: 1
- Attack B unique rescues: 9
- Attack B unique harms: 8
- Final Judge rescues: 3
- Final Judge harms: 7

Total measured rescue events = 14; total measured harm events = 16. The required positive marginal architecture value was not established.

The Final Judge is the clearest current regression: the three-stage aggregate scored 24/105, while the full pipeline after the Judge scored 20/105.

## Confidence result

Raw model stages still emitted confidence 50 throughout the benchmark. The V3 structural confidence protocol created non-zero final variance, but calibration was not repaired:

- BASE Brier: 0.25
- NEW full AI Brier: 0.338716
- NEW confidence mean: 61.886
- NEW confidence variance: 71.606
- Accuracy in confidence 40-59 bucket: 10.0% (30 tasks)
- Accuracy in confidence 60-79 bucket: 22.67% (75 tasks)

Therefore `CONFIDENCE_CALIBRATION_REPAIRED = NOT_PROVEN` and the V3 confidence layer is materially overconfident relative to observed accuracy.

## Strongest capability gaps on this benchmark

NEW full AI pipeline accuracy by selected families:

- adversarial wording: 0 / 7
- ambiguous evidence: 0 / 7
- evidence independence: 0 / 7
- implication/negation: 0 / 7
- future leakage: 1 / 7
- formal logic: 1 / 7
- provenance identity: 1 / 7
- causal reasoning: 1 / 7
- arithmetic word reasoning: 4 / 7
- missing information: 4 / 7

These are development diagnostics, not labels to memorize. This taskset is now burned as development evidence and cannot be reused as final promotion proof after further repairs.

## Promotion checks frozen before execution

Passed:
- task_count_at_least_100
- ai_reasoning_new_strictly_better numerically
- paired_new_wins_exceed_base_wins
- confidence_non_degenerate
- no_high_confidence_wrong under the predeclared >=90 definition
- equal_inference_calls
- verifier_not_used_in_reasoning_lane
- legacy_verifier_coverage_not_full

Failed:
- paired_exact_p_le_0_05
- attack_or_judge_positive_marginal_value

The run therefore returns `DO_NOT_PROMOTE` under its own frozen gate.

Separate hostile review also finds confidence calibration inadequate; this does not change the frozen scoring rule after the outcome, but it is a required repair for any future candidate gate.

## What is actually proven

1. The 105-task unseen run executed successfully with equal 420-vs-420 call budgets.
2. Lane A did not use deterministic answer replacement.
3. The legacy verifier did not cover these tasks.
4. NEW full AI scored 20/105 versus frozen BASE 18/105 on this taskset.
5. The paired difference is not statistically persuasive.
6. Attack/Judge marginal value is not positive overall under the recorded rescue/harm accounting.
7. Final Judge currently damages performance relative to the three-stage aggregate.
8. Confidence calibration is not repaired.

## What is not proven

- NEW_PRIME_REASONING > BASE_PRIME_REASONING as a reliable transferable claim
- Attack A useful marginal value beyond weak task-specific evidence
- Attack B useful marginal value beyond weak task-specific evidence
- Final Judge improvement
- confidence calibration repair
- readiness for the next external opponent
- superiority over any external model

## Decision

`PROMOTION_DECISION = DO_NOT_PROMOTE`

`NEXT_OPPONENT = NONE`

Stop at this checkpoint. Any further repair must use these results only for general failure diagnosis and must require a brand-new unseen holdout for the next promotion claim.
