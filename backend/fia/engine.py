# PHASE23_DATA_RELIABILITY_V1
# PHASE22_TRUTH_CONSISTENCY_V1
from datetime import datetime, timezone
from math import exp

from .config import Config
from .models import Signal, Forecast
from .phase22_truth import validate_truth
from .intelligence import intelligent_score as calculate_evidence_score, intelligence_coverage, evidence_summary, intelligence_confidence, nasdaq_impact_direction, top_nasdaq_drivers

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
    "Equal-weight participation": 0.90,
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
    if value in {"fresh", "recent", "request_live", "live_cached"}:
        return 0.95
    if value in {"aging", "delayed"}:
        return 0.70
    if value in {"fallback"}:
        return 0.65
    if value in {"stale", "stale_cached_rate_limit", "stale_cached_provider_error"}:
        return 0.50
    if value in {"old"}:
        return 0.35
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
    """Weighted DATA availability/freshness coverage.

    Phase 22 definition:
      data_coverage = how much expected input weight is actually available.
    Source quality belongs to intelligence_coverage, not data availability.
    """
    total_weight = sum(max(0.0, float(s.weight)) for s in signals)
    if total_weight <= 0:
        return 0.0

    available_weight = sum(
        max(0.0, float(s.weight)) * _freshness_factor(s.freshness)
        for s in signals
    )
    return clamp(available_weight / total_weight, 0.0, 1.0)

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

    if raw.get("earnings") is not None:
        invalidation.append(
            "Major earnings/guidance surprise changes the leadership impulse"
        )

    return invalidation


def build_forecast(snapshot: dict) -> Forecast:
    raw = snapshot.get("data", {})
    source_health = raw.get("source_health") if isinstance(raw.get("source_health"), dict) else {}

    signals = []

    def source_freshness(source_name: str, score):
        # Signal freshness follows provider truth. A numeric value from a stale or
        # fallback source must not silently receive full live evidence weight.
        if score is None:
            return "missing"
        item = source_health.get(source_name) if isinstance(source_health, dict) else None
        if not isinstance(item, dict):
            return "live"  # backward-compatible for historical/test snapshots without Phase23 metadata
        if not item.get("available"):
            return "missing"
        status=str(item.get("status") or "").lower()
        freshness=str(item.get("freshness") or "").lower()
        if "stale" in status or "stale" in freshness:
            return "stale"
        if item.get("fallback") or status == "fallback" or freshness == "fallback":
            return "fallback"
        if freshness in {"delayed","aging"}:
            return "delayed"
        if freshness in {"recent","fresh"}:
            return "recent"
        if status in {"missing","error"}:
            return "missing"
        return "live"

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
        ("NQ structure", raw.get("nq_structure"), 0.20,
         "PROXY: QQQ 60m completed-bar structure. NOT NQ futures.", "candles"),
        ("SPX confirmation", raw.get("spx_confirmation"), 0.10,
         "PROXY: SPY normalised percent change. NOT an SPX divergence statistic.", "market_quotes"),
        ("DXY", raw.get("dxy"), 0.08, "US dollar pressure on NASDAQ risk assets", "dxy"),
        ("US10Y", raw.get("us10y"), 0.07, "US 10Y yield / rates pressure", "us10y"),
        ("Mega-cap leadership", raw.get("mega_cap"), 0.20, "Impact-weighted NASDAQ mega-cap leadership", "market_quotes"),
        ("Semiconductors", raw.get("semis"), 0.12, "AI / semiconductor leadership", "market_quotes"),
        ("Equal-weight participation", raw.get("breadth"), 0.08,
         "Equal-weighted mean change across the 15 tracked large caps (NOT market breadth)", "market_quotes"),
        ("News", raw.get("news"), 0.07, "Market-moving news sentiment", "news"),
        ("Macro calendar", raw.get("macro"), 0.04, "Scheduled macro-event risk", "macro"),
        ("Earnings/guidance", raw.get("earnings"), 0.04, "Earnings and guidance impulse", "earnings"),
    ]

    for name, value, weight, detail, source_name in adapters:
        add(name, value, weight, detail, source_freshness(source_name, value))

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
    elif candle_health.startswith("derived"):
        # V6.6.2: structure inferred from a quote scalar is a PROXY, not candle
        # evidence. It must not earn the same coverage as a real candle series.
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

    # Phase 21 validated decision policy:
    # remove the 55/45 prediction neutral band.
    # Use the same one-decimal probability exposed by the FIA result/UI
    # so the displayed probability and direction cannot disagree around 50%.
    decision_probability = round(bullish_probability, 1)

    # V6.6.2 NO_EDGE DISCIPLINE.
    # Phase 21 removed the 55/45 *probability* neutral band, and that stays removed:
    # we do NOT abstain merely because an estimate sits near 50. We abstain when there
    # is no information to estimate from. Those are different things.
    #
    # Before this change the engine emitted BULLISH at exactly 50.0 with zero evidence,
    # so "direction" was never absent and NO_EDGE was unreachable in the live forecast
    # the UI reads.
    _live_signal_count = sum(
        1 for s in signals
        if getattr(s, "score", None) is not None
        and float(getattr(s, "score", 0.0) or 0.0) != 0.0
        and str(getattr(s, "freshness", "")).lower() not in ("missing", "unknown", "")
    )
    _no_edge = (_live_signal_count == 0) or (float(intelligence_cov or 0.0) <= 0.0)

    if _no_edge:
        direction = "NO_EDGE"
        # An abstention is not a 50/50 forecast; it is the absence of a forecast.
        bullish_probability = 50.0
        bearish_probability = 50.0
        decision_probability = 50.0
        confidence = 0.0
    elif decision_probability >= 50.0:
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

    invalidation = _build_invalidation(
        direction,
        signals,
        raw,
    )

    # Phase 23: expose the same provider truth used by signal freshness.

    def _source_label(name, fallback):
        item = source_health.get(name) or {}
        source = str(item.get("source") or fallback)
        status_value = str(item.get("status") or "unknown")
        freshness_value = str(item.get("freshness") or "unknown")
        return f"{source} | {status_value} | {freshness_value}"

    source_status = {
        "market": _source_label(
            "market_quotes",
            "Finnhub" if raw.get("provider_quotes_available") else "missing",
        ),
        "news": _source_label(
            "news",
            str(raw.get("news_status") or "missing"),
        ),
        "macro": _source_label(
            "macro",
            str(raw.get("macro_status") or "missing"),
        ),
        "earnings": _source_label(
            "earnings",
            "Finnhub earnings" if raw.get("earnings") is not None else "missing",
        ),
        "dxy": _source_label(
            "dxy",
            str(raw.get("dxy_source") or "missing"),
        ),
        "us10y": _source_label(
            "us10y",
            str(raw.get("us10y_source") or "missing"),
        ),
        "provider_health": str(
            (raw.get("provider_health") or {}).get("overall")
            or raw.get("provider_health_status")
            or "unknown"
        ),
    }

    consistency = validate_truth(
        direction=direction,
        thesis=thesis,
        bullish_probability=round(bullish_probability, 1),
        bearish_probability=round(bearish_probability, 1),
        signals=signals,
        raw=raw,
    )

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
        generated_at=datetime.now(timezone.utc).isoformat(),
        data_coverage=round(coverage, 3),
        source_status=source_status,
        thesis=thesis,
        bullish_evidence=bullish_evidence,
        bearish_evidence=bearish_evidence,
        intelligence_coverage=round(intelligence_cov, 3),
        consistency=consistency,
    )
