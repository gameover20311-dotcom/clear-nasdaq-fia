from __future__ import annotations

import hashlib
import json
import os
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from flask import Flask, jsonify, request

# Importing V3 installs the hardened 32-task / 8-category arena over the V2 base.
from prime_race import zero_budget_hardening as hardening

arena = hardening.arena
app = Flask(__name__)

POLICY_VERSION = "PRIME_ZERO_BUDGET_MANUAL_CHALLENGE_V1"
SCOPE = "DEVELOPMENT_ONLY_NO_PROMOTION_CLAIM"
DEPENDENCE_NOTE = "DEPENDENCE_NOT_EXCLUDABLE"
ZERO_BUDGET = True


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _sha(payload: Any) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _select_one_per_category() -> list[Any]:
    grouped: dict[str, list[Any]] = defaultdict(list)
    for task in arena.TASKS:
        grouped[task.category].append(task)

    selected: list[Any] = []
    for category in sorted(grouped):
        candidates = sorted(grouped[category], key=lambda t: t.task_id)
        digest = hashlib.sha256(f"{arena.PUBLIC_HASH}:{category}".encode("utf-8")).digest()
        selected.append(candidates[int.from_bytes(digest[:4], "big") % len(candidates)])
    return selected


SELECTED = _select_one_per_category()
SELECTED_IDS = [task.task_id for task in SELECTED]
PUBLIC_CHALLENGE = {
    "policy_version": POLICY_VERSION,
    "scope": SCOPE,
    "zero_budget": True,
    "source_arena_policy": hardening.POLICY_VERSION,
    "source_public_task_sha256": arena.PUBLIC_HASH,
    "task_count": len(SELECTED),
    "categories": [task.category for task in SELECTED],
    "tasks": [task.public() for task in SELECTED],
    "answers_exposed": False,
    "external_model_calls_made_by_service": False,
    "comparison_contract": {
        "same_exact_tasks_required": True,
        "accuracy_is_primary": True,
        "confidence_brier_is_secondary_diagnostic": True,
        "call_budget_is_user_attested_not_independently_verified": True,
        "resubmission_possible": True,
        "therefore_promotion_evidence": False,
    },
    "claims_not_allowed": [
        "WORLD_NUMBER_ONE",
        "PRIME_BEATS_ASTRA",
        "GENERAL_SUPERIORITY",
        "PRODUCTION_READINESS",
    ],
}
CHALLENGE_ID = _sha(PUBLIC_CHALLENGE)
PUBLIC_CHALLENGE["challenge_id"] = CHALLENGE_ID


def _normalize_lane(value: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(value, dict):
        raise ValueError("LANE_MUST_BE_OBJECT")
    if set(value) != set(SELECTED_IDS):
        missing = sorted(set(SELECTED_IDS) - set(value))
        extra = sorted(set(value) - set(SELECTED_IDS))
        raise ValueError(f"LANE_TASK_SET_MISMATCH:missing={missing}:extra={extra}")

    normalized: dict[str, dict[str, Any]] = {}
    for task_id in SELECTED_IDS:
        item = value[task_id]
        if not isinstance(item, dict):
            raise ValueError(f"LANE_ITEM_NOT_OBJECT:{task_id}")
        choice = str(item.get("choice", "")).strip().upper()
        if choice not in {"A", "B", "C", "D"}:
            raise ValueError(f"INVALID_CHOICE:{task_id}")
        raw_confidence = item.get("confidence", 0)
        if isinstance(raw_confidence, bool):
            raise ValueError(f"INVALID_CONFIDENCE:{task_id}")
        try:
            confidence = int(raw_confidence)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"INVALID_CONFIDENCE:{task_id}") from exc
        if not 0 <= confidence <= 100:
            raise ValueError(f"INVALID_CONFIDENCE:{task_id}")
        normalized[task_id] = {"choice": choice, "confidence": confidence}
    return normalized


def _score(lane: dict[str, dict[str, Any]]) -> dict[str, Any]:
    correct = 0
    brier_terms: list[float] = []
    category_totals: dict[str, list[bool]] = defaultdict(list)
    for task in SELECTED:
        item = lane[task.task_id]
        ok = item["choice"] == task.answer
        correct += int(ok)
        p = item["confidence"] / 100.0
        brier_terms.append((p - (1.0 if ok else 0.0)) ** 2)
        category_totals[task.category].append(ok)
    return {
        "correct": correct,
        "n": len(SELECTED),
        "accuracy": round(correct / len(SELECTED), 6),
        "confidence_brier": round(sum(brier_terms) / len(brier_terms), 6),
        "category_accuracy": {
            category: round(sum(flags) / len(flags), 6)
            for category, flags in sorted(category_totals.items())
        },
    }


