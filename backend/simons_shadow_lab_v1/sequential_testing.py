"""Pre-registered sequential alpha spending for Shadow Lab V2 Hybrid.

This module solves one specific problem: repeated peeking at the same forward
candidate must not silently inflate the false-positive rate.

The implementation is intentionally conservative.  It uses an
O'Brien-Fleming-shaped cumulative spending function, but each ordinary p-value
is compared with the *incremental* alpha allocated to that look.  By the union
bound this controls the total Type-I error across looks even when the repeated
look statistics are dependent.  It does not claim to reproduce the exact
canonical Lan-DeMets group-sequential boundary machinery.

When several pre-registered candidates share a family, the family alpha is
Bonferroni-allocated before the sequential schedule is constructed.  This
keeps cross-candidate multiplicity and repeated looks separate and explicit.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from statistics import NormalDist
from typing import Any, Dict, List, Optional, Sequence

from .lab import GENESIS, _read_json, _write_new_json, canonical_bytes, sha256_bytes


@dataclass(frozen=True)
class AlphaSpendingPlan:
    hypothesis_id: str
    information_fractions: Sequence[float]
    family_alpha: float = 0.05
    family_size: int = 1
    sidedness: str = "ONE_SIDED"
    spending_shape: str = "OBRIEN_FLEMING"
    notes: str = ""

    def normalized(self) -> Dict[str, Any]:
        hid = str(self.hypothesis_id or "").strip()
        if not hid:
            raise ValueError("hypothesis_id is required")
        alpha = float(self.family_alpha)
        if not (0.0 < alpha < 1.0):
            raise ValueError("family_alpha must be in (0,1)")
        size = int(self.family_size)
        if size < 1:
            raise ValueError("family_size must be >= 1")
        sided = str(self.sidedness or "").upper()
        if sided not in {"ONE_SIDED", "TWO_SIDED"}:
            raise ValueError("sidedness must be ONE_SIDED or TWO_SIDED")
        shape = str(self.spending_shape or "").upper()
        if shape != "OBRIEN_FLEMING":
            raise ValueError("only OBRIEN_FLEMING spending is supported")
        fracs = [float(x) for x in self.information_fractions]
        if not fracs:
            raise ValueError("at least one information fraction is required")
        if any(not (0.0 < x <= 1.0) for x in fracs):
            raise ValueError("information fractions must be in (0,1]")
        if any(b <= a for a, b in zip(fracs, fracs[1:])):
            raise ValueError("information fractions must be strictly increasing")
        if abs(fracs[-1] - 1.0) > 1e-12:
            raise ValueError("final information fraction must equal 1.0")
        effective_alpha = alpha / size
        return {
            "hypothesis_id": hid,
            "information_fractions": fracs,
            "family_alpha": alpha,
            "family_size": size,
            "family_correction": "BONFERRONI",
            "effective_hypothesis_alpha": effective_alpha,
            "sidedness": sided,
            "spending_shape": shape,
            "notes": str(self.notes or ""),
        }


def obrien_fleming_cumulative_alpha(
    information_fraction: float,
    alpha: float,
    sidedness: str = "ONE_SIDED",
) -> float:
    """O'Brien-Fleming-shaped cumulative alpha spend A(t).

    At t=1 the cumulative spend equals ``alpha`` (within floating point error),
    while early looks spend very little alpha.
    """
    t = float(information_fraction)
    a = float(alpha)
    sided = str(sidedness or "").upper()
    if not (0.0 < t <= 1.0):
        raise ValueError("information_fraction must be in (0,1]")
    if not (0.0 < a < 1.0):
        raise ValueError("alpha must be in (0,1)")
    if sided == "ONE_SIDED":
        z = NormalDist().inv_cdf(1.0 - a)
        spent = 1.0 - NormalDist().cdf(z / (t ** 0.5))
    elif sided == "TWO_SIDED":
        z = NormalDist().inv_cdf(1.0 - a / 2.0)
        spent = 2.0 * (1.0 - NormalDist().cdf(z / (t ** 0.5)))
    else:
        raise ValueError("sidedness must be ONE_SIDED or TWO_SIDED")
    return min(a, max(0.0, spent))


def alpha_schedule(plan: AlphaSpendingPlan) -> Dict[str, Any]:
    p = plan.normalized()
    effective = float(p["effective_hypothesis_alpha"])
    previous = 0.0
    looks: List[Dict[str, Any]] = []
    for i, fraction in enumerate(p["information_fractions"], 1):
        cumulative = obrien_fleming_cumulative_alpha(fraction, effective, p["sidedness"])
        local = max(0.0, cumulative - previous)
        looks.append({
            "look_index": i,
            "information_fraction": fraction,
            "cumulative_alpha_spent": cumulative,
            "local_alpha_for_ordinary_p_value": local,
        })
        previous = cumulative
    total_local = sum(float(x["local_alpha_for_ordinary_p_value"]) for x in looks)
    return {
        "method": "OBRIEN_FLEMING_SHAPED_UNION_BOUND_ALPHA_SPENDING_V1",
        "plan": p,
        "looks": looks,
        "total_local_alpha": total_local,
        "family_alpha_bound": p["family_alpha"],
        "hypothesis_alpha_bound": effective,
        "type_i_control_note": (
            "Ordinary p-values are tested against disjoint incremental alpha budgets; "
            "the union bound controls repeated-look Type-I error without assuming independence."
        ),
        "exact_lan_demets_boundary_claimed": False,
    }


def evaluate_look(plan: AlphaSpendingPlan, look_index: int, p_value: float) -> Dict[str, Any]:
    schedule = alpha_schedule(plan)
    idx = int(look_index)
    if idx < 1 or idx > len(schedule["looks"]):
        raise ValueError("look_index is outside the pre-registered schedule")
    p = float(p_value)
    if not (0.0 <= p <= 1.0):
        raise ValueError("p_value must be in [0,1]")
    look = dict(schedule["looks"][idx - 1])
    threshold = float(look["local_alpha_for_ordinary_p_value"])
    met = p <= threshold
    return {
        **look,
        "p_value": p,
        "threshold_met": met,
        "scientific_status": (
            "SEQUENTIAL_THRESHOLD_MET_REQUIRES_REVIEW" if met
            else "CONTINUE_PRE_REGISTERED_SEQUENCE"
        ),
        "predictive_edge_proven": False,
        "automatic_production_promotion": False,
    }


class SequentialAlphaLedger:
    """Immutable plan + append-only look ledger for one pre-registered hypothesis."""

    def __init__(self, lab_root: Path, hypothesis_id: str):
        self.root = Path(lab_root) / "sequential_alpha" / str(hypothesis_id)
        self.hypothesis_id = str(hypothesis_id)

    @property
    def plan_path(self) -> Path:
        return self.root / "plan.json"

    @property
    def events_root(self) -> Path:
        return self.root / "events"

    def freeze_plan(self, plan: AlphaSpendingPlan, now: Optional[datetime] = None) -> Dict[str, Any]:
        normalized = plan.normalized()
        if normalized["hypothesis_id"] != self.hypothesis_id:
            raise ValueError("ledger hypothesis_id does not match plan")
        schedule = alpha_schedule(plan)
        now = now or datetime.now(timezone.utc)
        unsigned = {
            "created_at_utc": now.astimezone(timezone.utc).isoformat(),
            "hypothesis_id": self.hypothesis_id,
            "schedule": schedule,
            "status": "FROZEN_BEFORE_SEQUENTIAL_LOOKS",
            "production_modified": False,
        }
        payload = {**unsigned, "plan_sha256": sha256_bytes(canonical_bytes(unsigned))}
        _write_new_json(self.plan_path, payload)
        return payload

    def load_plan(self) -> Dict[str, Any]:
        payload = _read_json(self.plan_path)
        unsigned = dict(payload)
        claimed = str(unsigned.pop("plan_sha256", ""))
        if claimed != sha256_bytes(canonical_bytes(unsigned)):
            raise RuntimeError("sequential alpha plan hash mismatch")
        return payload

    def events(self) -> List[Dict[str, Any]]:
        if not self.events_root.exists():
            return []
        out: List[Dict[str, Any]] = []
        prev = GENESIS
        for expected, path in enumerate(sorted(self.events_root.glob("*.json")), 1):
            event = _read_json(path)
            unsigned = dict(event)
            claimed = str(unsigned.pop("event_hash", ""))
            if claimed != sha256_bytes(canonical_bytes(unsigned)):
                raise RuntimeError(f"sequential alpha event hash mismatch:{path.name}")
            if int(event.get("seq") or 0) != expected or event.get("prev_event_hash") != prev:
                raise RuntimeError("sequential alpha ledger chain mismatch")
            prev = claimed
            out.append(event)
        return out

    def append_look(
        self,
        look_index: int,
        p_value: float,
        observed_n: int,
        *,
        now: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        plan_doc = self.load_plan()
        events = self.events()
        if events and bool((events[-1].get("payload") or {}).get("threshold_met")):
            raise RuntimeError("sequential test already stopped after threshold crossing")
        expected = len(events) + 1
        if int(look_index) != expected:
            raise ValueError(f"look_index must be next pre-registered look: expected {expected}")
        looks = ((plan_doc.get("schedule") or {}).get("looks") or [])
        if expected > len(looks):
            raise ValueError("all pre-registered looks have already been consumed")
        p = float(p_value)
        if not (0.0 <= p <= 1.0):
            raise ValueError("p_value must be in [0,1]")
        n = int(observed_n)
        if n < 1:
            raise ValueError("observed_n must be >= 1")
        look = dict(looks[expected - 1])
        threshold = float(look["local_alpha_for_ordinary_p_value"])
        met = p <= threshold
        now = now or datetime.now(timezone.utc)
        payload = {
            "information_fraction": look["information_fraction"],
            "observed_n": n,
            "p_value": p,
            "local_alpha": threshold,
            "cumulative_alpha_spent": look["cumulative_alpha_spent"],
            "threshold_met": met,
            "decision": "STOP_FOR_STATISTICAL_REVIEW" if met else "CONTINUE",
            "predictive_edge_proven": False,
            "automatic_production_promotion": False,
        }
        unsigned = {
            "seq": expected,
            "event_type": "SEQUENTIAL_ALPHA_LOOK",
            "hypothesis_id": self.hypothesis_id,
            "created_at_utc": now.astimezone(timezone.utc).isoformat(),
            "prev_event_hash": events[-1]["event_hash"] if events else GENESIS,
            "plan_sha256": plan_doc["plan_sha256"],
            "payload": payload,
        }
        event = {**unsigned, "event_hash": sha256_bytes(canonical_bytes(unsigned))}
        _write_new_json(self.events_root / f"{expected:08d}_look.json", event)
        return event
