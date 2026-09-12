"""Paired BASE-vs-candidate validation and the confirmatory promotion gate.

WHAT THE AUDIT PROVED
---------------------
The previous gate passed on a single observation. `block_size` was clamped to
`min(block_size, n)`, so for n <= 5 the only legal block start was 0, every
resample was the identical series, and the 90% interval collapsed to a point
that trivially satisfied `ci[0] > 0`. The suite's own gate test then certified
this by constructing ten IDENTICAL rows, which is also a zero-variance sample,
and asserting that the gate passed.

Four structural defences replace that:

  1. A ConfirmatoryPlan must exist and must be registered BEFORE the data. N is
     preregistered, so a sample that does not match the plan exactly cannot be
     confirmatory. This is what blocks optional stopping.
  2. A circular block bootstrap, so every observation can begin a block and the
     resample distribution is not an artifact of the series edges.
  3. An effective-block floor. A bootstrap over fewer than MIN_EFFECTIVE_BLOCKS
     independent blocks has no resolution and is refused outright.
  4. Explicit degeneracy detection. If the resample distribution has no spread,
     the interval is not a confidence statement and the gate fails closed.

ON THE VALUE OF N
-----------------
MIN_EFFECTIVE_BLOCKS is a structural floor on the estimator, not a power
calculation and not a scientifically sufficient N. It is the point below which
the bootstrap stops meaning anything. The scientifically required N must come
from a preregistered power design against a target effect size, which does not
exist yet and is deliberately not invented here. Meeting the floor is necessary
and nowhere near sufficient.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import math
import random
from typing import Dict, Mapping, Optional, Sequence, Tuple

from .replay import ReplayClass

CLASSES = ("bullish", "bearish", "neutral")

# Structural floor on the block bootstrap, NOT a power-derived sample size.
MIN_EFFECTIVE_BLOCKS = 20
DEFAULT_BLOCK_SIZE = 5
DEFAULT_DRAWS = 2000
DEFAULT_SEED = 56
DEGENERACY_TOLERANCE = 1e-12
# Top-label ECE over 3 classes is badly biased when bins hold one or two rows.
MIN_ECE_SAMPLES = 50


def _probs(row: Mapping[str, float]) -> Dict[str, float]:
    vals = {k: float(row.get(k, 0.0)) for k in CLASSES}
    if any(not math.isfinite(v) or v < 0 for v in vals.values()):
        raise ValueError("invalid probability")
    total = sum(vals.values())
    if total <= 0:
        raise ValueError("probabilities require positive mass")
    return {k: v / total for k, v in vals.items()}


def multiclass_brier(probabilities: Mapping[str, float], outcome: str) -> float:
    if outcome not in CLASSES:
        raise ValueError(f"outcome must be one of {CLASSES}")
    p = _probs(probabilities)
    return sum((p[k] - (1.0 if k == outcome else 0.0)) ** 2 for k in CLASSES)


def paired_brier_differences(
    base: Sequence[Mapping[str, float]],
    candidate: Sequence[Mapping[str, float]],
    outcomes: Sequence[str],
) -> Tuple[float, ...]:
    """base_loss - candidate_loss. Positive means the candidate is better."""
    if not (len(base) == len(candidate) == len(outcomes)):
        raise ValueError("base, candidate and outcomes must have equal length")
    return tuple(multiclass_brier(b, y) - multiclass_brier(c, y)
                 for b, c, y in zip(base, candidate, outcomes))


@dataclass(frozen=True)
class BootstrapResult:
    lo: float
    hi: float
    mean: float
    degenerate: bool
    effective_blocks: int
    block_size: int
    draws: int
    samples: int
    usable: bool


def block_bootstrap_ci(
    values: Sequence[float],
    *,
    confidence: float = 0.90,
    block_size: int = DEFAULT_BLOCK_SIZE,
    draws: int = DEFAULT_DRAWS,
    seed: int = DEFAULT_SEED,
    min_effective_blocks: int = MIN_EFFECTIVE_BLOCKS,
) -> BootstrapResult:
    """Circular moving-block bootstrap of the mean, with degeneracy detection."""
    xs = [float(x) for x in values]
    n = len(xs)
    if block_size <= 0 or draws <= 0:
        raise ValueError("block_size and draws must be > 0")
    effective_blocks = n // block_size if block_size else 0
    if n == 0:
        return BootstrapResult(math.nan, math.nan, math.nan, True, 0,
                               block_size, draws, 0, False)
    if effective_blocks < min_effective_blocks:
        # Too few independent blocks for the interval to carry information.
        return BootstrapResult(math.nan, math.nan, sum(xs) / n, True,
                               effective_blocks, block_size, draws, n, False)

    rng = random.Random(seed)
    means = []
    for _ in range(draws):
        total = 0.0
        taken = 0
        while taken < n:
            start = rng.randrange(0, n)           # circular: any index may start
            for k in range(block_size):
                if taken >= n:
                    break
                total += xs[(start + k) % n]
                taken += 1
        means.append(total / n)
    means.sort()
    degenerate = (means[-1] - means[0]) <= DEGENERACY_TOLERANCE
    alpha = (1.0 - confidence) / 2.0
    lo = means[int(alpha * (draws - 1))]
    hi = means[int((1.0 - alpha) * (draws - 1))]
    return BootstrapResult(lo, hi, sum(xs) / n, degenerate, effective_blocks,
                           block_size, draws, n, not degenerate)


def expected_calibration_error(
    probabilities: Sequence[Mapping[str, float]],
    outcomes: Sequence[str],
    bins: int = 10,
    *,
    min_samples: int = MIN_ECE_SAMPLES,
) -> float:
    if len(probabilities) != len(outcomes):
        raise ValueError("length mismatch")
    if len(probabilities) < min_samples:
        # Top-label ECE on a handful of rows is dominated by its own bias.
        return float("nan")
    bucket_rows = [[] for _ in range(bins)]
    for p_raw, y in zip(probabilities, outcomes):
        p = _probs(p_raw)
        pred = max(CLASSES, key=lambda k: p[k])
        conf = p[pred]
        idx = min(bins - 1, int(conf * bins))
        bucket_rows[idx].append((conf, 1.0 if pred == y else 0.0))
    n = len(probabilities)
    ece = 0.0
    for rows in bucket_rows:
        if not rows:
            continue
        mean_conf = sum(x for x, _ in rows) / len(rows)
        accuracy = sum(y for _, y in rows) / len(rows)
        ece += len(rows) / n * abs(mean_conf - accuracy)
    return ece


@dataclass(frozen=True)
class ConfirmatoryPlan:
    """A preregistration record. It must exist before the data it judges.

    `preregistered_n` is the committed sample size. It is supplied by the
    caller's power design; this module does not invent one and refuses any
    sample whose size differs from it, which is what makes optional stopping
    structurally impossible rather than merely discouraged.
    """

    plan_id: str
    preregistered_n: int
    target_delta: float
    registered_at_utc: datetime
    evidence_class: ReplayClass
    alpha: float = 0.05
    block_size: int = DEFAULT_BLOCK_SIZE
    power_design_reference: str = "NOT_YET_DERIVED_REQUIRES_FORWARD_PILOT"

    def __post_init__(self) -> None:
        if not str(self.plan_id).strip():
            raise ValueError("plan_id must be non-empty")
        if int(self.preregistered_n) <= 0:
            raise ValueError("preregistered_n must be > 0")
        if not math.isfinite(float(self.target_delta)) or self.target_delta <= 0:
            raise ValueError("target_delta must be finite and > 0")
        if self.registered_at_utc.tzinfo is None:
            raise ValueError("registered_at_utc must be timezone-aware")
        object.__setattr__(self, "registered_at_utc",
                           self.registered_at_utc.astimezone(timezone.utc))

    @property
    def is_prospective(self) -> bool:
        """Only forward out-of-sample observations can confirm."""
        return self.evidence_class == ReplayClass.FORWARD_OOS


@dataclass(frozen=True)
class PairedValidationResult:
    n: int
    base_mean_brier: float
    candidate_mean_brier: float
    mean_delta: float
    delta_ci90: Tuple[float, float]
    base_ece: float
    candidate_ece: float
    target_delta: float
    effective_blocks: int
    degenerate_bootstrap: bool
    confirmatory_eligible: bool
    promotion_gate_pass: bool
    blocking_reasons: Tuple[str, ...]
    note: str
    plan_id: Optional[str] = None


def evaluate_paired_candidate(
    base: Sequence[Mapping[str, float]],
    candidate: Sequence[Mapping[str, float]],
    outcomes: Sequence[str],
    *,
    plan: Optional[ConfirmatoryPlan] = None,
    block_size: Optional[int] = None,
    seed: int = DEFAULT_SEED,
) -> PairedValidationResult:
    n = len(outcomes)
    if not (len(base) == len(candidate) == n):
        raise ValueError("length mismatch")

    target_delta = plan.target_delta if plan is not None else 0.010
    reasons = []

    if n == 0:
        return PairedValidationResult(
            0, math.nan, math.nan, math.nan, (math.nan, math.nan), math.nan,
            math.nan, target_delta, 0, True, False, False,
            ("NO_OBSERVATIONS",), "NO_OBSERVATIONS",
            plan.plan_id if plan else None)

    base_losses = [multiclass_brier(p, y) for p, y in zip(base, outcomes)]
    cand_losses = [multiclass_brier(p, y) for p, y in zip(candidate, outcomes)]
    diffs = [a - b for a, b in zip(base_losses, cand_losses)]
    boot = block_bootstrap_ci(
        diffs,
        block_size=block_size if block_size is not None
        else (plan.block_size if plan is not None else DEFAULT_BLOCK_SIZE),
        seed=seed,
    )
    mean_delta = sum(diffs) / n

    # ---- preregistration and evidence class -------------------------------
    if plan is None:
        reasons.append("NO_PREREGISTERED_PLAN")
    else:
        if n != plan.preregistered_n:
            reasons.append("N_DOES_NOT_MATCH_PREREGISTERED_N")
        if not plan.is_prospective:
            reasons.append("EVIDENCE_CLASS_IS_NOT_FORWARD_OOS")

    # ---- estimator adequacy ------------------------------------------------
    if boot.effective_blocks < MIN_EFFECTIVE_BLOCKS:
        reasons.append("INSUFFICIENT_EFFECTIVE_BLOCKS")
    if boot.degenerate:
        reasons.append("DEGENERATE_BOOTSTRAP")

    # ---- effect ------------------------------------------------------------
    if not (mean_delta >= target_delta):
        reasons.append("MEAN_DELTA_BELOW_TARGET")
    if boot.degenerate or not (boot.lo > 0.0):
        if "DEGENERATE_BOOTSTRAP" not in reasons:
            reasons.append("CI_LOWER_BOUND_NOT_ABOVE_ZERO")

    confirmatory_eligible = plan is not None and not {
        "NO_PREREGISTERED_PLAN",
        "N_DOES_NOT_MATCH_PREREGISTERED_N",
        "EVIDENCE_CLASS_IS_NOT_FORWARD_OOS",
        "INSUFFICIENT_EFFECTIVE_BLOCKS",
        "DEGENERATE_BOOTSTRAP",
    } & set(reasons)

    promotion_gate_pass = confirmatory_eligible and not reasons

    note = ("FIXED_N_PREREGISTERED_NO_OPTIONAL_STOPPING" if plan is not None
            else "DIAGNOSTIC_ONLY_NO_PREREGISTERED_PLAN")

    return PairedValidationResult(
        n=n,
        base_mean_brier=sum(base_losses) / n,
        candidate_mean_brier=sum(cand_losses) / n,
        mean_delta=mean_delta,
        delta_ci90=(boot.lo, boot.hi),
        base_ece=expected_calibration_error(base, outcomes),
        candidate_ece=expected_calibration_error(candidate, outcomes),
        target_delta=target_delta,
        effective_blocks=boot.effective_blocks,
        degenerate_bootstrap=boot.degenerate,
        confirmatory_eligible=confirmatory_eligible,
        promotion_gate_pass=promotion_gate_pass,
        blocking_reasons=tuple(reasons),
        note=note,
        plan_id=plan.plan_id if plan is not None else None,
    )