def _evaluate(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("PAYLOAD_MUST_BE_OBJECT")
    if payload.get("challenge_id") != CHALLENGE_ID:
        raise ValueError("CHALLENGE_ID_MISMATCH")
    prime = _normalize_lane(payload.get("prime"))
    challenger = _normalize_lane(payload.get("challenger"))

    prime_score = _score(prime)
    challenger_score = _score(challenger)
    if prime_score["correct"] > challenger_score["correct"]:
        verdict = "PRIME_BETTER_ON_THIS_DEVELOPMENT_CHALLENGE_ONLY"
    elif prime_score["correct"] < challenger_score["correct"]:
        verdict = "CHALLENGER_BETTER_ON_THIS_DEVELOPMENT_CHALLENGE_ONLY"
    else:
        verdict = "TIE_ON_PRIMARY_ACCURACY"

    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
    receipt = {
        "status": "COMPLETE",
        "policy_version": POLICY_VERSION,
        "challenge_id": CHALLENGE_ID,
        "verdict": verdict,
        "scores": {"prime": prime_score, "challenger": challenger_score},
        "metadata": {
            "prime_label": str(metadata.get("prime_label", "PRIME"))[:120],
            "challenger_label": str(metadata.get("challenger_label", "CHALLENGER"))[:120],
            "same_call_budget_attested": bool(metadata.get("same_call_budget_attested", False)),
        },
        "answer_key_returned": False,
        "per_task_correctness_returned": False,
        "external_model_calls_made_by_service": False,
        "evidence_independence": DEPENDENCE_NOTE,
        "scope": SCOPE,
        "promotion_evidence": False,
        "claims_not_allowed": PUBLIC_CHALLENGE["claims_not_allowed"],
        "finished_utc": _utc(),
    }
    receipt["receipt_sha256"] = _sha(receipt)
    return receipt


def _selftest() -> dict[str, Any]:
    cases: dict[str, bool] = {}
    cases["eight_categories_selected"] = len(SELECTED) == 8 and len({t.category for t in SELECTED}) == 8
    cases["selected_ids_unique"] = len(set(SELECTED_IDS)) == len(SELECTED_IDS)
    cases["answer_key_hidden"] = all("answer" not in task for task in PUBLIC_CHALLENGE["tasks"])
    cases["public_challenge_no_external_calls"] = PUBLIC_CHALLENGE["external_model_calls_made_by_service"] is False
    cases["development_only_scope"] = PUBLIC_CHALLENGE["comparison_contract"]["therefore_promotion_evidence"] is False

    perfect = {task.task_id: {"choice": task.answer, "confidence": 100} for task in SELECTED}
    wrong = {
        task.task_id: {"choice": next(x for x in "ABCD" if x != task.answer), "confidence": 100}
        for task in SELECTED
    }
    cases["perfect_scores_all"] = _score(perfect)["correct"] == len(SELECTED)
    cases["wrong_scores_zero"] = _score(wrong)["correct"] == 0

    base_payload = {
        "challenge_id": CHALLENGE_ID,
        "prime": perfect,
        "challenger": wrong,
        "metadata": {"same_call_budget_attested": True},
    }
    receipt = _evaluate(base_payload)
    cases["receipt_does_not_return_answer_key"] = "answer" not in json.dumps(receipt).lower()
    cases["receipt_marks_nonpromotion"] = receipt["promotion_evidence"] is False
    cases["prime_wins_perfect_vs_wrong"] = receipt["verdict"] == "PRIME_BETTER_ON_THIS_DEVELOPMENT_CHALLENGE_ONLY"

    bad_id_rejected = False
    try:
        _evaluate({**base_payload, "challenge_id": "wrong"})
    except ValueError:
        bad_id_rejected = True
    cases["wrong_challenge_id_rejected"] = bad_id_rejected

    missing_rejected = False
    broken = dict(perfect)
    broken.pop(next(iter(broken)))
    try:
        _evaluate({**base_payload, "prime": broken})
    except ValueError:
        missing_rejected = True
    cases["missing_task_rejected"] = missing_rejected

    passed = sum(bool(v) for v in cases.values())
    return {
        "pass": passed == len(cases),
        "passed": passed,
        "total": len(cases),
        "cases": cases,
        "policy_version": POLICY_VERSION,
        "challenge_id": CHALLENGE_ID,
    }


SELFTEST = _selftest()


@app.get("/")
def root():
    return jsonify({
        "service": "prime-zero-budget-manual-challenge",
        "status": "READY" if SELFTEST["pass"] else "SELFTEST_FAILED",
        "policy_version": POLICY_VERSION,
        "scope": SCOPE,
        "zero_budget": True,
        "selftest": SELFTEST,
        "challenge_id": CHALLENGE_ID,
        "task_count": len(SELECTED),
        "external_model_calls_made_by_service": False,
        "next_state": "READY_FOR_MANUAL_FREE_UI_COMPARISON" if SELFTEST["pass"] else "BLOCKED",
    })


@app.get("/challenge")
def challenge():
    return jsonify(PUBLIC_CHALLENGE)


@app.get("/selftest")
def selftest():
    return jsonify(SELFTEST), (200 if SELFTEST["pass"] else 500)


@app.post("/score")
def score():
    try:
        return jsonify(_evaluate(request.get_json(silent=True)))
    except ValueError as exc:
        return jsonify({"status": "REJECTED", "error": str(exc)[:500], "promotion_evidence": False}), 400


if __name__ == "__main__":
    if not SELFTEST["pass"]:
        raise SystemExit("manual zero-budget challenge selftest failed")
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "10000")))
