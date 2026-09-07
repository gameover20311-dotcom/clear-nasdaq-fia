# CLEAR NASDAQ — FIA · Cognitive Evidence Intelligence Master Specification

## Mission

CLEAR NASDAQ — FIA is a research and forecasting intelligence system for NASDAQ-100 / NQ over a 4–8 hour horizon. It is not a broker, order router or autonomous execution engine. The cognitive layer must investigate evidence, preserve provenance, create competing hypotheses, challenge itself, quantify uncertainty and refuse high-reliability claims when the evidence or validation does not support them.

## Data truth contract

Every usable evidence item must carry source/provider, instrument, observed timestamp, first-seen timestamp where available, freshness/status, raw and normalized value, revision/version metadata where available, checksum and traceable forecast ID. Missing/stale/error data cannot silently become a neutral directional vote. QQQ, NQ, ES, SPX/SPY, DXY, US10Y and other instruments must remain explicitly labelled and cannot be substituted without a visible fallback label.

## News intelligence contract

The system must support normalized article ingestion, publisher/domain identification, publication and first-seen time, duplicate/copy clustering, tracked company/ticker mapping, event type, index relevance, source quality, official-domain/primary-source identification, novelty, explicit actual-vs-consensus surprise when the data exists, observed post-publication price reaction, priced-in status only when reaction evidence exists, impact horizon, source confirmation, contradiction detection and sentiment decay. Unknown surprise or reaction remains unknown.

## Specialist brains

The production cognitive layer contains fifteen specialist brains:

1. Price Structure AI
2. Multi-timeframe Trend AI
3. NQ/ES/SPX Confirmation AI
4. Mega-cap Leadership AI
5. Semiconductor AI
6. Breadth/Internals AI
7. Rates & Yield AI
8. Genuine Dollar/DXY AI
9. Macro Surprise AI
10. Fed Communication AI
11. News Event AI
12. Earnings & Guidance AI
13. Liquidity & Session AI
14. Volatility & Options AI
15. Market Regime AI

Each specialist returns direction, continuous score, bullish probability, reliability, uncertainty, evidence references, reason and explicit missing reason when unavailable.

## Cognitive investigation

The system independently builds bullish and bearish hypotheses and a counter-case. Evidence importance is selected from evidence strength, reliability and regime relevance rather than from the desired forecast direction. Missing high-value evidence and material bull/bear conflict are placed in a controlled investigation queue.

A separate Independent Critic evaluates missing evidence, contradictions, correlated/double-counted evidence, excessive decisiveness in conflicted regimes, weak primary-source confirmation, insufficient coverage and macro-event claims without point-in-time macro evidence. The critic may force a research hold. A bounded reinvestigation pass may query allow-listed provider data, deeper normalized news, SEC EDGAR verification and FRED/ALFRED vintages. It does not use future outcome labels or arbitrary hidden weight tuning.

## Historical analogy

Historical analogies are multidimensional and use point-in-time signal vectors. In a historical replay, an analogy is eligible only if its own future outcome would already have been known at the current replay timestamp. Similarity, sample size and effective sample size are surfaced; fewer than five valid analogues is treated as insufficient evidence.

## Regime-aware fusion

Fusion uses transparent base specialist weights multiplied by current reliability and predeclared regime multipliers. Correlated evidence families have explicit aggregate caps to reduce double counting. Dynamic weighting is auditable and does not learn directly from the current outcome. The analogy engine is capped as a minority contributor.

## Probability and reliability

Raw cognitive probability is separated from reliability. Development-only probability calibration uses regularized Platt scaling. Holdout data is not used to fit calibration. Output includes calibrated bullish/bearish probability, reliability grade/score, approximate probability interval, data coverage, intelligence coverage, decision gate, opposing evidence, missing evidence, model version, dataset split and forecast ID.

## Time-machine replay

Historical tests must use only information available at the replay timestamp. Future candles, future news, later earnings actuals, later filings, revised macro data not yet known, future session extrema and hindsight futures-roll selection are prohibited. Phase 29 provides completed-bar and frozen entry-contract outcome truth; Phase 30 adds cognitive replay and development/holdout calibration.

## Validation

Validation reports directional accuracy, Brier score, log loss, calibration error/reliability bands, 95% Wilson intervals, monthly stability, regime performance, base-model comparison, naive 50% comparison, momentum comparison, specialist ablation, mistake attribution and holdout performance. Suspicious perfect results and denominator errors fail closed.

## Learning and drift

Errors are classified before changes are proposed. Categories include missing/stale data, macro context missing, ignored contradiction/overconfidence, chart/liquidity context missing, and valid-evidence/market-moved-opposite. Drift monitoring compares current/forward distributions to the frozen reference and produces STABLE/WATCH/ALERT states. No weight change is accepted without development evidence and separate out-of-sample validation.

## Acceptance standard

A market-grade claim remains WITHHELD unless traceability, no-known-leakage, missing-data truth, sufficient holdout size and useful out-of-sample probability quality all pass. A sophisticated architecture is never allowed to replace evidence of performance.

## Safety

Research only. No broker connection. No automatic order execution. No accuracy guarantee. No promise that a changing market will never require maintenance or future data-source upgrades.
