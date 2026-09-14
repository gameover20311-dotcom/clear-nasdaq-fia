# CNMI Shadow Integration — Non-Authoritative Adapter

## Purpose

This repository branch contains a **shadow-only executable adapter** derived from the frozen CNMI Research Admission Governance Framework.

Adapter identity:

`CNMI_SHADOW_ADAPTER_V1_NONAUTHORITATIVE`

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

## What the adapter does

`backend/fia/cnmi_shadow.py` implements a deterministic, fail-closed governance check for:

1. requested admission level (`RESEARCH`, `CORE`, `PRODUCTION`)
2. the nine CNMI hard non-compensable gates
3. typed scientific claims
4. research/core/production admission requirements
5. provenance completeness states
6. untouched-confirmation constraints
7. materiality identity completeness/contamination checks
8. confirmatory-vs-point-estimate Pareto distinction
9. deterministic candidate/result digests

A positive empirical metric can never offset a failed applicable hard gate.

## Protected-system invariants

The adapter is deliberately isolated from the prediction path:

- `PRODUCTION_INFLUENCE = false`
- `DEPLOYMENT_AUTHORIZED = false`
- `PREDICTIVE_EDGE_CLAIMED = false`
- BASE_FIA forecast logic is not imported or modified
- Forward-OOS is not imported or modified
- DPCSE/MFRE/UMSE/Shadow Lab are not imported or modified
- no frozen evidence, seal, ledger, or scientific identity is rewritten

The adapter may judge governance records supplied to it. It cannot alter forecast probabilities, direction, confidence, historical evidence, seals, or deployment state.

## Why this is a separate adapter

The frozen CNMI package explicitly stopped at a research-governance freeze and did not itself authorize implementation/integration. The user subsequently requested a project integration. To preserve provenance honesty, the executable object is therefore named and versioned separately instead of silently relabeling the frozen CNMI artifact as executable CNMI.

## Verification

`backend/tests/test_cnmi_shadow.py` attacks the main invariants, including:

- hard-gate non-compensation
- missing-gate fail-closed behavior
- research/core/production separation
- prospective-evidence requirement
- deliberate provenance destruction precedence
- recoverable-but-missing provenance
- latent prior exposure and untouched-confirmation failure
- point-estimate Pareto overclaim
- missing/contaminated materiality identity
- unknown claim types
- no automatic deployment authorization
- deterministic output identity

GitHub Actions workflow `.github/workflows/cnmi-shadow-verify.yml` executes the shadow regression suite and Python compilation on the integration branch and on relevant pull requests.

## Promotion rule

Passing this adapter's tests means only that the adapter satisfies its declared executable contract. It does **not** establish:

- market edge
- predictive improvement
- CNMI universal validity
- production admission for any candidate
- deployment authorization

Any future production-affecting use requires a separate protocol, prospective evidence, applicable CNMI production gates, and explicit deployment authorization.
