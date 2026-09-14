# SIMONS SHADOW LAB V1 — Data Contract

## Source authority

Shadow Lab consumes immutable CLEAR NASDAQ Forward-OOS events. Production is read-only. The lab has no API that updates, deletes, reseals, backfills, or re-labels a production event.

Supported source modes:

1. File-ledger mode: verifies event hash chain, ledger head, campaign seal, evidence references and evidence-file SHA256 when the evidence files are present.
2. Durable Postgres mode: SELECT-only access to `forward_oos_events`, `is_test=FALSE`, verifies the canonical event hash chain. The durable table does **not** contain evidence-file bytes, so durable-mode reports `evidence_file_bytes_verified=false` rather than pretending the evidence SHA was independently rechecked.

## Eligible research row

A directional research row originates from `FORECAST_LOCK` and may later receive separate `RESOLUTION_4H` and/or `RESOLUTION_8H` events.

Lock-time fields may include:

- forecast ID and lock time
- explicit NQ contract and entry metadata
- 4H/8H published probabilities
- 4H/8H confidence/state/actionability
- FIA direction, regime, score and status
- data/intelligence coverage
- source-status metadata
- locked FIA evidence-component scores such as NQ structure, DXY, US10Y, mega-cap leadership, semiconductors, participation, news, macro calendar and earnings/guidance when present

Missing fields remain missing. No zero, proxy, current value, or hindsight substitution is allowed merely to make a row complete.

## Outcomes

4H/8H outcomes are labels only. They are never allowed into decision-time feature extraction. Candidate decisions must be immutable before a matching resolution can be attached.

## Abstentions

Production abstention observations are legitimate scientific records but are not silently converted into bullish/bearish outcomes or wins/losses. V1 directional strategy discovery uses directional locks only; abstention research remains separately identifiable.

## Feature wording

`component_alignment_count` measures agreement among components inside the FIA evidence stack. It must **not** be described as independent-model confirmation or independent evidence.

## Discovery vs validation

Every candidate stores its discovery snapshot and discovery forecast IDs. Those rows are permanently ineligible for that candidate's forward validation. Only forecast locks strictly later than candidate freeze may enter validation.

## Small-sample policy

- `<30` resolved fires: `INSUFFICIENT_SAMPLE_NOT_PROVEN`
- `30–49`: `FORWARD_VALIDATING_NOT_PROVEN`
- `>=50`: may become `RESEARCH_REVIEW_ELIGIBLE_NOT_PRODUCTION_APPROVED`

None of these statuses mean predictive edge or profitability is proven.
