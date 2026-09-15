from __future__ import annotations

import hashlib
import json
import os
import random
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from flask import Flask, jsonify

from prime_race.zero_budget_providers import ProviderConfig, ProviderError, call_free_provider

POLICY_VERSION = "PRIME_ZERO_BUDGET_ARENA_V2"
ARENA_SCOPE = "RESEARCH_ONLY_NO_PRODUCTION_INFLUENCE"
ZERO_BUDGET = True
DEPENDENCE_NOTE = "DEPENDENCE_NOT_EXCLUDABLE"

app = Flask(__name__)
_run_lock = threading.Lock()
_last_run: dict[str, Any] = {"status": "NOT_RUN"}


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
    """Generate exact-answer tasks at runtime without exposing answer keys."""
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


def _fmt_task(task: ArenaTask) -> str:
    options = "\n".join(f"{k}. {v}" for k, v in task.options.items())
    return (
        f"TASK {task.task_id}\nCATEGORY: {task.category}\nQUESTION:\n{task.question}\n\n"
        f"EVIDENCE/CONTEXT:\n{task.context}\n\nOPTIONS:\n{options}\n\n"
        "Return JSON only with choice, confidence (0-100), and reason. Choose exactly one option."
    )


def _plain(config: ProviderConfig, task: ArenaTask) -> dict[str, Any]:
    system = (
        "You are in a blind benchmark. Use only supplied evidence. Do not assume missing facts. "
        "Prefer abstention-like conservative reasoning over invented evidence, but you must choose A/B/C/D."
    )
    return call_free_provider(config, system, _fmt_task(task))


def _prime(config: ProviderConfig, task: ArenaTask) -> dict[str, Any]:
    base = _fmt_task(task)
    policy = (
        "ULTRA MODE: evidence over confidence; falsification over confirmation; no fake PASS; "
        "separate fact from assumption; attack the current answer before accepting it. "
        "Repeated calls to the same model/provider are not independent evidence."
    )
    draft = call_free_provider(config, policy + " ROLE: initial analyst.", base)
    attack = call_free_provider(
        config,
        policy + " ROLE: hostile attacker. Try to prove the draft wrong. Prefer the strongest alternative if warranted.",
        base + "\n\nDRAFT=" + json.dumps(draft, sort_keys=True),
    )
    counter = call_free_provider(
        config,
        policy + " ROLE: counter-attacker. Try to prove the attack wrong and identify what survives both sides.",
        base + "\n\nDRAFT=" + json.dumps(draft, sort_keys=True) + "\nATTACK=" + json.dumps(attack, sort_keys=True),
    )
    final = call_free_provider(
        config,
        policy + " ROLE: final judge. Choose the weakest defensible answer supported by the supplied evidence.",
        base
        + "\n\nDRAFT=" + json.dumps(draft, sort_keys=True)
        + "\nATTACK=" + json.dumps(attack, sort_keys=True)
        + "\nCOUNTER=" + json.dumps(counter, sort_keys=True),
    )
    final["trace"] = {"draft": draft, "attack": attack, "counter": counter}
    final["evidence_independence"] = DEPENDENCE_NOTE
    return final


def _score(outputs: dict[str, dict[str, Any]], tasks: list[ArenaTask]) -> dict[str, Any]:
    rows = []
    for task in tasks:
        got = str(outputs.get(task.task_id, {}).get("choice", ""))
        ok = got == task.answer
        rows.append({"id": task.task_id, "category": task.category, "got": got, "ok": ok})
    correct = sum(1 for row in rows if row["ok"])
    return {
        "correct": correct,
        "n": len(rows),
        "accuracy": round(correct / len(rows), 6) if rows else 0.0,
        "rows": rows,
    }


def _execute_arena() -> dict[str, Any]:
    gate = _provider_gate()
    if not gate["external_calls_allowed"]:
        return {
            "status": "ABSTAIN_ZERO_BUDGET_GATE",
            "reason": "No explicitly confirmed free-only provider is bound. No external model call was made.",
            "provider_gate": gate,
            "public_task_sha256": PUBLIC_HASH,
            "production_influence": False,
        }

    provider = gate["provider"]
    model = os.getenv("ARENA_MODEL", "").strip()
    if not model:
        return {
            "status": "ABSTAIN_MODEL_NOT_CONFIGURED",
            "provider_gate": gate,
            "production_influence": False,
        }

    limit = max(1, min(int(os.getenv("ARENA_TASK_LIMIT", "4")), 12))
    tasks = TASKS[:limit]
    config = ProviderConfig(label=provider, model=model, timeout_seconds=max(10, min(int(os.getenv("ARENA_TIMEOUT_SECONDS", "45")), 90)))

    outputs: dict[str, dict[str, dict[str, Any]]] = {"plain": {}, "prime": {}}
    failures: list[dict[str, str]] = []

    for task in tasks:
        try:
            outputs["plain"][task.task_id] = _plain(config, task)
            outputs["prime"][task.task_id] = _prime(config, task)
        except ProviderError as exc:
            failures.append({"id": task.task_id, "error": str(exc)[:500]})
            break

    completed_ids = set(outputs["plain"]) & set(outputs["prime"])
    completed_tasks = [task for task in tasks if task.task_id in completed_ids]
    scores = {
        "plain": _score(outputs["plain"], completed_tasks),
        "prime": _score(outputs["prime"], completed_tasks),
    }

    verdict = "INCONCLUSIVE"
    if completed_tasks and not failures:
        if scores["prime"]["correct"] > scores["plain"]["correct"]:
            verdict = "PRIME_BETTER_ON_THIS_RUN_ONLY"
        elif scores["prime"]["correct"] < scores["plain"]["correct"]:
            verdict = "PLAIN_BETTER_ON_THIS_RUN_ONLY"
        else:
            verdict = "TIE_ON_THIS_RUN_ONLY"

    result = {
        "status": "COMPLETE" if completed_tasks and not failures else "INCONCLUSIVE_PROVIDER_FAILURE",
        "verdict": verdict,
        "policy_version": POLICY_VERSION,
        "provider": provider,
        "model": model,
        "tasks_requested": len(tasks),
        "tasks_completed": len(completed_tasks),
        "public_task_sha256": PUBLIC_HASH,
        "scores": scores,
        "failures": failures,
        "outputs": outputs,
        "evidence_independence": DEPENDENCE_NOTE,
        "claims_not_allowed": [
            "WORLD_NUMBER_ONE",
            "PRIME_BEATS_ASTRA",
            "GENERAL_SUPERIORITY",
            "PRODUCTION_READINESS",
        ],
        "production_influence": False,
        "finished_utc": _utc(),
    }
    result["result_sha256"] = _sha(result)
    return result


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
        "last_run": _last_run,
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


@app.get("/result")
def result():
    return jsonify(_last_run)


@app.post("/run")
@app.get("/run")
def run():
    global _last_run
    if not _run_lock.acquire(blocking=False):
        return jsonify({"status": "BUSY", "production_influence": False}), 409
    try:
        _last_run = _execute_arena()
        code = 200 if _last_run.get("status") == "COMPLETE" else 409
        return jsonify(_last_run), code
    finally:
        _run_lock.release()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "10000")))
