from __future__ import annotations

import hashlib
import json
import os
import random
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from flask import Flask, jsonify

POLICY_VERSION = "PRIME_ZERO_BUDGET_ARENA_V1"
ARENA_SCOPE = "RESEARCH_ONLY_NO_PRODUCTION_INFLUENCE"
ZERO_BUDGET = True

app = Flask(__name__)


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _sha(payload: Any) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


@dataclass(frozen=True)
class ArenaTask:
    task_id: str
    category: str
    question: str
    context: str
    options: dict[str, str]
    answer: str

    def public(self) -> dict[str, Any]:
        return {
            "id": self.task_id,
            "category": self.category,
            "question": self.question,
            "context": self.context,
            "options": self.options,
        }


def _make_tasks(seed: int, n: int = 24) -> list[ArenaTask]:
    """Generate exact-answer, mutation-resistant tasks at runtime.

    Answers are computed by the harness and are never placed in the public task payload.
    The point is to test reasoning/orchestration without using a model as the judge.
    """
    rng = random.Random(seed)
    tasks: list[ArenaTask] = []

    for i in range(n):
        kind = i % 6
        a = rng.randint(2, 19)
        b = rng.randint(2, 19)
        c = rng.randint(2, 19)
        token = hashlib.sha256(f"{seed}:{i}:{a}:{b}:{c}".encode()).hexdigest()[:8]
        task_id = f"ZB-{i+1:03d}-{token}"

        if kind == 0:
            # Temporal leakage / prospective evidence.
            lock = 1000 + rng.randint(1, 50)
            outcome = lock + rng.randint(5, 80)
            context = (
                f"Forecast was locked at t={lock}. Outcome was first observed at t={outcome}. "
                "A later analyst wants to edit the locked forecast after seeing the outcome."
            )
            options = {
                "A": "Allow the edit because the outcome is now known.",
                "B": "Keep the original lock immutable; append the outcome separately.",
                "C": "Replace the lock and delete the old record.",
                "D": "Treat the edited record as equally prospective.",
            }
            answer = "B"
            question = "Which action preserves a genuine prospective test?"
            category = "temporal_integrity"

        elif kind == 1:
            # Evidence independence.
            context = (
                "Three judgments were produced by repeated calls to the same model family using the same evidence. "
                "No independent data source or independent model lineage was used."
            )
            options = {
                "A": "Count all three as fully independent confirmations.",
                "B": "Call them independent because the wording differs.",
                "C": "Treat agreement as useful but mark independence as not established.",
                "D": "Ignore all three outputs completely.",
            }
            answer = "C"
            question = "What is the strongest defensible evidence claim?"
            category = "evidence_independence"

        elif kind == 2:
            # Exact arithmetic with distractors.
            x = a * b + c
            options = {
                "A": str(x + 1),
                "B": str(a * (b + c)),
                "C": str(x),
                "D": str(max(0, x - 1)),
            }
            answer = "C"
            question = f"Compute {a} × {b} + {c}."
            context = "Use normal arithmetic precedence."
            category = "exact_arithmetic"

        elif kind == 3:
            # Contradiction detection.
            name = f"artifact-{token}"
            context = (
                f"Record 1 says {name} SHA-256 = aaa{token}. "
                f"Record 2 says the same exact artifact bytes have SHA-256 = bbb{token}. "
                "No transformation, re-encoding, or version change is documented."
            )
            options = {
                "A": "Both hashes can certify the same exact bytes without further explanation.",
                "B": "There is an unresolved provenance contradiction that must be investigated.",
                "C": "The second hash automatically supersedes the first.",
                "D": "Hash mismatches do not matter for artifact identity.",
            }
            answer = "B"
            question = "What conclusion is justified?"
            category = "provenance"

        elif kind == 4:
            # Fail-closed behavior.
            required = a
            observed = rng.randint(0, required - 1)
            context = (
                f"Promotion policy requires at least {required} prospective rows. "
                f"Only {observed} qualifying prospective rows exist. All unit tests pass."
            )
            options = {
                "A": "Promote because unit tests passed.",
                "B": "Promote provisionally and count missing rows later.",
                "C": "Do not promote; the evidence gate is not met.",
                "D": "Backfill historical rows and call them prospective.",
            }
            answer = "C"
            question = "What should the system do?"
            category = "promotion_gate"

        else:
            # Simple formal implication.
            p = rng.choice([True, False])
            q = rng.choice([True, False])
            implication = (not p) or q
            context = f"P={str(p).lower()}, Q={str(q).lower()}. Evaluate the material implication P -> Q."
            options = {"A": "true", "B": "false", "C": "unknown", "D": "contradictory"}
            answer = "A" if implication else "B"
            question = "What is the truth value of P -> Q?"
            category = "formal_logic"

        tasks.append(ArenaTask(task_id, category, question, context, options, answer))

    return tasks


