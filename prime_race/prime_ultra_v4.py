from __future__ import annotations

import random
from collections import Counter
from dataclasses import dataclass
from typing import Any

POLICY_VERSION = "PRIME_ULTRA_V4"
REASONING_VERIFIER_OVERRIDE = False
HYBRID_LANE_ENABLED = True

FAMILIES = [
    "arithmetic_chain",
    "boolean_truth_table",
    "conditional_logic",
    "quantifier_counterexample",
    "set_inclusion",
    "ordering_constraints",
    "probability_complement",
    "contradiction_scope",
    "timestamp_causality",
    "provenance_chain",
    "evidence_overlap",
    "future_leakage_boundary",
    "causal_confounding",
    "missing_information",
    "adversarial_negation",
    "governance_threshold",
]


@dataclass(frozen=True)
class Task:
    task_id: str
    family: str
    question: str
    context: str
    options: dict[str, str]
    answer: str

    def public(self) -> dict[str, Any]:
        return {
            "id": self.task_id,
            "category": self.family,
            "question": self.question,
            "context": self.context,
            "options": dict(self.options),
        }


def _shuffle(rng: random.Random, correct: str, wrongs: list[str]) -> tuple[dict[str, str], str]:
    values = [correct, *wrongs]
    if len(values) != 4 or len(set(values)) != 4:
        raise ValueError("options must be four unique strings")
    rng.shuffle(values)
    options = dict(zip("ABCD", values))
    answer = next(k for k, v in options.items() if v == correct)
    return options, answer


def _task(rng: random.Random, family: str, index: int) -> Task:
    tid = f"V4-{family}-{index:03d}"

    if family == "arithmetic_chain":
        a = rng.randint(12, 48)
        b = rng.randint(3, 9)
        c = rng.randint(2, 7)
        result = a * b - c
        question = "What is the exact result after applying the operations in order?"
        context = f"Start with {a}. Multiply by {b}. Then subtract {c}."
        correct = str(result)
        wrongs = [str(result + 1), str(result - 1), str(a * (b - c))]

    elif family == "boolean_truth_table":
        p = rng.choice([True, False])
        q = rng.choice([True, False])
        value = (p and (not q)) or ((not p) and q)
        question = "What is the truth value of (P AND NOT Q) OR (NOT P AND Q)?"
        context = f"P is {p}. Q is {q}."
        correct = "True" if value else "False"
        wrongs = ["Both true and false", "Undefined without another premise", "Equivalent to P AND Q"] if value else ["True", "Both true and false", "Undefined without another premise"]

    elif family == "conditional_logic":
        p = rng.choice([True, False])
        q = rng.choice([True, False])
        value = (not p) or q
        question = "Evaluate the material implication P -> Q."
        context = f"P is {p}; Q is {q}."
        correct = "True" if value else "False"
        wrongs = ["False", "Cannot be evaluated", "Equivalent to Q -> P"] if value else ["True", "Cannot be evaluated", "Equivalent to Q -> P"]

    elif family == "quantifier_counterexample":
        threshold = rng.randint(3, 8)
        good = [rng.randint(threshold + 1, threshold + 8) for _ in range(4)]
        bad = rng.randint(0, threshold)
        values = good + [bad]
        rng.shuffle(values)
        question = f"Is the universal claim 'every listed value is greater than {threshold}' true?"
        context = f"The complete finite list is {values}."
        correct = "No; one counterexample is enough to refute the universal claim"
        wrongs = [
            "Yes; a majority satisfying the rule proves a universal claim",
            "Yes; one exception is statistically negligible",
            "Cannot determine even though the complete list is given",
        ]

    elif family == "set_inclusion":
        n = rng.randint(3, 7)
        question = "Which relation must follow?"
        context = f"Every member of set A is in set B. Every member of set B is in set C. Set A contains {n} members."
        correct = "Every member of A is in C"
        wrongs = ["Every member of C is in A", "A and C must be identical", "No member of A can be in C"]

    elif family == "ordering_constraints":
        names = rng.sample(list("WXYZ"), 4)
        a, b, c, d = names
        question = "Which ordering statement is forced by the constraints?"
        context = f"{a} occurs before {b}; {b} before {c}; {c} before {d}."
        correct = f"{a} occurs before {d}"
        wrongs = [f"{d} occurs before {a}", f"{c} occurs before {a}", f"{b} occurs after {d}"]

    elif family == "probability_complement":
        pct = rng.randint(12, 78)
        question = "What is the probability of NOT E?"
        context = f"P(E) = {pct}%. E and NOT E are complements."
        correct = f"{100 - pct}%"
        wrongs = [f"{pct}%", f"{max(0, 100 - pct - 1)}%", f"{min(100, 100 - pct + 1)}%"]

    elif family == "contradiction_scope":
        same = rng.choice([True, False])
        question = "Do the two claims form a direct contradiction?"
        if same:
            context = "Claim 1: system R had property M at time T1. Claim 2: the same system R did not have property M at the same time T1 and under the same scope."
            correct = "Yes; they assert M and NOT M under the same scope and time"
            wrongs = ["No; direct negations can always both be true", "No; different sentences are automatically independent", "Cannot assess contradictions in principle"]
        else:
            context = "Claim 1: system R had property M at time T1. Claim 2: system R did not have property M at a later time T2; properties may change over time."
            correct = "No; different times prevent a direct contradiction from being established"
            wrongs = ["Yes; M and NOT M are contradictory regardless of time", "Yes; later evidence retroactively changes T1", "No; because negative claims are never testable"]

    elif family == "timestamp_causality":
        event = rng.randint(100, 300)
        observation = event + rng.randint(1, 20)
        question = "Can this observation be used as pre-event evidence?"
        context = f"The target event time is {event}. The observation was first available at {observation}."
        correct = "No; it became available only after the target event"
        wrongs = ["Yes; timestamps do not matter", "Yes; later evidence can be relabeled pre-event", "Yes; if the observation is accurate"]

    elif family == "provenance_chain":
        question = "What is the strongest justified provenance conclusion?"
        context = "Two reports repeat the same statistic. Both explicitly cite the same original dataset and add no independent measurement."
        correct = "They are two reports but only one underlying evidence source"
        wrongs = ["They are automatically two independent sources", "The shared source makes the statistic false", "Provenance is irrelevant once wording differs"]

    elif family == "evidence_overlap":
        question = "How should the evidence count be treated?"
        context = "Analyst A and Analyst B independently write summaries, but both summaries are generated from the exact same model output and identical source packet."
        correct = "Dependence cannot be excluded; do not count them as two independent confirmations"
        wrongs = ["Count two confirmations because there are two analyst names", "Treat them as independent because the prose differs", "Independence is guaranteed whenever outputs are stored separately"]

    elif family == "future_leakage_boundary":
        lock = rng.randint(50, 150)
        later = lock + rng.randint(1, 15)
        question = "Is the prospective evaluation valid if that later fact influences the locked prediction?"
        context = f"Prediction lock is timestamp {lock}. A market fact first known at timestamp {later} was used while reconstructing the prediction."
        correct = "No; using information first available after the lock is future leakage"
        wrongs = ["Yes; reconstruction makes future facts permissible", "Yes; only the final score matters", "Yes; future facts are allowed if they improve accuracy"]

    elif family == "causal_confounding":
        question = "What causal conclusion is justified?"
        context = "Treatment and outcome are correlated in observational data, but assignment was not randomized and an unmeasured common cause may affect both."
        correct = "Causation is not established because confounding remains possible"
        wrongs = ["Causation is proven by any nonzero correlation", "The outcome must cause the treatment", "Confounding can be ignored in observational data"]

    elif family == "missing_information":
        question = "Can the requested comparison be determined?"
        context = "Only the combined sample mean is reported. Group membership, group variances, and the underlying observations are unavailable. Asked which group has larger variance."
        correct = "No; the available information is insufficient to compare group variances"
        wrongs = ["Yes; the combined mean determines each group variance", "Yes; the larger group must have larger variance", "Yes; variance follows directly from sample size alone"]

    elif family == "adversarial_negation":
        question = "Which option is NOT a reason to reject a claimed prospective result?"
        context = "Consider: post-outcome editing; missing authentic lock timestamp; genuinely independent evidence available before lock; use of outcome data before the claimed lock."
        correct = "Genuinely independent evidence that was available before the lock"
        wrongs = ["Post-outcome editing", "No authentic evidence of the claimed lock time", "Use of outcome data before the claimed lock"]

    elif family == "governance_threshold":
        required = rng.randint(40, 80)
        observed = rng.randint(5, required - 5)
        question = "What is the correct promotion decision?"
        context = f"Policy requires {required} prospectively locked qualifying cases. Only {observed} exist. Engineering tests pass."
        correct = "Do not promote; the prospective evidence threshold is not met"
        wrongs = ["Promote because engineering tests replace prospective evidence", "Backfill historical cases and relabel them prospective", "Promote first and revise the threshold afterward"]

    else:
        raise ValueError(family)

    options, answer = _shuffle(rng, correct, wrongs)
    return Task(tid, family, question, context, options, answer)


