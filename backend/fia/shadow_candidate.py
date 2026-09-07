"""SHADOW CANDIDATE C1 — correlation-aware evidence normalisation.

STATUS: SHADOW ONLY. Never touches a published probability. BASE_FIA is and
remains the production incumbent.

THE MEASURED DEFECT
-------------------
Across 261 point-in-time checkpoints (2025-09-01..2026-08-31), the five
equity-family drivers are near-collinear:

    NQ structure  <-> Equal-weight participation   r = +0.917
    NQ structure  <-> SPX confirmation             r = +0.913
    Mega-cap      <-> Equal-weight participation   r = +0.892
    Semiconductors<-> Equal-weight participation   r = +0.860
    Mega-cap      <-> Semiconductors               r = +0.602   (weakest pair)

    mean |r| = 0.829
    first eigenvalue explains 86.5% of block variance
    effective independent signals = 1.32  (inverse-Herfindahl of the spectrum)

BASE_FIA treats those five as five independent confirmations. They carry
roughly 1.3 signals' worth of information, an over-counting factor of ~3.8x.
Meanwhile the two genuinely orthogonal inputs are nearly uncorrelated with the
block and with each other (equity<->DXY r = 0.12..0.22, equity<->US10Y
r = 0.075..0.109, DXY<->US10Y r = 0.040) and carry the least weight.

THE CANDIDATE
-------------
Group drivers by measured ancestry. For a cluster with nominal count n and
measured effective count e, scale its weights by lambda = e/n, then renormalise
across all clusters. Singletons keep lambda = 1.0.

    lambda(equity) = 1.32 / 5 = 0.264

This is a REDISTRIBUTION, not a magnitude cut: shrinking the equity block
mechanically raises every other driver's share. That is the intended effect and
also the main risk -- see FAILURE MODES.

WHY THIS SHOULD PREDICT NQ
--------------------------
4H: intraday moves are dominated by one common equity factor. Counting it five
times inflates apparent agreement precisely when the five drivers are saying one
thing, which is exactly when BASE_FIA is most confident and most likely to be
confidently wrong.
8H: over a longer horizon, rates and the dollar carry information the equity
complex does not yet reflect. Their measured orthogonality is the reason to give
them a larger share.

FAILURE MODES (stated in advance, before any result exists)
-----------------------------------------------------------
1. The redistribution raises News, whose production scorer is an unvalidated
   keyword count. A candidate win driven mainly by News weight is luck, not
   edge, and must be rejected on those grounds.
2. lambda is estimated from ONE 261-row window and may be regime-dependent.
3. On degraded days the independent inputs are exactly the missing ones, so the
   candidate may abstain more often than BASE. That may be correct behaviour or
   merely less useful; only the paired comparison can say.
4. The correlation matrix is FROZEN here on purpose. Re-estimating it after
   seeing forward losses would be fitting to the test set.

FALSIFICATION
-------------
Paired Brier on the same unseen locked rows, 4H and 8H separately. If the 95%
bootstrap CI of the paired delta does not exclude zero, the candidate does not
win. Inconclusive keeps it in shadow; clearly worse rejects it.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

CANDIDATE_ID = "C1_CORRELATION_AWARE_NORMALISATION"
CANDIDATE_VERSION = "1.0.0"

# Ancestry clusters. Membership is by measured shared source, not by name.
EQUITY_CLUSTER = (
    "NQ structure",              # QQQ 60m completed-bar structure
    "SPX confirmation",          # SPY normalised percent change
    "Mega-cap leadership",       # weighted basket of the same 10 names
    "Semiconductors",            # 7-name subset of the same basket
    "Equal-weight participation",  # equal-weighted mean of all 15
)

# Measured on 261 PIT checkpoints. FROZEN: re-estimating after seeing forward
# outcomes would be fitting to the test set.
EQUITY_EFFECTIVE_SIGNALS = 1.32
EQUITY_NOMINAL_SIGNALS = 5
EQUITY_LAMBDA = EQUITY_EFFECTIVE_SIGNALS / EQUITY_NOMINAL_SIGNALS  # 0.264

MEASUREMENT = {
    "rows": 261,
    "window": "2025-09-01..2026-08-31",
    "method": "inverse-Herfindahl of the eigenvalue spectrum of the 5x5 Pearson matrix",
    "mean_abs_r": 0.829,
    "first_eigenvalue_share": 0.865,
    "frozen": True,
}


def cluster_lambda(name: str) -> float:
    return EQUITY_LAMBDA if name in EQUITY_CLUSTER else 1.0


def effective_evidence_count(present: Any) -> float:
    """Effective independent signals among the drivers actually present."""
    names = [str(n) for n in (present or [])]
    eq = [n for n in names if n in EQUITY_CLUSTER]
    others = [n for n in names if n not in EQUITY_CLUSTER]
    eq_eff = 0.0
    if eq:
        # Scale the measured block effective count by how much of the block is
        # present. A single equity driver alone is still one real signal.
        eq_eff = max(1.0, EQUITY_EFFECTIVE_SIGNALS * len(eq) / EQUITY_NOMINAL_SIGNALS)
        eq_eff = min(eq_eff, float(len(eq)))
    return round(eq_eff + float(len(others)), 3)


def score_from_packet(drivers: Any) -> Optional[Dict[str, Any]]:
    """Recompute a probability from the SAME stored driver packet BASE used.

    Deliberately reads the locked evidence rather than recomputing evidence:
    the candidate cannot receive different, extra or fresher information than
    BASE, because it is reading BASE's own immutable bytes.

    Returns None when the packet carries no usable driver, so the candidate
    abstains exactly where the evidence is absent.
    """
    rows = []
    for d in (drivers or []):
        if not isinstance(d, dict):
            continue
        name = str(d.get("name") or "")
        try:
            score = float(d.get("score"))
            weight = float(d.get("effective_weight"))
        except (TypeError, ValueError):
            continue
        if weight == 0:
            continue
        rows.append((name, score, weight))
    if not rows:
        return None

    num = 0.0
    den = 0.0
    contrib = {}
    for name, score, weight in rows:
        lam = cluster_lambda(name)
        w = weight * lam
        num += score * w
        den += abs(w)
        contrib[name] = {"lambda": lam, "base_weight": weight,
                         "candidate_weight": round(w, 6)}
    if den == 0:
        return None

    normalised = max(-1.0, min(1.0, num / den))
    # Same mapping BASE uses: p = 50 + 25 * clamp(score). The candidate changes
    # the WEIGHTING of evidence, not the probability mapping or the thresholds.
    bull = round(50.0 + 25.0 * normalised, 3)
    present = [r[0] for r in rows]
    return {
        "candidate_id": CANDIDATE_ID,
        "candidate_version": CANDIDATE_VERSION,
        "bullish_probability": bull,
        "bearish_probability": round(100.0 - bull, 3),
        "weighted_score": round(normalised, 6),
        "effective_evidence_count": effective_evidence_count(present),
        "nominal_driver_count": len(present),
        "equity_drivers_present": sum(1 for n in present if n in EQUITY_CLUSTER),
        "equity_lambda": EQUITY_LAMBDA,
        "contributions": contrib,
        "production_influence": False,
        "measurement": MEASUREMENT,
    }