def _selftest() -> dict[str, Any]:
    cases: dict[str, bool] = {}

    t1 = _make_tasks(123456, 24)
    t2 = _make_tasks(123456, 24)
    t3 = _make_tasks(123457, 24)

    cases["same_seed_reproducible"] = [x.public() for x in t1] == [x.public() for x in t2]
    cases["different_seed_changes_tasks"] = [x.public() for x in t1] != [x.public() for x in t3]
    cases["answers_hidden_from_public_payload"] = all("answer" not in x.public() for x in t1)
    cases["all_answers_valid_options"] = all(x.answer in x.options for x in t1)
    cases["all_task_ids_unique"] = len({x.task_id for x in t1}) == len(t1)
    cases["six_categories_present"] = len({x.category for x in t1}) == 6
    cases["zero_budget_default"] = ZERO_BUDGET is True
    cases["production_influence_disabled"] = ARENA_SCOPE == "RESEARCH_ONLY_NO_PRODUCTION_INFLUENCE"

    # Budget firewall: external model calls are impossible until an explicitly free
    # provider is configured AND the operator confirms the provider cannot bill.
    billing_mode = os.getenv("ARENA_BILLING_MODE", "DISABLED").strip().upper()
    provider = os.getenv("ARENA_PROVIDER", "NONE").strip().upper()
    external_enabled = billing_mode == "FREE_ONLY_CONFIRMED" and provider in {"GROQ_FREE", "GEMINI_FREE", "LOCAL_OLLAMA"}
    cases["paid_calls_fail_closed_by_default"] = external_enabled is False

    passed = sum(bool(v) for v in cases.values())
    return {
        "policy_version": POLICY_VERSION,
        "pass": passed == len(cases),
        "passed": passed,
        "total": len(cases),
        "cases": cases,
    }


BOOT_SEED = int.from_bytes(os.urandom(8), "big")
TASKS = _make_tasks(BOOT_SEED, 24)
PUBLIC_TASKS = [t.public() for t in TASKS]
PUBLIC_HASH = _sha(PUBLIC_TASKS)
SELFTEST = _selftest()


def _provider_gate() -> dict[str, Any]:
    billing_mode = os.getenv("ARENA_BILLING_MODE", "DISABLED").strip().upper()
    provider = os.getenv("ARENA_PROVIDER", "NONE").strip().upper()
    allowed = billing_mode == "FREE_ONLY_CONFIRMED" and provider in {"GROQ_FREE", "GEMINI_FREE", "LOCAL_OLLAMA"}
    return {
        "provider": provider,
        "billing_mode": billing_mode,
        "external_calls_allowed": allowed,
        "allowed_free_provider_labels": ["GROQ_FREE", "GEMINI_FREE", "LOCAL_OLLAMA"],
        "rule": "Any provider that can incur paid usage is blocked by this arena.",
    }


@app.get("/")
def root():
    gate = _provider_gate()
    return jsonify({
        "service": "prime-zero-budget-arena",
        "status": "READY" if SELFTEST["pass"] else "SELFTEST_FAILED",
        "policy_version": POLICY_VERSION,
        "scope": ARENA_SCOPE,
        "zero_budget": True,
        "selftest": SELFTEST,
        "provider_gate": gate,
        "benchmark": {
            "task_count": len(PUBLIC_TASKS),
            "public_task_sha256": PUBLIC_HASH,
            "answers_exposed": False,
            "runtime_seed_exposed": False,
        },
        "next_state": "READY_FOR_FREE_PROVIDER_BINDING" if SELFTEST["pass"] else "BLOCKED",
        "observed_utc": _utc(),
    })


@app.get("/selftest")
def selftest():
    return jsonify(SELFTEST)


@app.get("/tasks")
def tasks():
    return jsonify({
        "policy_version": POLICY_VERSION,
        "task_count": len(PUBLIC_TASKS),
        "public_task_sha256": PUBLIC_HASH,
        "tasks": PUBLIC_TASKS,
    })


@app.get("/provider-gate")
def provider_gate():
    return jsonify(_provider_gate())


@app.post("/run")
@app.get("/run")
def run():
    gate = _provider_gate()
    if not gate["external_calls_allowed"]:
        return jsonify({
            "status": "ABSTAIN_ZERO_BUDGET_GATE",
            "reason": "No explicitly confirmed free-only provider is bound. No external model call was made.",
            "provider_gate": gate,
            "public_task_sha256": PUBLIC_HASH,
            "production_influence": False,
        }), 409
    return jsonify({
        "status": "NOT_IMPLEMENTED_PROVIDER_ADAPTER",
        "reason": "Provider binding is allowed by policy but adapter execution is intentionally not implemented in V1 until free-only status is verified.",
        "provider_gate": gate,
        "production_influence": False,
    }), 501


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "10000")))
