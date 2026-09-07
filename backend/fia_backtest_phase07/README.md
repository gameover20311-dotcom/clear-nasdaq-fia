# Phase 07 — Session Analysis

Phase 7 analyzes historical FIA performance by trading session.

Default UTC windows:
- ASIA: 00:00–07:59 UTC
- LONDON: 08:00–12:59 UTC
- NEW_YORK: 13:00–20:59 UTC
- OFF_SESSION: 21:00–23:59 UTC

The analysis keeps 4H and 8H horizons separate.

It reports:
- observation count;
- accuracy when realized outcomes are available;
- average realized return;
- average predicted probability.

Missing historical records are not replaced with fabricated values.

This phase does not modify live FIA weights or forecast logic.
