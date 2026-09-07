# V5 Threat Model

Protected invariants: BASE_FIA and sealed Forward-OOS remain untouched; LLM evidence comes from one atomic dashboard snapshot; provider-health is gate-only metadata; inference stays localhost-only; failures are fail-closed; HOLDOUT code/cases are sealed; outputs are first-write and hash-bound; outcomes are separate and immutable.

Threats include prompt injection, stale/missing data, model hallucination, correlated evidence, overconfidence, non-atomic state joins, concurrent writes, ledger truncation/edit, JSON non-finite values, SSRF/remote endpoint substitution, benchmark leakage/cherry-picking, HOLDOUT reruns, teacher-reference contamination, outcome backfill and deliberate deletion of local audit history.

No software can honestly guarantee zero unknown bugs forever. V5 targets zero known critical/high defects after reproducible red-team testing. For externally credible benchmark claims, seal hashes must also be recorded outside the mutable project directory.
