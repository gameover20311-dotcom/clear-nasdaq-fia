from __future__ import annotations

from dataclasses import dataclass
from typing import List, Dict, Tuple
import re


@dataclass
class EvidenceAssessment:
    signal_name: str
    direction: str
    strength: float
    freshness: float
    source_quality: float
    market_impact: float
    confirmation: float
    conflict: float
    effective_weight: float
    contribution: float
    evidence: str


_HIGH_IMPACT = {
    "cpi", "pce", "nfp", "fed", "fomc", "dxy", "us10y",
    "nvda", "msft", "aapl", "amzn", "meta", "googl", "avgo",
    "qqq", "nq", "nasdaq", "liquidity",
}

_MEDIUM_IMPACT = {
    "spy", "spx", "semis", "sox", "breadth", "earnings",
    "macro", "news", "tsla",
}


def _key(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (name or "").lower())


def nasdaq_impact_direction(name: str, direction: str) -> str:
    """
    Translate raw signal direction into its expected NASDAQ impact direction.

    Some signals move in the same direction as NASDAQ, while macro/rates
    signals such as DXY and US10Y can have an inverse relationship.
    """
    key = _key(name)
    raw = (direction or "").lower()

    inverse_keys = {
        "dxy",
        "us10y",
    }

    if key in inverse_keys:
        if raw == "bullish":
            return "Bearish"
        if raw == "bearish":
            return "Bullish"

    if raw == "bullish":
        return "Bullish"
    if raw == "bearish":
        return "Bearish"

    return "Neutral"


def market_impact(name: str) -> float:
    key = _key(name)

    if key in _HIGH_IMPACT:
        return 1.00

    if key in _MEDIUM_IMPACT:
        return 0.70

    return 0.35


def freshness_score(freshness: str) -> float:
    value = (freshness or "").lower()

    if any(x in value for x in ("very fresh", "very_fresh", "live", "now")):
        return 1.00

    if any(x in value for x in ("fresh", "recent")):
        return 0.90

    if any(x in value for x in ("moderate", "medium")):
        return 0.65

    if any(x in value for x in ("old", "stale")):
        return 0.30

    return 0.55


def source_quality(detail: str) -> float:
    text = (detail or "").lower()

    high_quality = (
        "fred", "federal reserve", "fed", "finnhub",
        "official", "earnings", "sec", "cpi", "pce", "nfp"
    )

    if any(x in text for x in high_quality):
        return 1.00

    if text.strip():
        return 0.75

    return 0.50


def evidence_strength(score: float) -> float:
    return min(1.0, abs(float(score)))


def assess_signals(signals) -> List[EvidenceAssessment]:
    if not signals:
        return []

    bullish = sum(1 for s in signals if float(s.score) > 0.15)
    bearish = sum(1 for s in signals if float(s.score) < -0.15)

    total_directional = bullish + bearish
    assessments = []

    for signal in signals:
        score = float(signal.score)
        direction = (
            "bullish" if score > 0.05
            else "bearish" if score < -0.05
            else "neutral"
        )

        confirmation = 0.0
        conflict = 0.0

        # Confirmation strength is based on same-direction
        # signal strength multiplied by market impact.
        same_direction_strength = sum(
            abs(float(s.score)) * market_impact(getattr(s, "name", ""))
            for s in signals
            if (
                (score > 0.15 and float(s.score) > 0.15)
                or
                (score < -0.15 and float(s.score) < -0.15)
            )
        )

        total_directional_strength = sum(
            abs(float(s.score)) * market_impact(getattr(s, "name", ""))
            for s in signals
            if abs(float(s.score)) > 0.15
        )

        if total_directional_strength > 0:
            confirmation = min(
                1.0,
                same_direction_strength / total_directional_strength
            )

        if direction == "bullish" and bullish > 1:
            confirmation = min(1.0, bullish / max(1, total_directional))
        elif direction == "bearish" and bearish > 1:
            confirmation = min(1.0, bearish / max(1, total_directional))

        # Conflict severity considers both opposing signal strength
        # and the market impact of the opposing evidence.
        opposing_strength = 0.0

        if direction == "bullish":
            opposing_strength = sum(
                abs(float(s.score)) * market_impact(getattr(s, "name", ""))
                for s in signals
                if float(s.score) < -0.15
            )
        elif direction == "bearish":
            opposing_strength = sum(
                abs(float(s.score)) * market_impact(getattr(s, "name", ""))
                for s in signals
                if float(s.score) > 0.15
            )

        total_impact_strength = sum(
            abs(float(s.score)) * market_impact(getattr(s, "name", ""))
            for s in signals
            if abs(float(s.score)) > 0.15
        )

        if total_impact_strength > 0:
            conflict = min(
                1.0,
                opposing_strength / total_impact_strength
            )
        else:
            conflict = 0.0

        strength = evidence_strength(score)
        fresh = freshness_score(getattr(signal, "freshness", "unknown"))
        quality = source_quality(getattr(signal, "detail", ""))
        impact = market_impact(getattr(signal, "name", ""))

        effective_weight = (
            max(0.0, float(signal.weight))
            * (0.50 + 0.50 * strength)
            * (0.50 + 0.50 * fresh)
            * (0.50 + 0.50 * quality)
            * impact
        )

        contribution = (
            score
            * effective_weight
            * (1.0 + 0.25 * confirmation)
            * (1.0 - 0.35 * conflict)
        )

        # Evidence direction must follow the actual signal score.
        # Positive score = bullish evidence, negative score = bearish evidence.
        if score > 0.15:
            direction = "bullish"
        elif score < -0.15:
            direction = "bearish"
        else:
            direction = "neutral"

        assessments.append(
            EvidenceAssessment(
                signal_name=getattr(signal, "name", ""),
                direction=direction,
                strength=round(strength, 3),
                freshness=round(fresh, 3),
                source_quality=round(quality, 3),
                market_impact=round(impact, 3),
                confirmation=round(confirmation, 3),
                conflict=round(conflict, 3),
                effective_weight=round(effective_weight, 4),
                contribution=round(contribution, 4),
                evidence=getattr(signal, "detail", "") or "No detailed evidence available.",
            )
        )

    return assessments


