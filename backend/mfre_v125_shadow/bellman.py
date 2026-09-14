from __future__ import annotations

"""Exact finite-support MFRE L7 Bellman executor for research/shadow use.

This module implements the generic backward-induction machinery only.  It does
NOT construct Gamma_theta, Phi, delta_stop, market probabilities, DPCSE models,
or any acquisition kernel.  Those remain separately declared/frozen runtime
bindings.  No audit-log object is accepted by this API.
"""

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import inspect
import math
from typing import Protocol, Sequence

from .types import ActionKind, ControlState, DeclarationBundle, PrimitiveSpec

ENGINE_MODE = "EXACT_FINITE_SUPPORT_RESEARCH"
TERMINAL_ACTIONS = {"Bull", "Bear", "NO_EDGE"}


def _d(value) -> Decimal:
    try:
        out = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError("MFRE_NON_NUMERIC_PROBABILITY_OR_RISK") from exc
    if not out.is_finite():
        raise ValueError("MFRE_NON_FINITE_PROBABILITY_OR_RISK")
    return out


@dataclass(frozen=True)
class TerminalEvaluation:
    action: str
    risk: Decimal

    def __post_init__(self) -> None:
        risk = _d(self.risk)
        if self.action not in TERMINAL_ACTIONS:
            raise ValueError("MFRE_UNKNOWN_TERMINAL_ACTION")
        if risk < Decimal("0") or risk > Decimal("1"):
            raise ValueError("MFRE_TERMINAL_RISK_OUT_OF_RANGE")
        object.__setattr__(self, "risk", risk)


@dataclass(frozen=True)
class Transition:
    probability: Decimal
    next_state: ControlState

    def __post_init__(self) -> None:
        probability = _d(self.probability)
        if probability <= Decimal("0") or probability > Decimal("1"):
            raise ValueError("MFRE_TRANSITION_PROBABILITY_OUT_OF_RANGE")
        object.__setattr__(self, "probability", probability)


@dataclass(frozen=True)
class ActionValue:
    action_id: str
    expected_value: Decimal


@dataclass(frozen=True)
class BellmanSolution:
    value: Decimal
    choice_action_id: str
    stop: bool
    terminal_action: str | None
    steps_remaining: int
    action_values: tuple[ActionValue, ...]


class ExactFiniteSupportRuntime(Protocol):
    """Domain binding surface.  Audit state is intentionally absent."""

    def terminal_evaluation(self, state: ControlState) -> TerminalEvaluation: ...
    def admissible_actions(self, state: ControlState) -> Sequence[str]: ...
    def transition_support(self, state: ControlState, action_id: str) -> Sequence[Transition]: ...


def _validate_method_signature(method, positional_count: int, name: str) -> None:
    sig = inspect.signature(method)
    params = list(sig.parameters.values())
    for p in params:
        if p.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD):
            raise ValueError(f"MFRE_RUNTIME_SIGNATURE_VARARGS_FORBIDDEN:{name}")
        if "audit" in p.name.lower():
            raise ValueError(f"MFRE_RUNTIME_AUDIT_ARGUMENT_FORBIDDEN:{name}")
    positional = [
        p for p in params
        if p.kind in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
    ]
    required = [p for p in positional if p.default is inspect.Parameter.empty]
    if len(positional) != positional_count or len(required) != positional_count:
        raise ValueError(f"MFRE_RUNTIME_SIGNATURE_INVALID:{name}")


