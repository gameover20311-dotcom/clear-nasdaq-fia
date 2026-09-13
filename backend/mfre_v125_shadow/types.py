from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
import hashlib, json, math, re
from typing import Any, Mapping, Tuple

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_UNRESOLVED_MARKERS = ("UNSET", "PLACEHOLDER", "REQUIRES_FREEZE", "TBD")


def _is_sha256(value: str) -> bool:
    return bool(_SHA256.fullmatch(str(value or "")))


def _is_resolved_id(value: str) -> bool:
    text = str(value or "").strip()
    return bool(text) and not any(marker in text.upper() for marker in _UNRESOLVED_MARKERS)


class ActionKind(str, Enum):
    ACQUIRE = "A_acq"
    COMPUTE = "A_comp"
    STOP = "A_stop"


class RandomnessOwnership(str, Enum):
    EXTERNAL_PROVIDER = "EXTERNAL_PROVIDER"
    ENGINE_OWNED = "ENGINE_OWNED"
    NONE_DETERMINISTIC = "NONE_DETERMINISTIC"


@dataclass(frozen=True)
class PrimitiveSpec:
    action_id: str
    kind: ActionKind
    cost: float
    budget_name: str
    randomness_ownership: RandomnessOwnership
    kernel_fingerprint: str = ""

    def __post_init__(self) -> None:
        if not self.action_id.strip():
            raise ValueError("action_id must be non-empty")
        if not math.isfinite(float(self.cost)) or float(self.cost) < 0:
            raise ValueError("cost must be finite and non-negative")
        if not self.budget_name.strip():
            raise ValueError("budget_name must be non-empty")
        if self.kind is ActionKind.STOP and self.randomness_ownership is not RandomnessOwnership.NONE_DETERMINISTIC:
            raise ValueError("A_stop must be NONE_DETERMINISTIC in this integration shell")

    @property
    def scientifically_frozen(self) -> bool:
        return _is_sha256(self.kernel_fingerprint)


