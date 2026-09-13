# ASTRA MAX — Independent Forensic Audit of UMSE V2 FINAL

Your first pass is **forensic and read-only**. Do not repair, redesign or
improve anything. Do not open a pull request. Return findings first.

## Do not inherit Cloud's conclusions

Cloud AI audited this build, repaired it, re-audited it and froze it. Treat
every Cloud statement as an unverified claim, including the closure states in
`UMSE_V2_FINAL_CLOUD_CLOSEOUT.md`. Cloud has already been wrong twice in ways
worth knowing about:

* Cloud's first audit asserted that a `max(0.0, ...)` clamp hid negative
  fluctuations in a conditional mutual information estimator. That was false.
  Plug-in CMI is non-negative by construction.
* Cloud's first repair pass reported an 18/18 mutation score that was an
  artefact of a test failing in every run, masking a true score of 11/18.

Assume there is a third error you have not been told about.

## Target

| Item | Value |
|---|---|
| Repository | `gameover20311-dotcom/clear-nasdaq-fia` |
| Branch | `research/umse-master-v2-full` |
| Final source checkpoint | `c10c6cb0f54af21395702608e0b1e82bce2b19a8` |
| Production base that must remain untouched | `1ab93b09d22b77e2bdce99fcfc1418395cbdf78d` |
| Claimed MODEL | `75d214345e52a6a255d55a1edecadd0338376295b63fbb2bc29c54ed5a98a61d` |
| Claimed PROTOCOL | `8d4c55f746bffd0929937903fcb57da0e2541199e2b3efc9b8248bd7fe88c8ff` |
| Claimed INFRASTRUCTURE | `70a93eecf7f36c227f6715e3059a0f12e944fcfba77b7f6236f5cd29e88a3b75` |
| Claimed classification hash | `7de6809074cf39441e7c8cd606e2e6864c0bd0ecb1daf29f5f9852f2190999e4` |

## What you must independently establish

1. **Identities.** Recompute all four from git blobs at the checkpoint without
   executing the branch's own identity code. Challenge scope completeness,
   self-inclusion, nested directories, and whether the classification hash can
   be changed without changing a digest.
2. **Production isolation.** Prove it from tree hashes and diffs, not from CI
   output. Attack symlinks, path tricks, generated files, workflow triggers and
   packaging side effects. Verify a backend-only commit cannot escape CI.
3. **MBO semantics.** Attack order identity, sequence resets, reused ranges,
   multi-channel domains, partial fills, modify semantics and queue-position
   claims. A negative lifetime must never become a clean zero-second OBSERVED
   survival point. Left truncation must never manufacture a short lifetime.
4. **Causal timing.** Attempt to inject future information through every
   timestamp field, decision time, outcome time and horizon resolution.
5. **All statistics, re-derived.** Kaplan-Meier, RMST and its tau, the block
   bootstrap, the one-sided alpha tail, Brier differences, permutation nulls,
   the BIC penalty and the cross-scale survival law. Do not accept a stored
   number; derive it.
6. **All 18 original mutation classes.** Run them yourself from a baseline you
   have verified green. Do not substitute easier mutations. Report X/18 and
   name every survivor.
7. **Incremental information.** Attack `I(UMSE;Y_future|FIA)` with independent
   noise, conditional confounding, sparse strata, high-cardinality conditioning,
   repeated feature search and multiple testing. A significant screen must
   remain UNCALIBRATED and non-promotional.
8. **Redundancy.** Try to show each layer is redundant with simpler statistics
   FIA already has. Recommend deletion where a module cannot demonstrate an
   independently testable reason to exist. Do not keep a module because it is
   sophisticated.
9. **Forward-OOS protocol.** Attack fixed-N, preregistration timing, fingerprint
   matching, evidence-hash uniqueness, duplicate forecasts, horizon separation,
   outcome timing bounds, optional stopping, alpha reuse and block-size versus
   forecast overlap.
10. **Real-data readiness.** Judge what would break on a live CME feed.

## Findings format

Classify each finding as exactly one of: `CRITICAL_GENUINE_BUG`,
`HIGH_GENUINE_BUG`, `MEDIUM_GENUINE_BUG`, `LOW_GENUINE_BUG`,
`SCIENTIFIC_IDENTIFIABILITY_LIMIT`, `DATA_READINESS_GAP`, `TEST_GAP`,
`REDUNDANT_COMPLEXITY`, `DOCUMENTATION_OR_CLAIM_ISSUE`,
`ALREADY_DEFENDED_CORRECTLY`.

For every genuine defect give the exact location, why it is wrong, a concrete
adversarial example you actually ran, the scientific consequence, the smallest
defensible repair and the regression test that would catch it.

## Boundaries you may not move

```
SUCCESSOR_CAMPAIGN_STARTED = false
ALPHA_SPENT = 0
PREDICTIVE_EDGE = NOT_PROVEN
PRODUCTION_INTEGRATION = false
PREDICTIVE_MAPPING_FROZEN = false
REAL_MBO_CALIBRATION = NOT_DONE
FORWARD_OOS_EDGE = NOT_PROVEN
```

A green CI run proves engineering contracts only. Synthetic tests are never
market evidence. Do not merge to production, start a successor campaign, spend
alpha, or freeze a predictive mapping.

Stop after the findings report.
