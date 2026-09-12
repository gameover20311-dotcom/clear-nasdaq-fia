"""Causal structural/topological regime diagnostics for UMSE V2.

The implementation uses the standard equivalence between 0-dimensional
Vietoris-Rips persistence and the edge lengths of a minimum spanning tree.
That gives a dependency-light way to describe fragmentation/merger scales in
an observed state cloud without pretending that topology itself predicts NQ.

Only points causally available at the decision time are used.  The result is a
descriptive regime diagnostic: never calibrated, never predictive, never a
promotion signal by itself.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import math
from typing import Iterable, Sequence

from .contracts import EvidenceStatus


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("timestamps must be timezone-aware")
    return value.astimezone(timezone.utc)


@dataclass(frozen=True)
class StatePoint:
    event_time_utc: datetime
    available_time_utc: datetime
    vector: tuple[float, ...]
    provenance_id: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "event_time_utc", _utc(self.event_time_utc))
        object.__setattr__(self, "available_time_utc", _utc(self.available_time_utc))
        if not self.vector:
            raise ValueError("vector must be non-empty")
        if any(not math.isfinite(float(x)) for x in self.vector):
            raise ValueError("vector values must be finite")
        if not str(self.provenance_id).strip():
            raise ValueError("provenance_id must be non-empty")

    def eligible_at(self, decision_time_utc: datetime) -> bool:
        decision = _utc(decision_time_utc)
        return self.event_time_utc <= decision and self.available_time_utc <= decision


@dataclass(frozen=True)
class TopologicalRegimeSignature:
    status: EvidenceStatus
    samples: int
    dimensions: int
    mst_edge_lengths: tuple[float, ...]
    largest_merge_scale: float | None
    median_merge_scale: float | None
    largest_gap_ratio: float | None
    persistence_entropy: float | None
    fragmentation_index: float | None
    reasons: tuple[str, ...]
    calibrated: bool = False
    predictive: bool = False
    promotion_eligible: bool = False

    def __post_init__(self) -> None:
        if self.calibrated or self.predictive or self.promotion_eligible:
            raise ValueError("topological regime diagnostics are descriptive only")


def _standardize(vectors: Sequence[tuple[float, ...]]) -> list[tuple[float, ...]]:
    dims = len(vectors[0])
    means = [sum(v[j] for v in vectors) / len(vectors) for j in range(dims)]
    scales: list[float] = []
    for j in range(dims):
        variance = sum((v[j] - means[j]) ** 2 for v in vectors) / len(vectors)
        scales.append(math.sqrt(variance))
    out = []
    for v in vectors:
        out.append(tuple((v[j] - means[j]) / scales[j] if scales[j] > 1e-12 else 0.0 for j in range(dims)))
    return out


def _distance(a: Sequence[float], b: Sequence[float]) -> float:
    return math.sqrt(sum((float(x) - float(y)) ** 2 for x, y in zip(a, b)))


def _mst_edges(points: Sequence[tuple[float, ...]]) -> list[float]:
    """Prim MST over the complete Euclidean graph; returns n-1 edge lengths."""
    n = len(points)
    if n <= 1:
        return []
    used = [False] * n
    best = [math.inf] * n
    best[0] = 0.0
    edges: list[float] = []
    for _ in range(n):
        u = min((i for i in range(n) if not used[i]), key=lambda i: best[i])
        used[u] = True
        if best[u] > 0.0 and math.isfinite(best[u]):
            edges.append(best[u])
        for v in range(n):
            if used[v]:
                continue
            d = _distance(points[u], points[v])
            if d < best[v]:
                best[v] = d
    return edges


def _median(xs: Sequence[float]) -> float:
    ys = sorted(float(x) for x in xs)
    n = len(ys)
    if n % 2:
        return ys[n // 2]
    return 0.5 * (ys[n // 2 - 1] + ys[n // 2])


def topological_regime_signature(
    points: Iterable[StatePoint],
    decision_time_utc: datetime,
    *,
    minimum_points: int = 20,
) -> TopologicalRegimeSignature:
    if minimum_points < 3:
        raise ValueError("minimum_points must be >= 3")
    decision = _utc(decision_time_utc)
    eligible = tuple(sorted(
        (p for p in points if p.eligible_at(decision)),
        key=lambda p: (p.event_time_utc, p.provenance_id),
    ))
    if len(eligible) < minimum_points:
        return TopologicalRegimeSignature(
            status=EvidenceStatus.INSUFFICIENT_DATA,
            samples=len(eligible),
            dimensions=len(eligible[0].vector) if eligible else 0,
            mst_edge_lengths=(),
            largest_merge_scale=None,
            median_merge_scale=None,
            largest_gap_ratio=None,
            persistence_entropy=None,
            fragmentation_index=None,
            reasons=("INSUFFICIENT_CAUSAL_STATE_POINTS",),
        )

    dims = len(eligible[0].vector)
    if any(len(p.vector) != dims for p in eligible):
        return TopologicalRegimeSignature(
            status=EvidenceStatus.PROTOCOL_INELIGIBLE,
            samples=len(eligible),
            dimensions=dims,
            mst_edge_lengths=(),
            largest_merge_scale=None,
            median_merge_scale=None,
            largest_gap_ratio=None,
            persistence_entropy=None,
            fragmentation_index=None,
            reasons=("STATE_VECTOR_DIMENSION_CHANGED",),
        )

    vectors = [p.vector for p in eligible]
    standardized = _standardize(vectors)
    edges = sorted(_mst_edges(standardized))
    if not edges or max(edges) <= 1e-12:
        return TopologicalRegimeSignature(
            status=EvidenceStatus.NOT_IDENTIFIABLE,
            samples=len(eligible),
            dimensions=dims,
            mst_edge_lengths=tuple(edges),
            largest_merge_scale=max(edges) if edges else 0.0,
            median_merge_scale=_median(edges) if edges else 0.0,
            largest_gap_ratio=None,
            persistence_entropy=None,
            fragmentation_index=None,
            reasons=("DEGENERATE_STATE_CLOUD",),
        )

    gaps = [b - a for a, b in zip(edges, edges[1:])]
    largest_gap = max(gaps) if gaps else 0.0
    med = _median(edges)
    gap_ratio = largest_gap / max(med, 1e-12)

    total = sum(edges)
    probs = [e / total for e in edges if e > 0.0]
    entropy = -sum(p * math.log(p) for p in probs)
    entropy /= math.log(len(edges)) if len(edges) > 1 else 1.0

    largest = edges[-1]
    fragmentation = largest / max(sum(edges) / len(edges), 1e-12)

    reasons = [
        "ZERO_DIMENSIONAL_PERSISTENCE_VIA_MST_ONLY",
        "DESCRIPTIVE_REGIME_GEOMETRY_NOT_FORECAST_EDGE",
    ]
    if gap_ratio > 2.0:
        reasons.append("LARGE_COMPONENT_MERGE_GAP_PRESENT")

    return TopologicalRegimeSignature(
        status=EvidenceStatus.UNCALIBRATED,
        samples=len(eligible),
        dimensions=dims,
        mst_edge_lengths=tuple(edges),
        largest_merge_scale=largest,
        median_merge_scale=med,
        largest_gap_ratio=gap_ratio,
        persistence_entropy=entropy,
        fragmentation_index=fragmentation,
        reasons=tuple(reasons),
        calibrated=False,
        predictive=False,
        promotion_eligible=False,
    )
