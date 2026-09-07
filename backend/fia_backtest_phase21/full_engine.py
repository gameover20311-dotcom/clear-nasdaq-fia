from datetime import datetime, timezone
from math import exp

from fia.config import Config
from fia.models import Signal, Forecast
from fia.intelligence import intelligent_score as calculate_evidence_score, intelligence_coverage, evidence_summary, intelligence_confidence, nasdaq_impact_direction, top_nasdaq_drivers

CFG = Config()


def clamp(x, a=-1.0, b=1.0):
    return max(a, min(b, x))


# ============================================================
# FIA INTELLIGENCE LAYER
# ============================================================

# Evidence quality reflects how much trust FIA gives to each
# category beyond its raw signal score.
EVIDENCE_QUALITY = {
    "NQ structure": 1.00,
    "SPX confirmation": 0.95,
    "DXY": 0.90,
    "US10Y": 0.90,
    "Mega-cap leadership": 1.00,
    "Semiconductors": 0.98,
    "Breadth": 0.90,
    "Liquidity": 0.95,
    "News": 0.82,
    "Macro calendar": 0.88,
    "Earnings/guidance": 0.92,
}


def _freshness_factor(freshness):
    """
    Freshness multiplier.
    Existing providers may currently only expose 'live'/'missing',
    so this remains backward compatible.
    """
    value = str(freshness or "").lower()

    if value == "live":
        return 1.00
    if value in {"fresh", "recent"}:
        return 0.95
    if value in {"aging", "stale"}:
        return 0.70
    if value in {"old"}:
        return 0.50
    return 0.0


def _signal_evidence(signal):
    """
    Converts an existing Signal into an evidence-adjusted contribution.
    """
    quality = EVIDENCE_QUALITY.get(signal.name, 0.80)
    freshness = _freshness_factor(signal.freshness)

    return {
        "quality": quality,
        "freshness": freshness,
        "effective_weight": signal.weight * quality * freshness,
        "contribution": signal.score * signal.weight * quality * freshness,
    }


def _direction(score):
    if score > 0.12:
        return "BULLISH"
    if score < -0.12:
        return "BEARISH"
    return "NEUTRAL"


def _build_evidence(signals):
    """
    Produces human-readable evidence without requiring new model fields.
    Strongest positive and negative evidence is surfaced through the
    existing Signal.detail strings.
    """
    positive = []
    negative = []

    for signal in signals:
        if signal.freshness == "missing":
            continue

        evidence = _signal_evidence(signal)
        strength = abs(signal.score) * evidence["quality"] * evidence["freshness"]

        if strength < 0.10:
            continue

        item = (
            f"{signal.name}: "
            f"{_direction(signal.score)} "
            f"(strength {strength:.2f}) — {signal.detail}"
        )

        if signal.score > 0:
            positive.append((strength, item))
        elif signal.score < 0:
            negative.append((strength, item))

    positive.sort(reverse=True)
    negative.sort(reverse=True)

    return (
        [item for _, item in positive[:4]],
        [item for _, item in negative[:4]],
    )


def _confirmation_score(signals):
    """
    Measures whether important signals agree.

    High agreement strengthens the thesis.
    Heavy disagreement reduces confidence.
    """
    active = [
        s for s in signals
        if s.freshness != "missing" and abs(s.score) >= 0.10
    ]

    if len(active) < 2:
        return 0.0, 0.0

    weighted_direction = sum(
        s.score * s.weight * EVIDENCE_QUALITY.get(s.name, 0.80)
        for s in active
    )

    total = sum(
        s.weight * EVIDENCE_QUALITY.get(s.name, 0.80)
        for s in active
    )

    if total == 0:
        return 0.0, 0.0

    normalized = weighted_direction / total

    same_direction = sum(
        s.weight
        for s in active
        if s.score * normalized > 0
    )

    opposite_direction = sum(
        s.weight
        for s in active
        if s.score * normalized < 0
    )

    agreement_total = same_direction + opposite_direction

    agreement = (
        same_direction / agreement_total
        if agreement_total
        else 0.0
    )

    conflict = opposite_direction / agreement_total if agreement_total else 0.0

    return clamp(agreement), clamp(conflict)


