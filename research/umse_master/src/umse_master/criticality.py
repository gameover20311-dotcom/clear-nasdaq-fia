"""Criticality diagnostics with explicit component availability.

WHAT THE AUDIT PROVED
---------------------
Three separate defects, all of which made absence of evidence look like
evidence of calm:

  * Every sub-estimator returned 0.0 when it had too little data, and the index
    averaged those zeros. With no data at all the index was 0.0000, a confident
    "calm" reading with no INSUFFICIENT_DATA signal anywhere.
  * The pipeline passed the book's `depth_imbalance` into the `liquidity_change`
    parameter. That is a cross-sectional asymmetry at one instant, not a change
    over time. A balanced book drove it toward zero, the 1e-9 denominator floor
    took over, and the elasticity component saturated at exactly 1.0 -- so the
    calmest possible book scored maximum criticality.
  * `rho_c = min(1.0, rho)` saturated, making rho = 1.0, 2.0 and 10.0 produce an
    identical index. A criticality measure that cannot separate critical from
    explosive fails at the one job it has.

REPAIR
------
Components are now Optional. A component that cannot be computed is named in
`unavailable_components` and is absent from `components`; it is never silently
zero. The index is the mean of the components that ARE available, and only when
at least MIN_COMPONENTS of them are, otherwise it is None with an explicit
status. Elasticity requires a genuine temporal liquidity change and returns
None when one is not supplied. The rho transform is now strictly monotone.

This is a candidate research diagnostic. `calibrated` is always False.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import math
from statistics import pvariance
from typing import Dict, Mapping, Optional, Sequence, Tuple

# Below this relative change the elasticity denominator is noise, not signal.
MIN_RELATIVE_LIQUIDITY_CHANGE = 1e-6
# Fewer than this many available components and the index is not meaningful.
MIN_COMPONENTS = 3


class ComponentStatus(str, Enum):
    OBSERVED = "OBSERVED"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    NOT_IDENTIFIABLE_WITH_CURRENT_DATA = "NOT_IDENTIFIABLE_WITH_CURRENT_DATA"


def lag1_autocorrelation(values: Sequence[float]) -> Optional[float]:
    xs = [float(x) for x in values]
    if len(xs) < 3:
        return None
    mean = sum(xs) / len(xs)
    denom = sum((x - mean) ** 2 for x in xs)
    if denom <= 1e-12:
        return None
    num = sum((xs[i] - mean) * (xs[i - 1] - mean) for i in range(1, len(xs)))
    return max(-1.0, min(1.0, num / denom))


def normalized_variance(values: Sequence[float]) -> Optional[float]:
    xs = [float(x) for x in values]
    if len(xs) < 2:
        return None
    scale = sum(abs(x) for x in xs) / len(xs)
    if scale <= 1e-12:
        # A series with no scale gives no scale-free variance. Saying 0.0 here
        # was one of the paths that made empty data look calm.
        return None
    return max(0.0, pvariance(xs) / (scale * scale))


def recovery_time_fraction(
    responses: Sequence[float], threshold_fraction: float = 0.25
) -> Optional[float]:
    xs = [abs(float(x)) for x in responses]
    if len(xs) < 2 or xs[0] <= 0:
        return None
    threshold = xs[0] * threshold_fraction
    for i, x in enumerate(xs[1:], start=1):
        if x <= threshold:
            return i / (len(xs) - 1)
    return 1.0


def liquidity_elasticity(
    relative_price_change: Optional[float],
    relative_liquidity_change: Optional[float],
    *,
    min_relative_liquidity_change: float = MIN_RELATIVE_LIQUIDITY_CHANGE,
) -> Optional[float]:
    """|relative price change| / |relative liquidity change| over an interval.

    BOTH arguments are changes BETWEEN two observations. A single book snapshot
    contains no liquidity change and therefore cannot produce an elasticity;
    callers in that position must pass None and accept an unavailable
    component. Passing a cross-sectional statistic such as depth imbalance here
    is the defect this signature exists to prevent.

    Returns None rather than dividing by a floor when the liquidity change is
    too small to carry information.
    """
    if relative_price_change is None or relative_liquidity_change is None:
        return None
    dp = float(relative_price_change)
    dl = float(relative_liquidity_change)
    if not math.isfinite(dp) or not math.isfinite(dl):
        return None
    if abs(dl) < min_relative_liquidity_change:
        return None
    return abs(dp) / abs(dl)


@dataclass(frozen=True)
class CriticalityDiagnostics:
    components: Mapping[str, float]
    unavailable_components: Tuple[str, ...]
    candidate_index: Optional[float]
    status: ComponentStatus
    hawkes_spectral_radius: Optional[float] = None
    calibrated: bool = False
    predictive: bool = False


def compute_criticality(
    *,
    hawkes_spectral_radius: Optional[float],
    state_series: Sequence[float],
    recovery_responses: Sequence[float],
    relative_price_change: Optional[float] = None,
    relative_liquidity_change: Optional[float] = None,
    min_components: int = MIN_COMPONENTS,
) -> CriticalityDiagnostics:
    components: Dict[str, float] = {}
    unavailable = []

    if hawkes_spectral_radius is None or not math.isfinite(float(hawkes_spectral_radius)):
        unavailable.append("hawkes_spectral_radius")
    else:
        rho = max(0.0, float(hawkes_spectral_radius))
        # Strictly monotone in rho, so critical and explosive stay distinct.
        components["hawkes_spectral_radius"] = rho / (1.0 + rho)

    acf = lag1_autocorrelation(state_series)
    if acf is None:
        unavailable.append("lag1_autocorrelation")
    else:
        components["lag1_autocorrelation"] = max(0.0, acf)

    var_raw = normalized_variance(state_series)
    if var_raw is None:
        unavailable.append("normalized_variance")
    else:
        components["normalized_variance"] = var_raw / (1.0 + var_raw)

    recovery = recovery_time_fraction(recovery_responses)
    if recovery is None:
        unavailable.append("recovery_time_fraction")
    else:
        components["recovery_time_fraction"] = recovery

    elasticity = liquidity_elasticity(relative_price_change, relative_liquidity_change)
    if elasticity is None:
        unavailable.append("liquidity_elasticity")
    else:
        components["liquidity_elasticity"] = elasticity / (1.0 + elasticity)

    if len(components) < min_components:
        return CriticalityDiagnostics(
            components=dict(components),
            unavailable_components=tuple(unavailable),
            candidate_index=None,
            status=ComponentStatus.INSUFFICIENT_DATA,
            hawkes_spectral_radius=hawkes_spectral_radius,
            calibrated=False,
        )

    index = sum(components.values()) / len(components)
    return CriticalityDiagnostics(
        components=dict(components),
        unavailable_components=tuple(unavailable),
        candidate_index=max(0.0, min(1.0, index)),
        status=ComponentStatus.OBSERVED,
        hawkes_spectral_radius=hawkes_spectral_radius,
        calibrated=False,
    )
