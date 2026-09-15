from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from flask import Flask, jsonify, request

HERE = Path(__file__).resolve().parent
PACK = json.loads((HERE / "tasks.json").read_text())
TASKS = PACK["tasks"]
TASK_BY_ID = {t["id"]: t for t in TASKS}

POLICY = """AI ULTRA MODE
- Separate FACT / ASSUMPTION / INFERENCE / UNKNOWN / NOT TESTED.
- Attack the proposed conclusion, then attack the rejection.
- Shared model/source lineage is not independent evidence.
- Reject leakage, hindsight, revised/post-outcome tuning and benchmark reuse.
- Source inspection is not runtime PASS.
- Prefer the weakest defensible conclusion.
- Never manufacture certainty.
- A benchmark win is scoped to that benchmark only.
"""

APP_VERSION = "PRIME_ZERO_BUDGET_ARENA_V1"
ZERO_BUDGET_RULE = "NO_PAID_CALLS_WITHOUT_EXPLICIT_USER_AUTHORIZATION"
DEFAULT_GROQ_MODEL = "openai/gpt-oss-20b"
DEFAULT_GEMINI_MODEL = "gemini-2.5-flash-lite"
DEFAULT_OLLAMA_MODEL = "gpt-oss:20b"

app = Flask(__name__)


def _bool_env(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _public_task(task: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in task.items() if k != "answer"}


def _fmt_task(task: dict[str, Any]) -> str:
    options = "\n".join(f"{k}. {v}" for k, v in task["options"].items())
    return (
        f"TASK {task['id']}\n"
        f"CATEGORY: {task['category']}\n"
        f"QUESTION: {task['question']}\n"
        f"CONTEXT: {task['context']}\n"
        f"OPTIONS:\n{options}\n"
        "Return JSON only: {\"choice\":\"A|B|C|D\",\"confidence\":0-100,\"reason\":\"short reason\"}."
    )


def _extract_json(text: str) -> dict[str, Any]:
    text = (text or "").strip()
    candidates = [text]
    m = re.search(r"\{.*\}", text, flags=re.S)
    if m:
        candidates.append(m.group(0))
    last: Exception | None = None
    for candidate in candidates:
        try:
            data = json.loads(candidate)
            if not isinstance(data, dict):
                raise ValueError("response is not an object")
            choice = str(data.get("choice", "")).upper().strip()
            confidence = int(data.get("confidence", 0))
            reason = str(data.get("reason", "")).strip()
            if choice not in {"A", "B", "C", "D"}:
                raise ValueError("invalid choice")
            if not 0 <= confidence <= 100:
                raise ValueError("invalid confidence")
            return {"choice": choice, "confidence": confidence, "reason": reason[:1000]}
        except Exception as exc:
            last = exc
    raise ValueError(f"invalid JSON answer: {type(last).__name__ if last else 'unknown'}")


def _http_json(url: str, payload: dict[str, Any], headers: dict[str, str], timeout: int = 90) -> dict[str, Any]:
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", **headers},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:500]
        raise RuntimeError(f"HTTP_{exc.code}:{body}") from None


def provider_status() -> dict[str, Any]:
    network_enabled = _bool_env("ZERO_BUDGET_NETWORK_ENABLED")
    return {
        "manual": {
            "configured": True,
            "network": False,
            "cost_guard": "ZERO_COST",
        },
        "groq": {
            "configured": bool(os.getenv("GROQ_API_KEY")),
            "network": network_enabled,
            "model": os.getenv("GROQ_MODEL", DEFAULT_GROQ_MODEL),
            "billing_status": "FREE_TIER_NOT_VERIFIED_BY_ARENA",
        },
        "gemini": {
            "configured": bool(os.getenv("GEMINI_API_KEY")),
            "network": network_enabled,
            "model": os.getenv("GEMINI_MODEL", DEFAULT_GEMINI_MODEL),
            "billing_status": "FREE_TIER_NOT_VERIFIED_BY_ARENA",
        },
        "ollama": {
            "configured": bool(os.getenv("OLLAMA_BASE_URL")),
            "network": network_enabled,
            "model": os.getenv("OLLAMA_MODEL", DEFAULT_OLLAMA_MODEL),
            "billing_status": "LOCAL_OR_USER_CONTROLLED",
        },
    }


def _assert_provider_allowed(provider: str) -> None:
    if provider not in {"groq", "gemini", "ollama"}:
        raise ValueError("unsupported provider")
    if not _bool_env("ZERO_BUDGET_NETWORK_ENABLED"):
        raise RuntimeError("ZERO_BUDGET_NETWORK_DISABLED")
    allow = {
        x.strip().lower()
        for x in os.getenv("ZERO_BUDGET_PROVIDER_ALLOWLIST", "").split(",")
        if x.strip()
    }
    if provider not in allow:
        raise RuntimeError("PROVIDER_NOT_ZERO_BUDGET_ALLOWLISTED")
    status = provider_status()[provider]
    if not status["configured"]:
        raise RuntimeError("PROVIDER_NOT_CONFIGURED")


def _provider_call(provider: str, system: str, user: str) -> tuple[dict[str, Any], dict[str, Any]]:
    _assert_provider_allowed(provider)
    t0 = time.time()
    if provider == "groq":
        base = os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1").rstrip("/")
        model = os.getenv("GROQ_MODEL", DEFAULT_GROQ_MODEL)
        raw = _http_json(
            base + "/chat/completions",
            {
                "model": model,
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
                "temperature": 0,
                "response_format": {"type": "json_object"},
            },
            {"Authorization": "Bearer " + os.environ["GROQ_API_KEY"]},
        )
        text = raw["choices"][0]["message"]["content"]
    elif provider == "ollama":
        base = os.environ["OLLAMA_BASE_URL"].rstrip("/")
        model = os.getenv("OLLAMA_MODEL", DEFAULT_OLLAMA_MODEL)
        raw = _http_json(
            base + "/chat/completions",
            {
                "model": model,
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
                "temperature": 0,
            },
            {"Authorization": "Bearer ollama"},
        )
        text = raw["choices"][0]["message"]["content"]
    else:
        model = os.getenv("GEMINI_MODEL", DEFAULT_GEMINI_MODEL)
        key = os.environ["GEMINI_API_KEY"]
        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            + model
            + ":generateContent?key="
            + key
        )
        raw = _http_json(
            url,
            {
                "systemInstruction": {"parts": [{"text": system}]},
                "contents": [{"role": "user", "parts": [{"text": user}]}],
                "generationConfig": {"temperature": 0, "responseMimeType": "application/json"},
            },
            {},
        )
        text = raw["candidates"][0]["content"]["parts"][0]["text"]
    return _extract_json(text), {"provider": provider, "model": model, "elapsed_sec": round(time.time() - t0, 3)}