def _impact_coverage(signals):
    """
    Coverage is based on evidence-adjusted importance, not merely
    provider availability.
    """
    total_importance = sum(
        s.weight * EVIDENCE_QUALITY.get(s.name, 0.80)
        for s in signals
    )

    live_importance = sum(
        s.weight
        * EVIDENCE_QUALITY.get(s.name, 0.80)
        * _freshness_factor(s.freshness)
        for s in signals
        if s.freshness != "missing"
    )

    if total_importance == 0:
        return 0.0

    return clamp(live_importance / total_importance, 0.0, 1.0)


def _intelligent_score(signals):
    """
    Core intelligence calculation.

    Unlike the old linear formula:
        weighted score -> coverage -> probability

    this calculation adjusts the evidence by:
        - evidence quality
        - freshness
        - cross-signal confirmation
        - conflict
    """
    total_effective_weight = 0.0
    weighted_evidence = 0.0

    for signal in signals:
        evidence = _signal_evidence(signal)

        total_effective_weight += evidence["effective_weight"]
        weighted_evidence += evidence["contribution"]

    if total_effective_weight == 0:
        return 0.0, 0.0, 0.0

    base_score = weighted_evidence / total_effective_weight

    agreement, conflict = _confirmation_score(signals)

    # Agreement bonus is deliberately modest.
    confirmation_multiplier = 1.0 + (agreement - 0.50) * 0.30

    # Conflict penalty prevents a handful of strong but contradictory
    # signals from producing unjustified confidence.
    conflict_multiplier = 1.0 - conflict * 0.22

    intelligent_score = (
        base_score
        * confirmation_multiplier
        * conflict_multiplier
    )

    return (
        clamp(intelligent_score),
        agreement,
        conflict,
    )


def _probability_from_score(score):
    """
    Smooth probability mapping.

    This replaces the old fixed:
        50 + 40 * score

    with a bounded logistic transformation.
    """
    probability = 50.0 + 45.0 * (
        2.0 / (1.0 + exp(-2.2 * score)) - 1.0
    )

    return clamp(probability, 5.0, 95.0)


def _confidence(
    probability,
    coverage,
    agreement,
    conflict,
):
    """
    Confidence is intentionally separate from probability.

    A 70% probability with poor evidence coverage should not have
    the same confidence as a 70% probability backed by broad,
    fresh and mutually confirming evidence.
    """
    directional_strength = abs(probability - 50.0) / 50.0

    confidence = (
        directional_strength * 45.0
        + coverage * 30.0
        + agreement * 20.0
        - conflict * 25.0
    )

    return clamp(confidence, 0.0, 100.0)


def _regime(score, conflict):
    magnitude = abs(score)

    if conflict >= 0.55:
        return "CONFLICTED"

    if magnitude >= 0.35:
        return "TREND"

    if magnitude <= 0.12:
        return "BALANCED"

    return "TRANSITION"


def _status(coverage):
    if coverage >= 0.85:
        return "LIVE"
    if coverage > 0:
        return "DEGRADED"
    return "DEMO"


def _build_invalidation(direction, signals, raw):
    """
    Dynamic invalidation based on the current thesis.
    """
    invalidation = []

    if direction == "BULLISH":
        invalidation.extend([
            "NQ structure flips materially bearish",
            "SPX/NQ confirmation diverges materially",
            "Mega-cap leadership turns materially negative",
            "Semiconductor leadership loses confirmation",
        ])
    elif direction == "BEARISH":
        invalidation.extend([
            "NQ structure flips materially bullish",
            "SPX/NQ confirmation turns supportive",
            "Mega-cap leadership reverses materially higher",
            "Semiconductor leadership regains strong confirmation",
        ])
    else:
        invalidation.extend([
            "NQ structure establishes a decisive directional break",
            "SPX/NQ confirmation develops a sustained divergence",
            "Mega-cap leadership becomes one-sided",
        ])

    if raw.get("macro") is not None:
        invalidation.append(
            "Major scheduled macro event materially changes the regime"
        )

    if raw.get("earnings_catalyst_risk"):
        invalidation.append(
            "Upcoming SEC-verified earnings release inside the forecast horizon materially changes leadership or volatility"
        )
    elif raw.get("earnings") is not None:
        invalidation.append(
            "Major earnings/guidance surprise changes the leadership impulse"
        )

    if raw.get("liquidity_signal") is not None:
        invalidation.append(
            "NQ liquidity sweep/reclaim structure materially changes the directional bias"
        )

    return invalidation


