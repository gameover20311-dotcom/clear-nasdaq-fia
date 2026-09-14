# CNMI Shadow Integration — Non-Authoritative Adapter

## Purpose

This repository contains a **project-level shadow-only executable adapter** derived from the frozen CNMI Research Admission Governance Framework.

Adapter identity:

`CNMI_SHADOW_ADAPTER_V1_1_NONAUTHORITATIVE`

This is **not** a rewrite of the frozen CNMI package and does not claim that the frozen CNMI package itself authorized implementation or integration.

## Frozen-source boundary

The frozen CNMI handoff remains authoritative for CNMI itself:

- framework scope: `RESEARCH_GOVERNANCE_ONLY`
- `CNMI_NATIVE_105_34_10 = NOT_CLAIMED`
- MFRE 105/34/10 material is external provenance only
- counterexample record: 41/41 frozen governance regressions
- no predictive-edge claim
- no deployment authorization

The final frozen package intentionally preserved protocol-specific limitations. This adapter therefore supplies **no universal**:

- materiality threshold
- statistical Pareto test
- meta-selection correction
- scalar utility/preference map

Those must be supplied and justified by the protocol being governed. Missing required protocol inputs fail closed.

## V1.1 hostile hardening

The V1 adapter could report `production_admissible=true` from caller-supplied booleans if the structural checklist was complete. That was too strong for a non-authoritative shadow adapter because the adapter does not independently verify external ledgers, market data, artifact hashes, runtime evidence, signatures, or evidence independence.

V1.1 closes that overclaim. It now separates:

- `production_structurally_eligible` — the supplied record satisfies the declared structural production checklist.
- `production_admissible` — **always false in this adapter until a trusted external production verifier is actually bound and executed**.

Therefore bare self-attestation can no longer become production proof. When structural eligibility is otherwise complete, the adapter emits `PRODUCTION:EXTERNAL_VERIFIER_NOT_BOUND` and `DEPENDENCE_NOT_EXCLUDABLE` instead of claiming admission.

Additional fail-closed repairs:

- PRODUCTION must declare and pass all H1–H9 hard gates; a caller cannot omit a gate from `applicable_hard_gates`.
- unknown claim types fail closed even if the candidate supplies its own truthy `explicit_evidence_rule`.
- `INCOMPLETE_KNOWN`, `HISTORICALLY_UNRECOVERABLE`, `RECOVERABLE_BUT_MISSING`, `DELIBERATELY_UNDOCUMENTED_OR_DESTROYED`, and `LATENT_PRIOR_EXPOSURE_NOT_EXCLUDABLE` all block structural production eligibility.
- duplicate/unknown applicable hard-gate declarations fail closed.

## What the adapter does

`research/cnmi_shadow/adapter.py` implements a deterministic, fail-closed governance check for:

1. requested admission level (`RESEARCH`, `CORE`, `PRODUCTION`)
2. the nine CNMI hard non-compensable gates
3. typed scientific claims
4. research/core requirements and production structural requirements
5. provenance completeness states
6. untouched-confirmation constraints
7. materiality identity completeness/contamination checks
8. confirmatory-vs-point-estimate Pareto distinction
9. deterministic candidate/result digests
10. explicit external-verifier boundary for production admission

A positive empirical metric can never offset a failed hard gate or the missing external-verifier boundary.

## Protected-system invariants

The adapter is deliberately outside the backend scientific fingerprint scope and isolated from the prediction path:

- `PRODUCTION_INFLUENCE = false`
- `DEPLOYMENT_AUTHORIZED = false`
- `PREDICTIVE_EDGE_CLAIMED = false`
- `EXTERNAL_PRODUCTION_VERIFIER_BOUND = false`
- BASE_FIA forecast logic is not imported or modified
- Forward-OOS is not imported or modified
- DPCSE/MFRE/UMSE/Shadow Lab are not imported or modified
- `backend/fia/identity_classification.json` is not modified
- MODEL / PROTOCOL / INFRASTRUCTURE scientific identity partition is not modified
- no frozen evidence, seal, ledger, or scientific identity is rewritten

The adapter may judge governance records supplied to it. It cannot alter forecast probabilities, direction, confidence, historical evidence, seals, or deployment state.

## Why this is a separate adapter

The frozen CNMI package explicitly stopped at a research-governance freeze and did not itself authorize implementation/integration. The user subsequently requested a project integration. To preserve provenance honesty, the executable object is therefore named and versioned separately instead of silently relabeling the frozen CNMI artifact as executable CNMI.

It lives under `research/cnmi_shadow/` rather than `backend/fia/` specifically so a research-governance adapter cannot silently enter or perturb the sealed backend scientific fingerprint scope.

## Verification

`research/cnmi_shadow/test_adapter.py` attacks the main invariants, including:

- all nine production hard gates are non-compensable
- omitted/duplicate/unknown production hard-gate declarations fail closed
- research/core/production separation
- prospective-evidence requirement
- all incomplete or unrecoverable provenance states block structural production eligibility
- latent prior exposure and untouched-confirmation failure
- point-estimate Pareto overclaim
- missing/contaminated materiality identity
- unknown claim types cannot self-register an evidence rule
- bare self-attestation never becomes production admission
- deterministic output identity

`research/cnmi_shadow/mutation_probe.py` deliberately mutates six critical fail-closed properties and requires every mutation to be killed.

`.github/scripts/production_isolation_gate.py` scans the declared production surfaces (`backend/main.py`, `backend/fia/**`, and `backend/fia_final_cockpit/**`, excluding tests) for direct imports, from-imports, literal dynamic imports, and config/string references to the known research/shadow packages. Its own hostile self-test injects direct, indirect, dynamic-import, and config-literal violations and requires detection before the repository scan can pass.

GitHub Actions workflow `.github/workflows/cnmi-shadow-verify.yml` runs on every branch when the governed or production-boundary paths change and executes compilation, hostile regression, mutation probes, verifier self-attacks, and the full production-surface isolation scan.

The repository's existing `FIA verify` workflow independently runs on all branches and pull requests and checks the original backend identities, protected artifacts, full regression suite, and working-tree mutation boundary.

## Promotion rule

Passing this adapter's tests means only that the adapter satisfies its declared executable contract. It does **not** establish:

- market edge
- predictive improvement
- CNMI universal validity
- production admission for any candidate
- deployment authorization
- independence of evidence sources

Any future production-affecting use requires a separately bound trusted verifier, prospective evidence, applicable CNMI production gates, and explicit deployment authorization.
