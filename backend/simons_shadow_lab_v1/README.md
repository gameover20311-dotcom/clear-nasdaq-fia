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

## Advanced research diagnostics

`research_metrics.py` adds research-only diagnostics without modifying the immutable core:

- Brier score;
- log loss;
- expected calibration error (ECE);
- climatology baseline and Brier skill comparison;
- regime-wise hit rate and Brier diagnostics;
- previous-regime -> current-regime state-transition analysis;
- one-at-a-time threshold perturbation to expose knife-edge/fragile candidates;
- gross directional move in NQ points;
- explicit assumed round-trip friction scenario in points;
- early-vs-late forward sample comparison as a simple signal-decay warning.

These diagnostics are deliberately labeled `DISCOVERY_ONLY_NOT_PROVEN`, `DISCOVERY_ROBUSTNESS_ONLY_NOT_VALIDATION`, or other NOT_PROVEN states. They do not select or promote strategies automatically.

## Friction policy

The lab keeps raw statistical evidence separate from execution assumptions.

`candidate_forward_metrics()` accepts an explicit `round_trip_cost_points` scenario and reports gross and net points separately. It does not size positions, model leverage, or turn an assumed friction number into a claimed measured cost.

## CLI

From `backend`:

```bash
python run_simons_shadow_lab_v1.py audit
python run_simons_shadow_lab_v1.py snapshot
python run_simons_shadow_lab_v1.py discover --snapshot-id <SNAPSHOT_ID> --min-n 12
python run_simons_shadow_lab_v1.py diagnostic --snapshot-id <SNAPSHOT_ID> --horizon 4
python run_simons_shadow_lab_v1.py diagnostic --snapshot-id <SNAPSHOT_ID> --horizon 8
python run_simons_shadow_lab_v1.py robustness --candidate-id <CANDIDATE_ID>
python run_simons_shadow_lab_v1.py forward-metrics --candidate-id <CANDIDATE_ID> --cost-points 0
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
- `DISCOVERY_ROBUSTNESS_ONLY_NOT_VALIDATION`
- `FORWARD_VALIDATION_READY_NOT_PROVEN`
- `INSUFFICIENT_SAMPLE_NOT_PROVEN`
- `FORWARD_VALIDATING_NOT_PROVEN`
- `RESEARCH_REVIEW_ELIGIBLE_NOT_PRODUCTION_APPROVED`

V1 deliberately never emits `PROVEN`.

## Current validation truth

The software architecture and regression tests can pass while the research result remains scientifically empty. Until a frozen candidate accumulates genuinely new post-freeze observations, there is no valid forward candidate sample to judge.

Therefore:

- engineering integrity may be PASS;
- candidate edge remains `NOT_PROVEN`;
- profitability remains `NOT_PROVEN`;
- no production promotion is allowed.

## Current limits

V1 still does not claim a strategy. Richer causal evidence extraction, predeclared state-transition candidates, measured execution-cost ingestion, adverse-excursion/drawdown metrics when genuinely available, and a separate research UI remain future work.

Those additions must not weaken isolation, candidate freezing, discovery/validation separation, or Forward-OOS integrity.

Engineering tests passing does **not** mean a profitable strategy or predictive edge exists.