def build_forecast(snapshot: dict) -> Forecast:
    raw = snapshot.get("data", {})

    signals = []

    def add(name, score, weight, detail, freshness="live"):
        if score is None:
            signals.append(
                Signal(
                    name=name,
                    score=0.0,
                    weight=weight,
                    detail="Awaiting provider data",
                    freshness="missing",
                )
            )
            return

        signals.append(
            Signal(
                name=name,
                score=clamp(float(score)),
                weight=weight,
                detail=detail,
                freshness=freshness,
            )
        )

    # ========================================================
    # EXISTING LIVE SIGNAL ADAPTERS
    # ========================================================

    adapters = [
        (
            "NQ structure",
            raw.get("nq_structure"),
            0.20,
            "QQQ/NQ intraday structure and momentum",
        ),
        (
            "SPX confirmation",
            raw.get("spx_confirmation"),
            0.10,
            "S&P 500 confirmation / divergence",
        ),
        (
            "DXY",
            raw.get("dxy"),
            0.08,
            "US dollar pressure on NASDAQ risk assets",
        ),
        (
            "US10Y",
            raw.get("us10y"),
            0.07,
            "US 10Y yield / rates pressure",
        ),
        (
            "Mega-cap leadership",
            raw.get("mega_cap"),
            0.20,
            "Impact-weighted NASDAQ mega-cap leadership",
        ),
        (
            "Semiconductors",
            raw.get("semis"),
            0.12,
            "AI / semiconductor leadership",
        ),
        (
            "Breadth",
            raw.get("breadth"),
            0.08,
            "NASDAQ participation and breadth",
        ),
        (
            "Liquidity",
            raw.get("liquidity_signal"),
            0.08,
            "Point-in-time NQ liquidity sweeps, reclaims and directional bias",
        ),
        (
            "News",
            raw.get("news"),
            0.07,
            "Market-moving news sentiment",
        ),
        (
            "Macro calendar",
            raw.get("macro"),
            0.04,
            "Scheduled macro-event risk",
        ),
        (
            "Earnings/guidance",
            raw.get("earnings"),
            0.04,
            "Earnings and guidance impulse",
        ),
    ]

    for name, value, weight, detail in adapters:
        add(name, value, weight, detail)

    if raw.get("earnings_catalyst_risk"):
        for signal in signals:
            if signal.name == "Earnings/guidance":
                symbols = raw.get("earnings_upcoming_symbols") or []
                hours = raw.get("earnings_hours_to_next")
                extra = ""
                if symbols:
                    extra += " | symbols: " + ", ".join(map(str, symbols))
                if hours is not None:
                    extra += f" | next event in {float(hours):.2f}h"
                signal.detail = (
                    "Upcoming SEC-verified earnings catalyst inside forecast horizon; "
                    "future EPS direction is intentionally unavailable before reveal"
                    + extra
                )
                signal.freshness = "missing"
                break

    # ========================================================
    # INTELLIGENCE ENGINE
    # ========================================================

    coverage = _impact_coverage(signals)

    # Candle evidence is a critical input for NQ structure.
    # Do not report full intelligence coverage when that evidence
    # is unavailable.
    candle_health = str(
        raw.get("provider_candle_evidence", "unknown")
    ).lower()

    if candle_health == "missing":
        coverage *= 0.80
    elif candle_health == "unknown":
        coverage *= 0.90

    intelligent_score, agreement, conflict = _intelligent_score(signals)

    # Intelligence Layer: evidence-adjusted score
    evidence_score, evidence_assessments = calculate_evidence_score(signals)
    intelligence_cov = intelligence_coverage(signals)

    # Blend existing model with evidence intelligence.
    intelligent_score = (
        (intelligent_score * 0.40)
        + (evidence_score * 0.60)
    )

    # Probability is now driven primarily by evidence-adjusted intelligence.
    bullish_probability = _probability_from_score(intelligent_score)
    bearish_probability = 100.0 - bullish_probability

    # Existing confidence model
    base_confidence = _confidence(
        bullish_probability,
        coverage,
        agreement,
        conflict,
    )

    # Intelligence-aware confidence
    intelligence_conf = intelligence_confidence(
        evidence_assessments,
        intelligence_cov,
    )

    # Preserve the existing model while giving evidence intelligence priority.
    confidence = (
        (base_confidence * 0.40)
        + (intelligence_conf * 100.0 * 0.60)
    )

    confidence = clamp(confidence, 0.0, 100.0)

    # Phase 21 decision policy:
    # remove the 55/45 prediction neutral band.
    #
    # IMPORTANT: the robustness/holdout audit used the persisted
    # one-decimal probability exposed by ForecastResult/CSV. Use the
    # same one-decimal value here so direction can never disagree with
    # the displayed probability around the 50.0 boundary.
    decision_probability = round(bullish_probability, 1)

    if decision_probability >= 50.0:
        direction = "BULLISH"
    else:
        direction = "BEARISH"

    regime = _regime(
        intelligent_score,
        conflict,
    )

    status = _status(coverage)

    positive_evidence, negative_evidence = _build_evidence(signals)

    # ========================================================
    # EVIDENCE-BACKED SIGNAL DETAILS
    # ========================================================

    for signal in signals:
        if signal.freshness == "missing":
            continue

        evidence = _signal_evidence(signal)

        signal.detail = (
            f"{signal.detail} | "
            f"Evidence quality {evidence['quality']:.2f}; "
            f"freshness {evidence['freshness']:.2f}; "
            f"effective contribution "
            f"{evidence['contribution']:+.3f}"
        )

    # Add the consolidated thesis to the first available signal so
    # existing Streamlit UI can display it without requiring a schema
    # migration.
    thesis_parts = []

    if positive_evidence:
        thesis_parts.append(
            "Bullish evidence: " + " | ".join(positive_evidence[:2])
        )

    if negative_evidence:
        thesis_parts.append(
            "Bearish/conflicting evidence: "
            + " | ".join(negative_evidence[:2])
        )

    thesis_parts.append(
        f"Evidence coverage {coverage:.0%}; "
        f"cross-signal agreement {agreement:.0%}; "
        f"conflict {conflict:.0%}."
    )

    thesis = " ".join(thesis_parts)

    # Keep existing schema untouched.
    # The thesis is attached to the highest-impact active signal.
    active_signals = [
        s for s in signals
        if s.freshness != "missing"
    ]

    if active_signals:
        anchor = max(
            active_signals,
            key=lambda s: s.weight
        )
        anchor.detail = (
            f"{anchor.detail} | FIA THESIS: {thesis}"
        )

    # Build evidence-backed intelligence summary.
    bullish_evidence_items, bearish_evidence_items = evidence_summary(
        evidence_assessments
    )

    def _format_evidence(a):
        strength = float(a.strength)

        if strength >= 0.70:
            strength_label = "Strong"
        elif strength >= 0.40:
            strength_label = "Moderate"
        else:
            strength_label = "Weak"

        impact_value = float(a.market_impact)
        if impact_value >= 0.75:
            impact_label = "High"
        elif impact_value >= 0.45:
            impact_label = "Medium"
        else:
            impact_label = "Low"

        quality_value = float(a.source_quality)
        if quality_value >= 0.75:
            quality_label = "High"
        elif quality_value >= 0.50:
            quality_label = "Medium"
        else:
            quality_label = "Low"

        confirmation_value = float(a.confirmation)
        if confirmation_value >= 0.70:
            confirmation_label = "Strong"
        elif confirmation_value >= 0.40:
            confirmation_label = "Moderate"
        else:
            confirmation_label = "Weak"

        conflict_value = float(a.conflict)
        if conflict_value >= 0.70:
            conflict_label = "High"
        elif conflict_value >= 0.40:
            conflict_label = "Medium"
        else:
            conflict_label = "Low"

        direction_label = str(a.direction).title()

        return (
            f"{a.signal_name}: {a.evidence} | "
            f"Direction: {direction_label} | "
            f"Strength: {strength_label} | "
            f"Impact: {impact_label} | "
            f"Quality: {quality_label} | "
            f"Confirmation: {confirmation_label} | "
            f"Conflict: {conflict_label} | "
            f"Contribution: {float(a.contribution):+.3f}"
        )

    bullish_evidence = [
        _format_evidence(a)
        for a in bullish_evidence_items
    ]

    bearish_evidence = [
        _format_evidence(a)
        for a in bearish_evidence_items
    ]

    if direction == "BULLISH":
        thesis = (
            f"Market bias is bullish based on evidence-adjusted signals "
            f"with {intelligence_cov * 100:.0f}% effective intelligence coverage."
        )
    elif direction == "BEARISH":
        thesis = (
            f"Market bias is bearish based on evidence-adjusted signals "
            f"with {intelligence_cov * 100:.0f}% effective intelligence coverage."
        )
    else:
        thesis = (
            f"Market bias is neutral because bullish and bearish evidence "
            f"remain relatively balanced with {intelligence_cov * 100:.0f}% "
            f"effective intelligence coverage."
        )

    if raw.get("earnings_catalyst_risk"):
        symbols = raw.get("earnings_upcoming_symbols") or []
        catalyst_text = "Upcoming SEC-verified earnings catalyst is inside the forecast horizon"
        if symbols:
            catalyst_text += ": " + ", ".join(map(str, symbols))
        thesis += " " + catalyst_text + ". Future EPS actual/estimate is not used before SEC reveal."

    invalidation = _build_invalidation(
        direction,
        signals,
        raw,
    )

    historical_mode = str(snapshot.get("status", "")).upper().startswith("HISTORICAL")

    if historical_mode:
        source_status = {
            "market": (
                f"Historical point-in-time market "
                f"{raw.get('provider_quotes_available', 0)}/"
                f"{raw.get('provider_quotes_requested', 0)}"
            ),
            "news": (
                "Historical advanced news"
                if raw.get("historical_news_evidence") == "available"
                else "missing"
            ),
            "macro": (
                "Historical macro neutral / live parity"
                if raw.get("historical_macro_evidence")
                else "missing"
            ),
            "earnings": (
                "SEC-verified released earnings"
                if raw.get("historical_earnings_evidence") == "released_verified"
                else (
                    "Upcoming SEC-verified earnings catalyst"
                    if raw.get("historical_earnings_evidence") == "upcoming_verified_catalyst"
                    else "missing"
                )
            ),
            "liquidity": (
                "Historical NQ 5m liquidity"
                if raw.get("nq_liquidity_evidence") == "available"
                else "missing"
            ),
        }
    else:
        source_status = {
            "market": (
                "Finnhub live"
                if raw.get("provider_quotes_available")
                else "missing"
            ),
            "news": (
                "NewsAPI live"
                if raw.get("news") is not None
                else "missing"
            ),
            "macro": (
                "FRED live"
                if raw.get("us10y") is not None
                else "missing"
            ),
            "earnings": (
                "Finnhub earnings"
                if raw.get("earnings") is not None
                else "missing"
            ),
            "liquidity": (
                "NQ liquidity"
                if raw.get("liquidity_signal") is not None
                else "missing"
            ),
        }

    return Forecast(
        symbol="NQ",
        horizon_hours=CFG.horizon_hours,
        direction=direction,
        bullish_probability=round(bullish_probability, 1),
        bearish_probability=round(bearish_probability, 1),
        confidence=round(confidence, 1),
        regime=regime,
        status=status,
        score=round(intelligent_score, 3),
        signals=signals,
        invalidation=invalidation,
        generated_at=str(snapshot.get("timestamp") or datetime.now(timezone.utc).isoformat()),
        data_coverage=round(coverage, 3),
        source_status=source_status,
        thesis=thesis,
        bullish_evidence=bullish_evidence,
        bearish_evidence=bearish_evidence,
        intelligence_coverage=round(intelligence_cov, 3),
    )