def generate_tasks(seed: int, per_family: int) -> list[Task]:
    rng = random.Random(seed)
    tasks = [_task(rng, family, i + 1) for family in FAMILIES for i in range(per_family)]
    rng.shuffle(tasks)
    return tasks


def stage_prompts() -> dict[str, str]:
    return {
        "draft": (
            "Independent Draft solver. Work only from the original task. Re-derive quantities and logic before selecting an option. "
            "Treat insufficiency, scope, timestamps, provenance and causality explicitly. Return JSON only."
        ),
        "attack_a": (
            "Hostile falsifier. Work only from the original task. Assume the obvious answer may be wrong. "
            "Try to refute each plausible conclusion using counterexamples, truth conditions, temporal order, provenance and causal boundaries. "
            "Then select the surviving option. Return JSON only."
        ),
        "attack_b": (
            "Independent alternative solver. Work only from the original task using a different route: reconstruct constraints from first principles, "
            "check negation and missing-information traps, and prefer abstention-like options when the evidence cannot support a stronger claim. Return JSON only."
        ),
        "judge": (
            "Independent verification judge. Work only from the original task and solve it from zero. "
            "Use a checklist: arithmetic, formal truth conditions, scope, time availability, provenance independence, leakage, causal identification, and evidence sufficiency. "
            "Return JSON only."
        ),
    }


def adjudicate_choices(stages: list[dict[str, Any]]) -> dict[str, Any]:
    valid = [s.get("choice") for s in stages if s.get("choice") in set("ABCD")]
    if not valid:
        return {"choice": None, "state": "ABSTAIN", "support": 0, "valid_votes": 0}
    counts = Counter(valid)
    choice, support = counts.most_common(1)[0]
    if support == 4:
        return {"choice": choice, "state": "STRONGLY_SUPPORTED", "support": 4, "valid_votes": len(valid)}
    if support == 3:
        return {"choice": choice, "state": "PARTIALLY_SUPPORTED", "support": 3, "valid_votes": len(valid)}
    return {"choice": None, "state": "INCONCLUSIVE", "support": support, "valid_votes": len(valid)}


def calibrated_confidence(adjudicated: dict[str, Any]) -> int:
    if adjudicated.get("choice") is None:
        return 8
    support = int(adjudicated.get("support") or 0)
    if support >= 4:
        return 32
    if support == 3:
        return 22
    return 10
