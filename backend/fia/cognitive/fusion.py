from __future__ import annotations

from typing import Dict, List, Optional

from .models import SpecialistView, RegimeView, AnalogyView, CriticView
from .utils import clamp, direction_from_probability, score_to_probability

BASE_WEIGHTS = {
    "Price Structure AI": .13,
    "Multi-timeframe Trend AI": .07,
    "NQ/ES/SPX Confirmation AI": .07,
    "Mega-cap Leadership AI": .11,
    "Semiconductor AI": .07,
    "Breadth/Internals AI": .06,
    "Rates & Yield AI": .07,
    "Genuine Dollar/DXY AI": .06,
    "Macro Surprise AI": .07,
    "Fed Communication AI": .05,
    "News Event AI": .06,
    "Earnings & Guidance AI": .06,
    "Liquidity & Session AI": .05,
    "Volatility & Options AI": .03,
    "Market Regime AI": .04,
}

REGIME_MULTIPLIERS = {
    "TREND": {"Price Structure AI":1.25,"Multi-timeframe Trend AI":1.22,"Mega-cap Leadership AI":1.18,"Semiconductor AI":1.12,"Breadth/Internals AI":1.10},
    "MACRO_EVENT": {"Macro Surprise AI":1.45,"Fed Communication AI":1.35,"Rates & Yield AI":1.28,"Genuine Dollar/DXY AI":1.22,"News Event AI":1.15},
    "EARNINGS_LED": {"Earnings & Guidance AI":1.45,"Mega-cap Leadership AI":1.25,"Semiconductor AI":1.15,"News Event AI":1.15},
    "HIGH_VOLATILITY": {"Volatility & Options AI":1.45,"Liquidity & Session AI":1.30,"Rates & Yield AI":1.15,"Price Structure AI":1.10},
    "RANGE": {"Liquidity & Session AI":1.35,"NQ/ES/SPX Confirmation AI":1.20,"Price Structure AI":1.08},
    "CONFLICTED": {"NQ/ES/SPX Confirmation AI":1.15,"Macro Surprise AI":1.10,"News Event AI":1.10,"Market Regime AI":1.20},
    "TRANSITION": {"NQ/ES/SPX Confirmation AI":1.18,"Price Structure AI":1.10,"Rates & Yield AI":1.08,"Market Regime AI":1.12},
}

CORRELATION_CAPS = {
    "tech_internal": ({"Mega-cap Leadership AI","Semiconductor AI","Breadth/Internals AI"}, .28),
    "price_cluster": ({"Price Structure AI","Multi-timeframe Trend AI","NQ/ES/SPX Confirmation AI"}, .30),
    "macro_cluster": ({"Rates & Yield AI","Genuine Dollar/DXY AI","Macro Surprise AI","Fed Communication AI"}, .32),
}


def _effective_weights(specialists: List[SpecialistView], regime: RegimeView) -> Dict[str,float]:
    spec = {s.name:s for s in specialists}
    mult = REGIME_MULTIPLIERS.get(regime.primary,{})
    raw: Dict[str,float] = {}
    for name, base in BASE_WEIGHTS.items():
        s = spec.get(name)
        if not s or s.reliability <= 0:
            continue
        rel = max(.05, s.reliability)
        raw[name] = base * mult.get(name,1.0) * rel

    # Cap correlated families before normalizing.
    for _, (members, cap) in CORRELATION_CAPS.items():
        total = sum(raw.get(n,0.0) for n in members)
        overall = sum(raw.values())
        if overall <= 0 or total <= 0:
            continue
        max_group = cap * overall / max(1e-9, 1-cap)
        if total > max_group:
            factor = max_group / total
            for n in members:
                if n in raw: raw[n] *= factor
    total = sum(raw.values())
    return {k:v/total for k,v in raw.items()} if total else {}


def fuse(specialists: List[SpecialistView], regime: RegimeView,
         analogy: Optional[AnalogyView] = None, critic: Optional[CriticView] = None) -> Dict[str,object]:
    weights = _effective_weights(specialists, regime)
    by = {s.name:s for s in specialists}
    contributions = []
    score = 0.0
    for name, weight in weights.items():
        s = by[name]
        contribution = s.score * weight
        score += contribution
        contributions.append({"specialist":name,"weight":round(weight,4),"score":s.score,"reliability":s.reliability,"contribution":round(contribution,5)})

    specialist_probability = score_to_probability(score)
    analogy_weight = 0.0
    raw_probability = specialist_probability
    if analogy and analogy.available and analogy.bullish_probability is not None:
        analogy_weight = min(.18, .04 + .16 * min(1.0, analogy.effective_sample_size/20.0) * analogy.mean_similarity)
        raw_probability = specialist_probability*(1-analogy_weight) + float(analogy.bullish_probability)*analogy_weight

    if regime.primary == "CONFLICTED":
        raw_probability = 50.0 + (raw_probability-50.0)*.72
    elif regime.primary == "TRANSITION":
        raw_probability = 50.0 + (raw_probability-50.0)*.86

    if critic:
        raw_probability = 50.0 + (raw_probability-50.0)*(1.0-critic.reliability_penalty)

    raw_probability = max(2.0,min(98.0,raw_probability))
    return {
        "raw_bullish_probability": round(raw_probability,3),
        "raw_bearish_probability": round(100-raw_probability,3),
        "direction": direction_from_probability(raw_probability),
        "specialist_probability": round(specialist_probability,3),
        "analogy_weight": round(analogy_weight,4),
        "regime": regime.to_dict(),
        "weights": {k:round(v,5) for k,v in weights.items()},
        "contributions": sorted(contributions,key=lambda x:abs(x["contribution"]),reverse=True),
        "policy": "Regime- and reliability-aware transparent fusion with family correlation caps. Outcome labels never change live weights.",
    }