def prime_answer(provider: str, task: dict[str, Any]) -> dict[str, Any]:
    base = _fmt_task(task)
    draft, dmeta = _provider_call(provider, POLICY + "\nROLE: initial analyst.", base)
    attack_a, ameta = _provider_call(
        provider,
        POLICY + "\nROLE: ATTACK A. Try to prove the draft wrong. Pick a different option if evidence warrants it.",
        base + "\nDRAFT=" + json.dumps(draft, separators=(",", ":")),
    )
    attack_b, bmeta = _provider_call(
        provider,
        POLICY + "\nROLE: ATTACK B. Try to prove Attack A wrong and identify what survives both attacks.",
        base + "\nDRAFT=" + json.dumps(draft, separators=(",", ":")) + "\nATTACK_A=" + json.dumps(attack_a, separators=(",", ":")),
    )
    final, jmeta = _provider_call(
        provider,
        POLICY + "\nROLE: final judge. Choose the weakest defensible option. Same-provider calls are dependent evidence, not independent votes.",
        base
        + "\nDRAFT=" + json.dumps(draft, separators=(",", ":"))
        + "\nATTACK_A=" + json.dumps(attack_a, separators=(",", ":"))
        + "\nATTACK_B=" + json.dumps(attack_b, separators=(",", ":")),
    )
    return {
        "final": final,
        "trace": {"draft": draft, "attack_a": attack_a, "attack_b": attack_b},
        "calls": [dmeta, ameta, bmeta, jmeta],
        "evidence_independence": "DEPENDENCE_NOT_EXCLUDABLE",
    }


def score_answers(answers: dict[str, Any]) -> dict[str, Any]:
    rows = []
    by_category: dict[str, list[bool]] = defaultdict(list)
    for task in TASKS:
        raw = answers.get(task["id"])
        if isinstance(raw, dict):
            choice = str(raw.get("choice", "")).upper().strip()
        else:
            choice = str(raw or "").upper().strip()
        ok = choice == task["answer"]
        by_category[task["category"]].append(ok)
        rows.append({
            "id": task["id"],
            "category": task["category"],
            "choice": choice or None,
            "correct": ok,
        })
    category_scores = {
        k: {"correct": sum(v), "n": len(v)} for k, v in sorted(by_category.items())
    }
    correct = sum(r["correct"] for r in rows)
    return {
        "correct": correct,
        "n": len(rows),
        "accuracy": round(correct / len(rows), 4) if rows else None,
        "category_scores": category_scores,
        "misses": [r for r in rows if not r["correct"]],
        "rows": rows,
        "claim_scope": "DEVELOPMENT_BENCHMARK_ONLY_NO_GENERAL_SUPERIORITY_CLAIM",
    }


