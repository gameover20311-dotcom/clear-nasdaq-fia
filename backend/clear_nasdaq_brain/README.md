# CLEAR NASDAQ — FIA BRAIN V6 CAUSAL-TWIN

V6 is not designed as a generic “multi-agent wrapper.” It adds pre-registered, testable reasoning structures around local `gpt-oss:20b`:

1. **Atomic Evidence Genome** — every forecast fingerprints the exact evidence composition, correlation structure and freshness profile.
2. **Causal Market Twin** — validated causal chains are converted into a deterministic driver graph exposing contradiction and concentration.
3. **Competing Hypothesis Ledger** — multiple explanations are pre-registered before the Chief forecast, with evidence for/against and explicit invalidation.
4. **Three-World Scenario Lattice** — BULL/BASE/BEAR worlds must be mutually exclusive and sum to 100; high entropy mechanically caps confidence.
5. **Reasoning Precommitment Hash** — causal twin + hypotheses + scenarios are hashed before the final Chief answer, preventing post-hoc narrative rewriting in later autopsy.
6. **Regime Novelty Gate** — a TRAIN-only robust evidence-genome baseline can detect out-of-distribution evidence regimes and cap confidence; it can never create direction.
7. **Temporal Failure Memory** — resolved prior mistakes can cap confidence, but memory is filtered strictly by `resolved_at < forecast_as_of` to block future leakage.
8. **DEV Ablation Lab** — each deterministic V6 gate can be switched off only on DEV to prove whether it materially changes behavior; HOLDOUT ablation is forbidden.

The original CLEAR NASDAQ backend remains read-only. Production evidence still comes only from the single atomic `/api/dashboard` payload. Provider health is deterministic gate metadata and is never mixed into LLM evidence.

## Truth rule
V6 does **not** claim that gpt-oss:20b literally became GPT-5.6 Sol, does not claim World #1, and does not claim market edge. Those claims require sealed blind comparison and genuine Forward-OOS evidence.

## V6 intervention + reasoning parity layer
- **Leave-one-driver-out causal interventions** test whether the twin's net view flips when a dominant driver is removed. Single-driver fragility caps confidence.
- **Structured Sol parity** now compares causal chains, competing hypotheses and BULL/BASE/BEAR scenario probabilities in addition to the final answer. A HOLDOUT row without this reasoning signature is invalid for V6 parity.