def intelligent_score(signals) -> Tuple[float, List[EvidenceAssessment]]:
    assessments = assess_signals(signals)

    if not assessments:
        return 0.0, []

    numerator = sum(a.contribution for a in assessments)
    denominator = sum(a.effective_weight for a in assessments)

    if denominator <= 0:
        return 0.0, assessments

    score = numerator / denominator
    return max(-1.0, min(1.0, score)), assessments


def intelligence_coverage(signals) -> float:
    if not signals:
        return 0.0

    total_weight = sum(max(0.0, float(s.weight)) for s in signals)

    if total_weight <= 0:
        return 0.0

    effective = 0.0

    for signal in signals:
        impact = market_impact(getattr(signal, "name", ""))
        fresh = freshness_score(getattr(signal, "freshness", "unknown"))
        quality = source_quality(getattr(signal, "detail", ""))

        effective += (
            max(0.0, float(signal.weight))
            * impact
            * (0.50 + 0.50 * fresh)
            * (0.50 + 0.50 * quality)
        )

    # Normalize against the maximum possible quality-adjusted coverage.
    max_possible = total_weight

    return max(0.0, min(1.0, effective / max_possible))



def intelligence_confidence(
    assessments: List[EvidenceAssessment],
    coverage: float,
) -> float:
    """Calculate confidence from evidence quality, confirmation and conflict."""

    if not assessments:
        return 0.0

    total_weight = sum(a.effective_weight for a in assessments)

    if total_weight <= 0:
        return 0.0

    avg_quality = sum(
        a.effective_weight * a.source_quality
        for a in assessments
    ) / total_weight

    avg_freshness = sum(
        a.effective_weight * a.freshness
        for a in assessments
    ) / total_weight

    avg_confirmation = sum(
        a.effective_weight * a.confirmation
        for a in assessments
    ) / total_weight

    avg_conflict = sum(
        a.effective_weight * a.conflict
        for a in assessments
    ) / total_weight

    confidence = (
        0.25 * avg_quality
        + 0.20 * avg_freshness
        + 0.25 * avg_confirmation
        + 0.30 * coverage
        - 0.30 * avg_conflict
    )

    return max(0.0, min(1.0, confidence))

def evidence_summary(assessments: List[EvidenceAssessment]):
    bullish = [
        a for a in assessments
        if a.direction == "bullish"
    ]

    bearish = [
        a for a in assessments
        if a.direction == "bearish"
    ]

    bullish.sort(key=lambda x: x.contribution, reverse=True)
    bearish.sort(key=lambda x: abs(x.contribution), reverse=True)

    return bullish[:5], bearish[:5]


def top_nasdaq_drivers(assessments, limit=3):
    """
    Return the strongest NASDAQ drivers based on absolute contribution.
    """
    ranked = sorted(
        assessments,
        key=lambda a: abs(float(a.contribution)),
        reverse=True,
    )
    return ranked[:limit]
