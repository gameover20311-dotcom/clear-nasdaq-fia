# SIMONS SHADOW LAB V1 — Threat / Leakage Model

## Assets protected

- production BASE_FIA behavior
- Forward-OOS campaign seals and model fingerprints
- immutable forecast locks
- evidence hashes and event hash chains
- discovery/validation separation
- candidate definitions and decision locks
- honest NOT_PROVEN status

## Threats and controls

### Future leakage
**Threat:** outcome data reaches decision-time features.
**Control:** `extract_lock_time_features()` never reads `row['outcomes']`; regression tests mutate outcomes and require identical decision-time features.

### Historical relabeling
**Threat:** an old row is presented as new forward validation.
**Control:** candidate freeze records discovery IDs; lock time must be strictly after candidate creation; discovery IDs are rejected.

### Parameter fishing / p-hacking
**Threat:** thousands of searches are run and only the winner is shown.
**Control:** predeclared grids return every tested combination; experiment registry hash-chains each registered run; BH q-values are reported; no automatic candidate selection exists.

### Same-model pseudo-confirmation
**Threat:** multiple FIA components are called independent confirmation.
**Control:** feature schema explicitly sets `component_alignment_is_independent_evidence=false`.

### Candidate mutation
**Threat:** thresholds change after seeing outcomes.
**Control:** candidates are create-once SHA256 records; no update API exists.

### Decision mutation
**Threat:** FIRE/NO_FIRE changes after resolution.
**Control:** decisions and resolutions are separate create-once hash-chained events.

### Production coupling
**Threat:** research code changes production output or model fingerprint.
**Control:** package lives outside `backend/fia`; no production write helper is imported; branch diff is reviewed against `main`; no automatic promotion exists.

### Durable-store overclaim
**Threat:** Postgres event mirror is presented as having reverified evidence files it does not store.
**Control:** durable adapter reports `evidence_file_bytes_verified=false` and preserves only the evidence hashes embedded in lock events.

### Missing/stale feature fabrication
**Threat:** absent evidence is silently filled to improve sample size.
**Control:** missing stays missing; matching fails closed where a required value is absent.

### Small-sample overclaim
**Threat:** a tiny cluster is marketed as a strategy.
**Control:** candidate status remains NOT_PROVEN below defined forward sample gates; reporting hard-displays EDGE NOT PROVEN.

### Cost overclaim
**Threat:** assumed friction is described as measured execution cost.
**Control:** gross and assumed-friction results are separate and the report labels friction as an assumption.

## Explicit non-goals

V1 does not reproduce Medallion, does not claim proprietary Renaissance knowledge, does not prove profitability, does not auto-trade, and does not auto-deploy a discovered candidate into BASE_FIA.
