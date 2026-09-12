# UMSE V2 — Final Cloud Closeout

Independent re-audit, repair, verification and freeze of UMSE MASTER V2 FULL.
Nothing in this document is evidence of market skill.

## Final checkpoint

| Item | Value |
|---|---|
| Branch | `research/umse-master-v2-full` |
| Final source checkpoint | `c10c6cb0f54af21395702608e0b1e82bce2b19a8` |
| Production base (untouched) | `1ab93b09d22b77e2bdce99fcfc1418395cbdf78d` |
| Tests | 79 pass, 0 fail |
| Original 18-mutation battery | **18 / 18 DETECTED** (verified baseline) |
| MODEL | `75d214345e52a6a255d55a1edecadd0338376295b63fbb2bc29c54ed5a98a61d` (7 files) |
| PROTOCOL | `8d4c55f746bffd0929937903fcb57da0e2541199e2b3efc9b8248bd7fe88c8ff` (8 files) |
| INFRASTRUCTURE | `70a93eecf7f36c227f6715e3059a0f12e944fcfba77b7f6236f5cd29e88a3b75` (2 files) |
| Classification manifest | `7de6809074cf39441e7c8cd606e2e6864c0bd0ecb1daf29f5f9852f2190999e4` |

Identities were recomputed independently from git blobs at the checkpoint,
without executing the branch's own identity code. 17 files, zero unclassified,
zero classified-but-absent.

## The mutation result the previous pass reported was wrong

The first repair pass reported 18/18. That number was an artefact. Its
workflow-isolation test read `.github/workflows/umse-v2-research.yml` through a
**working-directory-relative path**, so whenever the suite ran from anywhere but
the repository root it raised `FileNotFoundError`. The baseline was therefore
already red, every mutated run was also red, and every mutation counted as
"detected".

Re-run from a verified-green baseline, the repaired build scored **11/18**.
Seven scientifically material mutations survived:

| # | Destroyed behaviour | Class |
|---|---|---|
| 4 | Kaplan-Meier restricted mean survival time forced to zero | MODEL |
| 5 | Order-book half-life forced to a constant | MODEL |
| 6 | Resistance depth term removed | MODEL |
| 9 | Topological persistence entropy replaced | MODEL |
| 10 | Topological fragmentation index forced constant | MODEL |
| 12 | Information-velocity propagation rate forced constant | MODEL |
| 14 | Complexity BIC penalty removed | PROTOCOL |

All seven are now killed by pinned characterisation tests, and the suite result
is reproducible from three different working directories.

## Original 17 findings — closure

| ID | Finding | State |
|---|---|---|
| V2-01 | Time-inconsistent lineage reported OBSERVED | **CLOSED_BY_REPAIR** |
| V2-02 | Per-record age filter truncated lineages | **CLOSED_BY_REPAIR** |
| V2-03 | Two mechanisms structurally unreachable | **CLOSED_BY_REPAIR** (reachability); identifiability limit remains |
| V2-04 | Lead-lag fired on 100% of common-driver data | **CLOSED_BY_REPAIR** |
| V2-05 | Isolation proof gated by a `paths:` filter | **CLOSED_BY_REPAIR** |
| V2-06 | 13 of 18 mutations survived | **CLOSED_BY_REPAIR** (18/18, verified baseline) |
| V2-07 | Four Forward-OOS protocol gaps | **CLOSED_BY_REPAIR** |
| V2-08 | Republished snapshots manufactured memory | **CLOSED_BY_REPAIR** |
| V2-09 | RMST reported without a tau | **CLOSED_BY_REPAIR** |
| V2-10 | Resistance mixed sources and price scope | **CLOSED_BY_REPAIR** |
| V2-11 | Duplicate MBO packets corrupted fills | **CLOSED_BY_REPAIR** |
| V2-12 | Topology sample-size artefact, dropped duplicates | **CLOSED_BY_REPAIR** |
| V2-13 | No incremental-information test against FIA | **PARTIALLY_CLOSED** — screen exists and is well calibrated; no V2 feature has yet been run through it on real data |
| V2-14 | Counterfactual has no estimand or uncertainty | **STILL_OPEN** — SCIENTIFIC_IDENTIFIABILITY_LIMIT |
| V2-15 | Resistance collapses to depth imbalance | **PARTIALLY_CLOSED** — scope fixed; a depth-only config is still legal and redundancy against real correlated flow is unmeasured |
| V2-16 | Transport gated on one feature's half-life | **STILL_OPEN** — SCIENTIFIC_IDENTIFIABILITY_LIMIT |
| V2-17 | "Preserve scientific status" CI step only echoes | **STILL_OPEN** — LOW, documentation |

