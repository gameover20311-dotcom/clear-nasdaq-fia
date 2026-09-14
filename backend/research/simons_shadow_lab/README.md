# SIMONS SHADOW LAB V1 — GPT-5.6 Sol independent build

Status: **RESEARCH ONLY**  
Production influence: **NONE**  
Predictive edge: **NOT_PROVEN**

## Purpose
SIMONS SHADOW LAB V1 is an isolated scientific research layer for CLEAR NASDAQ FIA. It consumes the immutable Forward-OOS record read-only, creates deterministic research snapshots, performs constrained interpretable discovery, freezes candidate rules, and evaluates them only on later genuinely unseen observations.

It does **not** reproduce or claim to know Renaissance Technologies / Medallion proprietary methods. The design borrows only public high-level principles: systematic research, many weak hypotheses, strict falsification, changing regimes, and strong anti-overfitting discipline.

## Isolation contract
The package lives under `backend/research/`, outside the production `backend/fia/` fingerprint surface. It intentionally does not import `fia.forward_oos`, because production verification may perform a durable restore when local storage is empty. The lab independently verifies the campaign seal, production fingerprint, event hash chain, ledger head and evidence hashes with read-only filesystem operations.

The lab may write only to a caller-supplied **lab-owned** directory for snapshots and frozen candidates. It never writes into `fia_forward_oos`, never reseals a campaign, never backfills a missed lock, and never changes BASE_FIA.

## V1 pipeline
1. **Audit source** — independently verify campaign seal/fingerprint and Forward-OOS ledger/evidence chain.
2. **Build deterministic snapshot** — identical source state yields the same snapshot ID/SHA256.
3. **Separate features/outcomes** — features come only from `FORECAST_LOCK` and lock-time evidence; later 4H/8H resolutions are labels only.
4. **Constrained discovery** — a predeclared probability/confidence/agreement grid is tested; every attempted hypothesis is retained and Benjamini-Hochberg FDR is applied.
5. **Freeze candidate** — exact rule, discovery snapshot hash, discovery row IDs, freeze time and validation N become immutable.
6. **Future-only validation** — rows at/before freeze or used in discovery are permanently excluded for that candidate.
7. **Paired BASE comparison** — candidate and BASE are compared on the same fired future rows with a deterministic paired bootstrap CI.
8. **No auto-promotion** — even a survivor can only become `RESEARCH_PROMOTION_REVIEW_ELIGIBLE`. Project truth remains `PREDICTIVE_EDGE=NOT_PROVEN`.

## Fail-closed behavior
Research stops or remains insufficient when source hashes fail, evidence is missing/tampered, timestamps imply future information, sample size is too small, a candidate freeze hash is invalid, or a frozen candidate is retuned under the same identity.

## Deliberate V1 limits
V1 starts narrow. It does **not** run large black-box ML searches, genetic optimization, arbitrary feature-combination explosions, or self-modifying thresholds. With a small Forward-OOS sample, those methods can manufacture false alpha very quickly.

The initial discovery surface evaluates 4H and 8H separately using bounded probability thresholds, confidence thresholds and horizon-agreement conditions. Additional hypothesis families should be added only with explicit test counting, complexity controls and leakage tests.

## Interpretation
- `DISCOVERY_ONLY` is not validated edge.
- `FORWARD_VALIDATING` is not validated edge.
- `ROBUST_CANDIDATE` means the candidate survived the configured V1 research gate and is eligible for human review only.
- Nothing in this module means automatic deployment.
- `PREDICTIVE_EDGE=NOT_PROVEN` remains the default scientific conclusion until genuine unseen evidence satisfies a separately approved standard.
