# Phase 09 — Ablation Testing

Phase 9 measures how historical results change when observations associated
with one signal are excluded.

The current implementation is descriptive leave-one-signal-out analysis.

It reports:
- baseline observation count;
- ablated observation count;
- baseline accuracy;
- ablated accuracy;
- accuracy delta;
- baseline average return;
- ablated average return;
- return delta.

Important:
This implementation does not rerun the FIA model with a signal removed.
Therefore results should not be interpreted as causal proof of signal importance.

It does not modify live FIA weights or forecast logic.

Actual historical conclusions require real historical prediction/outcome records.
