# Phase 06 — Regime Analysis

Phase 6 analyzes historical FIA outcomes by market regime.

The module:
- preserves the existing FIA regime when available;
- provides a fallback trend/volatility classifier;
- separates 4H and 8H observations;
- calculates regime-wise observation count;
- calculates regime-wise accuracy when outcomes are available;
- calculates average realized return when available.

This phase does not modify live FIA weights or forecast logic.

Actual historical results require historical prediction/outcome records.
