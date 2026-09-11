# SIMONS SHADOW LAB V1

Independent quantitative research layer for CLEAR NASDAQ FIA.

## Purpose

The lab studies immutable Forward-OOS evidence without changing BASE_FIA, the production Forward-OOS ledger, evidence files, campaign seals, dashboard logic, or predictive logic.

It is inspired by publicly documented systematic-research principles associated with Jim Simons / Renaissance Technologies: many weak hypotheses, disciplined testing, model-driven decisions, signal decay awareness, and aggressive skepticism about overfitting.

It does **not** reproduce Medallion, claim access to proprietary Renaissance methods, or claim predictive edge.

## Hard isolation

The package lives outside `backend/fia`, so adding or deleting it does not enter the production FIA Python fingerprint surface used by `fia/forward_oos.py`.

The lab never imports production append/write helpers. Production Forward-OOS is treated as read-only evidence.

Writes are allowed only under the separate lab root (default `simons_shadow_lab_data`).

## Scientific flow

1. Verify production Forward-OOS hash chain, evidence hashes, campaign seal hash and ledger head.
2. Create an immutable research snapshot with its own SHA256 manifest.
3. Register hypotheses as `DISCOVERY_ONLY_NOT_PROVEN`.
4. Run a small predeclared interpretable threshold grid for exploration only.
5. Freeze a candidate rule with exact conditions, horizon, discovery snapshot, discovery forecast IDs and number of tests tried.
6. A candidate may lock `FIRE` / `NO_FIRE` only on a production forecast whose lock time is strictly after candidate freeze.
7. The shadow decision is immutable and explicitly records `outcome_information_read: false`.
8. Only after production appends the matching 4H/8H resolution may the lab append a separate shadow resolution event.
9. Candidate reports remain `NOT_PROVEN`; no automatic production promotion exists.

## Anti-overfitting controls in V1

- discovery rows are permanently excluded from that candidate's forward validation;
- candidate rules are immutable after freeze;
- all exploratory grid tests are returned, not only the best one;
- Benjamini-Hochberg q-values are reported for the fixed grid;
- minimum sample status is explicit;
- no black-box model is fitted to a tiny sample;
- no historical row can be relabeled as forward validation;
- no result can auto-update BASE_FIA.

## CLI

From `backend`:

```bash
python run_simons_shadow_lab_v1.py audit
python run_simons_shadow_lab_v1.py snapshot
python run_simons_shadow_lab_v1.py discover --snapshot-id <SNAPSHOT_ID> --min-n 12
python run_simons_shadow_lab_v1.py report --candidate-id <CANDIDATE_ID>
```

Use explicit roots when required:

```bash
python run_simons_shadow_lab_v1.py \
  --source-root /path/to/fia_forward_oos \
  --lab-root /path/to/simons_shadow_lab_data \
  audit
```

## Status vocabulary

- `DISCOVERY_ONLY_NOT_PROVEN`
- `FORWARD_VALIDATION_READY_NOT_PROVEN`
- `INSUFFICIENT_SAMPLE_NOT_PROVEN`
- `FORWARD_VALIDATING_NOT_PROVEN`
- `RESEARCH_REVIEW_ELIGIBLE_NOT_PRODUCTION_APPROVED`

V1 deliberately never emits `PROVEN`.

## Current limits

V1 is the scientific skeleton, not the final strategy engine. It does not yet include execution-cost modeling, drawdown/expectancy, state-transition models, regime decay scoring, richer causal evidence extraction, or a UI. Those should be added only after isolation and real Forward-OOS ingestion are verified on the target runtime.

Engineering tests passing does **not** mean a profitable strategy or predictive edge exists.
