# Phase 28 — Market-Grade Point-in-Time Replay

This phase does not tune the forecast, Phase24, Phase25 or Phase26 logic. It builds a strict one-year historical replay around the frozen production research engine.

Data policy:
- NQ: raw overlapping Massive 5m futures contracts; dominant contract selected using only completed trailing-24h volume as-of each timestamp.
- ES: same Massive 5m method when the current API plan permits it; otherwise SMT remains missing.
- Market leadership / QQQ / SPY / DXY / US10Y: historical 1h Yahoo adapter already used by the project.
- News: cached Polygon one-year archive plus point-in-time supplemental Finnhub logic.
- Earnings: SEC acceptance timestamp gates released earnings; future actual EPS is prohibited.
- Macro: Finnhub calendar timing if historical plan access exists. No directional macro score is invented; unavailable macro is missing, not neutral.
- Phase25: deterministic OHLC-only OB/FVG/liquidity/SMT/session/execution evidence from completed historical bars.

A `MARKET_GRADE` label is only emitted when all hard real-data checks pass and both ES SMT coverage and historical macro-calendar coverage are available. Otherwise the summary says `REAL_DATA_DEGRADED` rather than pretending completeness.
