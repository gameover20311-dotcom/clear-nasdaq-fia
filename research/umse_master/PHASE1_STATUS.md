# UMSE MASTER — Phase 1 Status

## Status

Phase 1 has started. It remains isolated from BASE_FIA and production.

## Implemented so far

- causal `MarketEvent` contract
- explicit event types for aggression, cancellation, replenishment, sweeps, large trades, book snapshots and cross-market shocks
- immutable causal `EventWindow`
- rejection of events not causally available at decision time
- rejection of future event-time rows even when provider metadata is malformed
- provenance-id uniqueness guard
- order-id semantics restricted to true MBO data classes
- descriptive, non-predictive primitive feature extraction
- aggression imbalance
- cancellation/replenishment volume
- replenishment ratio
- sweep counts
- large-trade volume
- observed price response
- explicit queue-survival identifiability flag

## Important scientific boundary

Aggregate L2 is never treated as true MBO. Exact queue/order survival is only marked identifiable when every relevant event carries true MBO order identity.

The primitives are descriptive only. No Phase-1 feature currently changes 4H/8H probabilities or claims predictive value.

## Test status

Combined Phase-0 + current Phase-1 contract suite was executed in an isolated Python environment:

`15 tests run — 15 PASS`

The tests cover causal timing, future-data rejection, synthetic/proxy restrictions, stale-data rejection, production isolation, 4H/8H separation, deterministic provenance, duplicate event rejection, MBO identity restrictions and causal primitive calculations.

## Current scientific status

- `PREDICTIVE_EDGE = NOT_PROVEN`
- `PRODUCTION_INTEGRATION = false`
- `SUCCESSOR_CAMPAIGN_STARTED = false`
- `ALPHA_SPENT = 0`

## Next Phase-1 work

- liquidity-field representation
- response-surprise contract
- resilience/impact-decay primitives
- state-transition observation container
- cross-scale persistence contract
- hostile tests for missing/stale/proxy mixtures

No predictive mapping will be frozen until these non-predictive contracts are stable.