## Repairs made in this closeout

* `queue_hazard` — RMST requires an explicit `tau_seconds`, echoes it, and flags
  short follow-up. Identical exits with follow-up at 5s and 500s previously gave
  4.100 and 350.600; both now give 4.100.
* `orderbook_memory` — consecutive republished snapshots dropped and counted.
  Lag-1 imbalance stays at the clean value instead of moving to +0.4565.
* `resistance_field` — flow must share the snapshot's source and lie inside the
  measured depth price window. Mixed vendors now return PROTOCOL_INELIGIBLE.
* `topology_regime` — zero-length MST edges retained so the edge count is always
  n-1, duplicates reported, and a sample-size normalised merge scale added.
* `paired_validation` — duplicate `evidence_hash` refused, outcome ceiling added,
  and `block_size` must cover the overlap implied by lock spacing.
* `queue_survival` — duplicate packets deduplicated before the lineage walk.
* `validation` (V1) — the gate is one-sided, so the stored two-sided confidence
  is `1 - 2*alpha`, putting exactly `alpha` in the lower tail. Verified by
  re-deriving the resample quantile by hand.
* tests — CWD-relative workflow path fixed; advanced-layer fixtures re-spaced to
  non-overlapping locks, because 8H forecasts locked one minute apart are
  roughly 480-deep dependent and cannot support a valid bootstrap.

## Adversarial evidence at the final checkpoint

```
lead-lag screen, alpha 0.01, reverse-direction guard active
  original common driver                  0/25 significant
  asymmetric-latency common driver        0/25
  periodic bursts, shared phase           1/25
  independent self-exciting clusters      0/25
  duplicated events                       0/25
  unequal counts (30 vs 400)              0/25
  GENUINE 1s lead (power)                23/25
  lag-window search, independent data     4/70  (no multiplicity correction)

incremental information I(UMSE;Y|FIA), alpha 0.01
  independent noise                       0/40 significant
  confounded by FIA (UMSE adds nothing)   0/40
  GENUINE incremental information        40/40
  high-cardinality FIA (40 states)        0/20, all INSUFFICIENT_DATA
  tiny sample (n=30)                      0/20, all INSUFFICIENT_DATA
  repeated feature search (40 features)   0/40

mechanism competition, 200k random evidence draws
  all 11 mechanisms reachable; 94.9% of draws yield NO identification
  median top1-top2 separation 0.033 (below the module's own 0.05 threshold)
```

## Production isolation

```
backend/ tree hash   main : bafa7dd2b70d7e51070ca5f32f4eca4b7a0896f4
backend/ tree hash   HEAD : bafa7dd2b70d7e51070ca5f32f4eca4b7a0896f4   IDENTICAL

files changed vs main : 84, all additions
outside research/ and the two research workflows : NONE
symlinks or non-regular files : NONE
push trigger paths filter : REMOVED, so every push runs the isolation job
```

## Unresolved empirical prerequisites

These are data limitations, not code defects, and no software change can close
them.

* No real CME MBO/depth/trade data exists in this branch. Every MBO action and
  size semantic is asserted, never validated against a live feed.
* No market-data adapter exists; only in-memory fixtures.
* Mechanism competition is reachable but weakly identifiable. The
  passive/absorption and liquidation/vacuum score pairs remain correlated above
  0.74, and the module correctly refuses to identify in most states.
* No family-wise correction exists for repeated incremental-information testing
  or lead-lag window search. Searching is the caller's risk.
* The topological and counterfactual layers still have no demonstrated
  incremental information over FIA and remain candidates for deletion.
* Confirmatory N must come from a preregistered power design that does not exist.

## Scientific boundaries, unchanged

```
SUCCESSOR_CAMPAIGN_STARTED = false
ALPHA_SPENT = 0
PREDICTIVE_EDGE = NOT_PROVEN
PRODUCTION_INTEGRATION = false
PREDICTIVE_MAPPING_FROZEN = false
REAL_MBO_CALIBRATION = NOT_DONE
FORWARD_OOS_EDGE = NOT_PROVEN
```

Engineering finalization is not predictive validation. A green CI run and an
18/18 mutation score prove that the code computes what it claims to compute.
They prove nothing about the market.
