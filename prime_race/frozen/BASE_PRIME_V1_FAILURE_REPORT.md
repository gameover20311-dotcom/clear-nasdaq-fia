# BASE_PRIME V1 — 8-Task Failure Autopsy

Freeze: `BASE_PRIME_V1_20260915`

Clean result: Prime `1/8`, matched plain `0/8`, `32` calls each. Architecture advantage remains `NOT_PROVEN`.

Harness note: the earlier permissive parser defect is a `HARNESS_ERROR`, not a Prime reasoning failure. It was repaired before this clean baseline and is excluded from Prime defect counts.

| Task | Category | Expected | Prime final | Result | Failure class | Why it happened | Stage failure | Why later stage did not catch it | General repair | Regression test |
|---|---|---:|---:|---|---|---|---|---|---|---|
| ZB3-024-9ab5fd0b60 | CAUSAL_CONFOUNDING | C | C | PASS | SEMANTIC_REASONING warning | Draft/Attack A/Attack B all initially favored B despite text describing unresolved confounding; final judge recovered C. | Draft + both attackers | Attackers copied the same flawed causal story instead of independently checking identification assumptions. | Add independent causal-boundary check and require attackers to test confounding/randomization/adjustment explicitly. | Fresh observational cases with shuffled labels and varied confounder wording. |
| ZB3-026-faa53124c9 | EVIDENCE_INDEPENDENCE | B | C | FAIL | EVIDENCE_DEPENDENCE + ATTACKER_COLLAPSE + JUDGE_DEPENDENCE | Prime treated repeated same-lineage judgments as independent confirmation. | Draft, Attack A, Attack B, Judge | Every stage converged on the same unsupported independence assumption. | Add a dependence doctrine check: same lineage/evidence cannot establish independence; final adjudicator must be allowed to reject unanimous stages. | Fresh same-provider/same-lineage/duplicated-source cases with answer positions randomized. |
| ZB3-019-c4e3002020 | EXACT_ARITHMETIC | D | C | FAIL | ARITHMETIC + ATTACKER_COLLAPSE + JUDGE_DEPENDENCE | Model computed 19×7+13−2 as 145 instead of 144. | All model stages | No deterministic recomputation existed; all stages inherited/repeated the arithmetic error. | Add safe deterministic arithmetic verifier before adjudication. | Runtime-generated integer expressions using +,-,×, parentheses and exact precedence. |
| ZB3-014-a57b56e916 | FORMAL_LOGIC | D | B | FAIL | FORMAL_LOGIC + JUDGE_DEPENDENCE | P=true,Q=false implication was classified true. | Draft wrong; attackers moved to B but B still wrong; Judge accepted B. | No truth-table verification existed. | Add deterministic boolean/implication verifier. | Fresh truth assignments for implication, conjunction, disjunction, negation and equivalence. |
| ZB3-031-cc0e4641b1 | FUTURE_LEAKAGE | A | B | FAIL | FUTURE_LEAKAGE + ATTACKER_COLLAPSE + JUDGE_DEPENDENCE | Model accepted a feature first available after the claimed prediction time because it was predictive. | All stages | Stages optimized for predictive value instead of temporal availability. | Add decision-time availability invariant: evidence first available after lock time invalidates prospective status. | Fresh t_prediction/t_available cases with shuffled option labels and both valid/invalid orderings. |
| ZB3-005-8e9b384138 | PROMOTION_GATE | D | C | FAIL | SEMANTIC_REASONING + TEMPORAL_INTEGRITY + ATTACKER_COLLAPSE | Prime chose historical backfill even though prospective-row threshold was unmet. | All stages | No hard gate distinguished prospective evidence from backfilled historical evidence. | Add fail-closed promotion gate verifier: unmet prospective threshold cannot be backfilled into prospective proof. | Fresh required/observed row counts and randomized distractors. |
| ZB3-028-e55d18bd92 | PROVENANCE | D | C | FAIL | PROVENANCE + ATTACKER_COLLAPSE + JUDGE_DEPENDENCE | Prime failed to recognize two different SHA-256 values for claimed identical bytes as a provenance contradiction. | Draft/Attack A wrong; Attack B/Final moved to C, still wrong. | Stages changed labels without checking cryptographic identity invariant. | Add artifact-identity verifier: same exact bytes cannot have two different SHA-256 hashes absent transformation/version change. | Fresh artifact/hash mismatch cases with and without documented transformation. |
| ZB3-009-9daaf60238 | TEMPORAL_INTEGRITY | A | C | FAIL | TEMPORAL_INTEGRITY + ATTACKER_COLLAPSE + JUDGE_DEPENDENCE | Prime allowed editing a cryptographically locked forecast after outcome observation while preserving prospective label. | Draft/Attack A/Attack B wrong; Judge changed to C but still wrong. | Judge was influenced by prior wrong conclusions and did not independently enforce immutability. | Make final judge solve original task independently; add lock immutability verifier. | Fresh lock/outcome/edit cases with randomized timestamps and labels. |

## Cross-cutting root causes

1. `ATTACKER_COLLAPSE`: Attack stages frequently repeated the draft rather than using genuinely different reasoning paths.
2. `JUDGE_DEPENDENCE`: Final judge consumed prior conclusions before independently solving the original problem and could inherit consensus errors.
3. `NO_DETERMINISTIC_SAFETY_NET`: Exact arithmetic and formal logic were left entirely to a weak language model.
4. `INTEGRITY_RULES_NOT_ENFORCED`: Temporal availability, provenance, dependence and promotion constraints were suggestions in prompts rather than executable invariants.
5. `CONFIDENCE_CALIBRATION_FAILURE`: all submitted answers used confidence 50; confidence carried no evidential information.
6. `EXTRA_CALLS_LOW_VALUE`: four calls produced only 1/8 versus 0/8 on the clean development challenge.

## Harness defect — separated from Prime

`PARSING`: the first battle runner had a permissive fallback that could treat an arbitrary standalone A/B/C/D in generated prose as the answer. That result was invalidated. The current baseline uses `STRICT_EXPLICIT_OR_LEADING_V2`, which accepts explicit/leading answer declarations and rejects arbitrary prose. This defect is not charged against Prime.