class ExactFiniteSupportBellmanEngine:
    """L7 backward induction over `ControlState` with exact Decimal probabilities.

    The executor is intentionally a compatible finite-support subset of the
    frozen mathematical contract.  A real CLEAR NASDAQ binding remains forbidden
    until its declaration bundle and runtime functions are separately frozen and
    fingerprinted.
    """

    def __init__(self, declarations: DeclarationBundle, runtime: ExactFiniteSupportRuntime):
        if not declarations.scientifically_frozen:
            raise RuntimeError(
                "MFRE_EXECUTOR_DECLARATIONS_NOT_FROZEN:" + ",".join(declarations.unresolved_fields)
            )
        self.declarations = declarations
        self.runtime = runtime
        self._primitives = {p.action_id: p for p in declarations.primitives}
        stops = [p.action_id for p in declarations.primitives if p.kind is ActionKind.STOP]
        if len(stops) != 1:
            raise ValueError("MFRE_EXECUTOR_REQUIRES_EXACTLY_ONE_STOP_PRIMITIVE")
        self.stop_action_id = stops[0]
        self._rank = {action_id: i for i, action_id in enumerate(declarations.tie_break)}
        if set(self._rank) != set(self._primitives):
            raise ValueError("MFRE_EXECUTOR_TIE_BREAK_DOES_NOT_MATCH_ACTION_MENU")
        _validate_method_signature(runtime.terminal_evaluation, 1, "terminal_evaluation")
        _validate_method_signature(runtime.admissible_actions, 1, "admissible_actions")
        _validate_method_signature(runtime.transition_support, 2, "transition_support")
        self.max_steps = int(
            declarations.compute_budget
            + declarations.acquisition_budget
            + declarations.selection_budget
        )
        self._memo: dict[tuple[ControlState, int], BellmanSolution] = {}

    def initial_state(self) -> ControlState:
        return ControlState(
            (),
            float(self.declarations.compute_budget),
            float(self.declarations.acquisition_budget),
            float(self.declarations.selection_budget),
        )

    def _validate_state(self, state: ControlState) -> None:
        limits = (
            (state.compute_remaining, float(self.declarations.compute_budget), "compute"),
            (state.acquisition_remaining, float(self.declarations.acquisition_budget), "acquisition"),
            (state.selection_remaining, float(self.declarations.selection_budget), "selection"),
        )
        for remaining, initial, name in limits:
            if not math.isfinite(float(remaining)) or remaining < 0 or remaining > initial:
                raise ValueError(f"MFRE_STATE_BUDGET_INVALID:{name}")
        for action_id, output_digest in state.history:
            if action_id not in self._primitives:
                raise ValueError("MFRE_STATE_CONTAINS_UNDECLARED_ACTION")
            if not str(output_digest):
                raise ValueError("MFRE_STATE_OUTPUT_DIGEST_EMPTY")

    @staticmethod
    def _remaining_for(state: ControlState, primitive: PrimitiveSpec) -> float:
        if primitive.budget_name == "compute":
            return state.compute_remaining
        if primitive.budget_name == "acquisition":
            return state.acquisition_remaining
        if primitive.budget_name == "selection":
            return state.selection_remaining
        raise ValueError("MFRE_UNKNOWN_BUDGET_NAME")

    def _affordable(self, state: ControlState, primitive: PrimitiveSpec) -> bool:
        if primitive.kind is ActionKind.STOP:
            return True
        return self._remaining_for(state, primitive) >= float(primitive.cost)

    def _continuation_actions(self, state: ControlState) -> tuple[str, ...]:
        raw = tuple(self.runtime.admissible_actions(state))
        if len(raw) != len(set(raw)):
            raise ValueError("MFRE_RUNTIME_DUPLICATE_ACTION")
        out = []
        for action_id in raw:
            if action_id not in self._primitives:
                raise ValueError("MFRE_RUNTIME_UNDECLARED_ACTION")
            primitive = self._primitives[action_id]
            if primitive.kind is ActionKind.STOP:
                raise ValueError("MFRE_RUNTIME_STOP_MUST_USE_TERMINAL_EVALUATION")
            if self._affordable(state, primitive):
                out.append(action_id)
        return tuple(out)

    def _validated_support(self, state: ControlState, action_id: str) -> tuple[Transition, ...]:
        primitive = self._primitives[action_id]
        support = tuple(self.runtime.transition_support(state, action_id))
        if not support:
            raise ValueError("MFRE_EMPTY_TRANSITION_SUPPORT")
        total = sum((t.probability for t in support), Decimal("0"))
        if total != Decimal("1"):
            raise ValueError("MFRE_TRANSITION_PROBABILITIES_MUST_SUM_TO_ONE_EXACTLY")
        for transition in support:
            next_state = transition.next_state
            self._validate_state(next_state)
            if len(next_state.history) != len(state.history) + 1:
                raise ValueError("MFRE_NEXT_STATE_HISTORY_LENGTH_INVALID")
            if next_state.history[:-1] != state.history:
                raise ValueError("MFRE_NEXT_STATE_HISTORY_PREFIX_INVALID")
            next_action_id, output_digest = next_state.history[-1]
            if next_action_id != action_id:
                raise ValueError("MFRE_NEXT_STATE_ACTION_MISMATCH")
            expected = state.append(
                action_id=action_id,
                output_digest=output_digest,
                kind=primitive.kind,
                budget_name=primitive.budget_name,
                cost=primitive.cost,
            )
            if expected != next_state:
                raise ValueError("MFRE_NEXT_STATE_BUDGET_OR_RECORD_MISMATCH")
        return support

    def solve(self, state: ControlState | None = None) -> BellmanSolution:
        start = self.initial_state() if state is None else state
        self._validate_state(start)
        return self._solve(start, self.max_steps)

    def _solve(self, state: ControlState, steps_remaining: int) -> BellmanSolution:
        key = (state, steps_remaining)
        if key in self._memo:
            return self._memo[key]

        terminal = self.runtime.terminal_evaluation(state)
        candidates: list[ActionValue] = [ActionValue(self.stop_action_id, terminal.risk)]

        if steps_remaining > 0:
            for action_id in self._continuation_actions(state):
                support = self._validated_support(state, action_id)
                expected = Decimal("0")
                for transition in support:
                    child = self._solve(transition.next_state, steps_remaining - 1)
                    expected += transition.probability * child.value
                candidates.append(ActionValue(action_id, expected))

        chosen = min(candidates, key=lambda item: (item.expected_value, self._rank[item.action_id]))
        solution = BellmanSolution(
            value=chosen.expected_value,
            choice_action_id=chosen.action_id,
            stop=chosen.action_id == self.stop_action_id,
            terminal_action=terminal.action if chosen.action_id == self.stop_action_id else None,
            steps_remaining=steps_remaining,
            action_values=tuple(candidates),
        )
        self._memo[key] = solution
        return solution