def hostile_selftest() -> dict[str, Any]:
    cases: dict[str, bool] = {}
    cases["unique_task_ids"] = len(TASK_BY_ID) == len(TASKS)
    cases["four_options_each"] = all(set(t["options"]) == {"A", "B", "C", "D"} for t in TASKS)
    cases["valid_answer_keys"] = all(t["answer"] in {"A", "B", "C", "D"} for t in TASKS)
    public = [_public_task(t) for t in TASKS]
    cases["answer_key_not_in_public_tasks"] = all("answer" not in t for t in public)
    perfect = {t["id"]: t["answer"] for t in TASKS}
    cases["scorer_perfect_path"] = score_answers(perfect)["correct"] == len(TASKS)
    wrong = {t["id"]: "A" if t["answer"] != "A" else "B" for t in TASKS}
    cases["scorer_wrong_path"] = score_answers(wrong)["correct"] == 0
    cases["network_fail_closed_by_default"] = not _bool_env("ZERO_BUDGET_NETWORK_ENABLED")
    cases["paid_openai_not_implemented"] = True
    return {
        "pass": all(cases.values()),
        "passed": sum(cases.values()),
        "total": len(cases),
        "cases": cases,
        "version": APP_VERSION,
    }


@app.get("/")
def root():
    return jsonify({
        "service": "prime-zero-budget-arena",
        "status": "RUNNING",
        "version": APP_VERSION,
        "zero_budget_rule": ZERO_BUDGET_RULE,
        "task_pack": PACK["version"],
        "task_count": len(TASKS),
        "network_calls_enabled": _bool_env("ZERO_BUDGET_NETWORK_ENABLED"),
        "astra_role": "FINAL_BOSS_LATER_NOT_REQUIRED_FOR_DEVELOPMENT",
        "world_number_one_claim": "NOT_TESTED",
    })


@app.get("/health")
def health():
    return jsonify({"ok": hostile_selftest()["pass"], "selftest": hostile_selftest()})


@app.get("/providers")
def providers():
    return jsonify(provider_status())


@app.get("/tasks")
def tasks():
    return jsonify({"version": PACK["version"], "tasks": [_public_task(t) for t in TASKS]})


@app.get("/tasks/<task_id>")
def task(task_id: str):
    item = TASK_BY_ID.get(task_id.upper())
    if not item:
        return jsonify({"error": "TASK_NOT_FOUND"}), 404
    return jsonify(_public_task(item))


@app.get("/selftest")
def selftest():
    result = hostile_selftest()
    return jsonify(result), (200 if result["pass"] else 500)


@app.post("/evaluate")
def evaluate():
    payload = request.get_json(silent=True) or {}
    answers = payload.get("answers") or {}
    if not isinstance(answers, dict):
        return jsonify({"error": "answers must be an object keyed by task id"}), 400
    return jsonify({
        "label": str(payload.get("label", "manual"))[:100],
        "score": score_answers(answers),
        "zero_cost": True,
    })


@app.post("/run/<provider>")
def run_provider(provider: str):
    provider = provider.lower().strip()
    try:
        _assert_provider_allowed(provider)
        payload = request.get_json(silent=True) or {}
        ids = payload.get("task_ids") or [t["id"] for t in TASKS[:2]]
        ids = [str(x).upper() for x in ids][:5]
        chosen = [TASK_BY_ID[x] for x in ids if x in TASK_BY_ID]
        if not chosen:
            return jsonify({"error": "NO_VALID_TASKS"}), 400
        outputs: dict[str, Any] = {}
        answers: dict[str, Any] = {}
        for item in chosen:
            result = prime_answer(provider, item)
            outputs[item["id"]] = result
            answers[item["id"]] = result["final"]
        partial = score_answers(answers)
        partial["n_attempted"] = len(chosen)
        partial["full_pack_score_not_valid"] = len(chosen) != len(TASKS)
        return jsonify({
            "provider": provider,
            "outputs": outputs,
            "score": partial,
            "cost_claim": "ZERO_BUDGET_ONLY_IF_USER_ACCOUNT_PROVIDER_TIER_IS_ACTUALLY_FREE",
            "billing_independently_verified": False,
            "victory_claim": "NOT_AUTHORIZED",
        })
    except Exception as exc:
        return jsonify({"error": type(exc).__name__, "detail": str(exc)[:500]}), 400


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "10000")))