@dataclass(frozen=True)
class DeclarationBundle:
    """Preregistered implementation declaration record.

    This object is allowed to represent an unfinished draft, but `scientifically_frozen`
    is false until every executable slot has a pinned implementation fingerprint and
    all protocol-level L10/decision parameters are declared. The controller MUST remain
    inert for a draft bundle.
    """

    primitives: Tuple[PrimitiveSpec, ...]
    compute_budget: int
    acquisition_budget: int
    selection_budget: int
    gamma_theta_id: str
    phi_id: str
    delta_stop_id: str
    bellman_policy_id: str
    gamma_theta_fingerprint: str = ""
    phi_fingerprint: str = ""
    delta_stop_fingerprint: str = ""
    bellman_policy_fingerprint: str = ""
    working_measure_id: str = ""
    working_measure_fingerprint: str = ""
    k_max: int = 0
    c_a: float = 0.0
    tie_break: Tuple[str, ...] = ()
    l10_parameters: Tuple[Tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        if not self.primitives:
            raise ValueError("at least one primitive is required")
        ids = [p.action_id for p in self.primitives]
        if len(ids) != len(set(ids)):
            raise ValueError("action_id values must be unique")
        if not any(p.kind is ActionKind.STOP for p in self.primitives):
            raise ValueError("an always-available A_stop primitive is required")
        for name, value in (
            ("compute_budget", self.compute_budget),
            ("acquisition_budget", self.acquisition_budget),
            ("selection_budget", self.selection_budget),
        ):
            if isinstance(value, bool) or int(value) < 0:
                raise ValueError(f"{name} must be a non-negative integer")
        for name, value in (
            ("gamma_theta_id", self.gamma_theta_id),
            ("phi_id", self.phi_id),
            ("delta_stop_id", self.delta_stop_id),
            ("bellman_policy_id", self.bellman_policy_id),
        ):
            if not str(value).strip():
                raise ValueError(f"{name} must be declared")
        if isinstance(self.k_max, bool) or int(self.k_max) < 0:
            raise ValueError("k_max must be a non-negative integer")
        if not math.isfinite(float(self.c_a)) or float(self.c_a) < 0 or float(self.c_a) > 0.5:
            raise ValueError("c_a must be finite and in [0, 0.5]")

    @property
    def unresolved_fields(self) -> Tuple[str, ...]:
        unresolved = []
        id_fields = {
            "gamma_theta_id": self.gamma_theta_id,
            "phi_id": self.phi_id,
            "delta_stop_id": self.delta_stop_id,
            "bellman_policy_id": self.bellman_policy_id,
            "working_measure_id": self.working_measure_id,
        }
        for name, value in id_fields.items():
            if not _is_resolved_id(value):
                unresolved.append(name)
        fp_fields = {
            "gamma_theta_fingerprint": self.gamma_theta_fingerprint,
            "phi_fingerprint": self.phi_fingerprint,
            "delta_stop_fingerprint": self.delta_stop_fingerprint,
            "bellman_policy_fingerprint": self.bellman_policy_fingerprint,
            "working_measure_fingerprint": self.working_measure_fingerprint,
        }
        for name, value in fp_fields.items():
            if not _is_sha256(value):
                unresolved.append(name)
        for primitive in self.primitives:
            if not primitive.scientifically_frozen:
                unresolved.append(f"primitive_kernel:{primitive.action_id}")
        if self.k_max <= 0:
            unresolved.append("k_max")
        if self.c_a <= 0.0:
            unresolved.append("c_a")
        if not self.tie_break:
            unresolved.append("tie_break")
        required_l10 = {"kappa", "ell", "B", "seed", "autocorrelation_band", "evaluation_window"}
        supplied_l10 = {str(k) for k, _ in self.l10_parameters}
        for name in sorted(required_l10 - supplied_l10):
            unresolved.append(f"l10:{name}")
        return tuple(unresolved)

    @property
    def scientifically_frozen(self) -> bool:
        return not self.unresolved_fields

    def canonical_payload(self) -> Mapping[str, Any]:
        return {
            "primitives": [
                {
                    "action_id": p.action_id,
                    "kind": p.kind.value,
                    "cost": float(p.cost),
                    "budget_name": p.budget_name,
                    "randomness_ownership": p.randomness_ownership.value,
                    "kernel_fingerprint": p.kernel_fingerprint,
                }
                for p in sorted(self.primitives, key=lambda x: x.action_id)
            ],
            "compute_budget": int(self.compute_budget),
            "acquisition_budget": int(self.acquisition_budget),
            "selection_budget": int(self.selection_budget),
            "gamma_theta_id": self.gamma_theta_id,
            "phi_id": self.phi_id,
            "delta_stop_id": self.delta_stop_id,
            "bellman_policy_id": self.bellman_policy_id,
            "gamma_theta_fingerprint": self.gamma_theta_fingerprint,
            "phi_fingerprint": self.phi_fingerprint,
            "delta_stop_fingerprint": self.delta_stop_fingerprint,
            "bellman_policy_fingerprint": self.bellman_policy_fingerprint,
            "working_measure_id": self.working_measure_id,
            "working_measure_fingerprint": self.working_measure_fingerprint,
            "k_max": int(self.k_max),
            "c_a": float(self.c_a),
            "tie_break": list(self.tie_break),
            "l10_parameters": [[str(k), str(v)] for k, v in sorted(self.l10_parameters)],
            "scientifically_frozen": self.scientifically_frozen,
        }

    @property
    def protocol_identity(self) -> str:
        if not self.scientifically_frozen:
            raise RuntimeError("MFRE_DECLARATION_BUNDLE_NOT_FROZEN:" + ",".join(self.unresolved_fields))
        raw = json.dumps(self.canonical_payload(), sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
        return hashlib.sha256(raw).hexdigest()


@dataclass(frozen=True)
class ControlState:
    history: Tuple[Tuple[str, str], ...] = ()
    compute_remaining: int = 0
    acquisition_remaining: int = 0
    selection_remaining: int = 0

    def append(self, *, action_id: str, output_digest: str, kind: ActionKind) -> "ControlState":
        c, a, s = self.compute_remaining, self.acquisition_remaining, self.selection_remaining
        if kind is ActionKind.COMPUTE:
            if c <= 0:
                raise RuntimeError("MFRE_COMPUTE_BUDGET_EXHAUSTED")
            c -= 1
        elif kind is ActionKind.ACQUIRE:
            if a <= 0:
                raise RuntimeError("MFRE_ACQUISITION_BUDGET_EXHAUSTED")
            a -= 1
        elif kind is not ActionKind.STOP:
            raise RuntimeError("MFRE_UNKNOWN_ACTION_KIND")
        return ControlState(self.history + ((action_id, output_digest),), c, a, s)
