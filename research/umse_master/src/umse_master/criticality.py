from __future__ import annotations

from dataclasses import dataclass
import math
from statistics import pvariance
from typing import Sequence


def lag1_autocorrelation(values: Sequence[float]) -> float:
    xs = [float(x) for x in values]
    if len(xs) < 3:
        return 0.0
    mean = sum(xs) / len(xs)
    denom = sum((x - mean) ** 2 for x in xs)
    if denom <= 1e-12:
        return 0.0
    num = sum((xs[i] - mean) * (xs[i - 1] - mean) for i in range(1, len(xs)))
    return max(-1.0, min(1.0, num / denom))


def normalized_variance(values: Sequence[float]) -> float:
    xs = [float(x) for x in values]
    if len(xs) < 2:
        return 0.0
    scale = max(1e-12, sum(abs(x) for x in xs) / len(xs))
    return max(0.0, pvariance(xs) / (scale * scale))


def recovery_time_fraction(responses: Sequence[float], threshold_fraction: float = 0.25) -> float:
    xs = [abs(float(x)) for x in responses]
    if len(xs) < 2 or xs[0] <= 0:
        return 0.0
    threshold = xs[0] * threshold_fraction
    for i, x in enumerate(xs[1:], start=1):
        if x <= threshold:
            return i / (len(xs) - 1)
    return 1.0


def liquidity_elasticity(price_change: float, liquidity_change: float) -> float:
    return abs(float(price_change)) / max(1e-9, abs(float(liquidity_change)))


@dataclass(frozen=True)
class CriticalityDiagnostics:
    hawkes_spectral_radius: float
    lag1_acf: float
    variance_component: float
    recovery_component: float
    liquidity_elasticity_component: float
    candidate_index: float
    calibrated: bool = False


def compute_criticality(
    *,
    hawkes_spectral_radius: float,
    state_series: Sequence[float],
    recovery_responses: Sequence[float],
    price_change: float,
    liquidity_change: float,
) -> CriticalityDiagnostics:
    rho = max(0.0, float(hawkes_spectral_radius))
    acf = lag1_autocorrelation(state_series)
    var_raw = normalized_variance(state_series)
    recovery = recovery_time_fraction(recovery_responses)
    elasticity = liquidity_elasticity(price_change, liquidity_change)
    rho_c = min(1.0, rho)
    acf_c = max(0.0, acf)
    var_c = var_raw / (1.0 + var_raw)
    elast_c = elasticity / (1.0 + elasticity)
    idx = (rho_c + acf_c + var_c + recovery + elast_c) / 5.0
    return CriticalityDiagnostics(rho, acf, var_c, recovery, elast_c, max(0.0, min(1.0, idx)), False)
