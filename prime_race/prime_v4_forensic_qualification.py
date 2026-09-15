from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import platform
import random
import re
import sys
import time
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import prime_repair_eval as legacy
import prime_ultra_v4 as v4

POLICY_VERSION = "PRIME_V4_FORENSIC_QUALIFICATION_V1"
MODEL_ID = os.getenv("PRIME_V4_MODEL_ID", "HuggingFaceTB/SmolLM2-360M-Instruct")
SEED = int(os.getenv("PRIME_V4_FORENSIC_SEED", "2609152359"))
TASKS_PER_FAMILY = int(os.getenv("PRIME_V4_TASKS_PER_FAMILY", "8"))
OUT = Path(os.getenv("PRIME_V4_FORENSIC_OUT", "prime_v4_forensic_results"))
BASE_VERSION = "BASE_PRIME_V1_FROZEN"
CANDIDATE_VERSION = "PRIME_ULTRA_V4_UNCHANGED"
BURNED_TASKSET_HASHES = {
    "57f804594569815880f387883d92d0bd0b43f9ce46316e4b3babba55ba5bba07",
    "ce0e102fb7bfc8d4cf01c19d67adb9fb3f820be331eadc16e3579e605ddad048",
}

FAMILIES = list(v4.FAMILIES)
LABELS = "ABCD"


def canonical_json(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def sha(obj: Any) -> str:
    return hashlib.sha256(canonical_json(obj)).hexdigest()


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


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


def _place_options(rng: random.Random, correct: str, wrongs: list[str], forced_label: str) -> tuple[dict[str, str], str]:
    if forced_label not in LABELS:
        raise ValueError("invalid forced label")
    if len(wrongs) != 3 or len(set([correct, *wrongs])) != 4:
        raise ValueError("options must be four unique strings")
    remaining_labels = [x for x in LABELS if x != forced_label]
    shuffled_wrongs = list(wrongs)
    rng.shuffle(shuffled_wrongs)
    options = {forced_label: correct}
    for label, wrong in zip(remaining_labels, shuffled_wrongs):
        options[label] = wrong
    return {label: options[label] for label in LABELS}, forced_label


def _task(rng: random.Random, family: str, index: int, forced_label: str) -> Task:
    tid = f"FV4-{family}-{index:03d}"

    if family == "arithmetic_chain":
        a = rng.randint(21, 93)
        b = rng.randint(3, 11)
        c = rng.randint(2, 19)
        d = rng.randint(2, 7)
        result = a * b - c + d
        question = "What is the exact result after applying the stated operations in order?"
        context = f"Start with {a}; multiply by {b}; subtract {c}; then add {d}."
        correct = str(result)
        wrongs = [str(result + 1), str(result - 1), str(a * (b - c) + d)]

    elif family == "boolean_truth_table":
        p = rng.choice([True, False])
        q = rng.choice([True, False])
        r = rng.choice([True, False])
        value = (p and (not q)) or (r and q)
        question = "Evaluate (P AND NOT Q) OR (R AND Q)."
        context = f"P={p}; Q={q}; R={r}."
        correct = "True" if value else "False"
        wrongs = [x for x in ["True", "False", "Undefined", "Both true and false"] if x != correct][:3]

    elif family == "conditional_logic":
        p = rng.choice([True, False])
        q = rng.choice([True, False])
        value = (not p) or q
        question = "Evaluate the material implication P -> Q."
        context = f"For this case, P={p} and Q={q}."
        correct = "True" if value else "False"
        wrongs = [x for x in ["True", "False", "Cannot be evaluated", "Equivalent to Q -> P"] if x != correct][:3]

    elif family == "quantifier_counterexample":
        threshold = rng.randint(4, 15)
        good = [rng.randint(threshold + 1, threshold + 20) for _ in range(5)]
        bad = rng.randint(-2, threshold)
        values = good + [bad]
        rng.shuffle(values)
        question = f"Is the universal claim 'every listed value is greater than {threshold}' true?"
        context = f"The complete finite list is {values}."
        correct = "No; at least one listed value is a counterexample"
        wrongs = [
            "Yes; a majority is enough for a universal claim",
            "Yes; one exception can be ignored",
            "Cannot determine although the complete list is given",
        ]

    elif family == "set_inclusion":
        n = rng.randint(2, 12)
        tag = rng.randint(100, 999)
        question = "Which relation must follow from the stated inclusions?"
        context = f"Case {tag}: every member of A is in B; every member of B is in C; A contains {n} members."
        correct = "Every member of A is in C"
        wrongs = ["Every member of C is in A", "A and C must be identical", "No member of A can be in C"]

    elif family == "ordering_constraints":
        names = rng.sample(["K", "L", "M", "N", "P", "Q"], 4)
        a, b, c, d = names
        question = "Which ordering statement is forced?"
        context = f"{a} is before {b}; {b} is before {c}; {c} is before {d}."
        correct = f"{a} is before {d}"
        wrongs = [f"{d} is before {a}", f"{c} is before {a}", f"{b} is after {d}"]

    elif family == "probability_complement":
        numerator = rng.randint(7, 83)
        denominator = 100
        question = "What is P(NOT E)?"
        context = f"P(E)={numerator}/{denominator}; E and NOT E are complements."
        correct = f"{denominator - numerator}/{denominator}"
        wrongs = [f"{numerator}/{denominator}", f"{max(0, denominator - numerator - 1)}/{denominator}", f"{min(denominator, denominator - numerator + 1)}/{denominator}"]

    elif family == "contradiction_scope":
        same_scope = rng.choice([True, False])
        t1 = rng.randint(10, 80)
        t2 = t1 if same_scope else t1 + rng.randint(1, 12)
        scope = f"scope-{rng.randint(100,999)}"
        question = "Do the claims establish a direct contradiction?"
        if same_scope:
            context = f"Under {scope} at T={t1}, claim 1 says R has M; claim 2 says the same R does not have M under the same {scope} at T={t2}."
            correct = "Yes; M and NOT M are asserted for the same object, scope, and time"
            wrongs = ["No; direct negations can always both be true", "No; wording differences make them independent", "Cannot assess contradiction in principle"]
        else:
            context = f"Under {scope}, claim 1 says R has M at T={t1}; claim 2 says R does not have M at later T={t2}; M may change over time."
            correct = "No; different times prevent a direct contradiction from being established"
            wrongs = ["Yes; time never matters for contradiction", "Yes; the later claim rewrites the earlier state", "No; negative claims are never testable"]

    elif family == "timestamp_causality":
        event = rng.randint(200, 900)
        observation = event + rng.randint(1, 60)
        source = f"feed-{rng.randint(10,99)}"
        question = "Can the observation be used as pre-event evidence?"
        context = f"Target event T={event}. {source} first published the observation at T={observation}."
        correct = "No; it first became available after the target event"
        wrongs = ["Yes; timestamps do not constrain evidence", "Yes; later facts can be relabeled pre-event", "Yes; accuracy alone makes it pre-event"]

    elif family == "provenance_chain":
        reports = rng.randint(2, 5)
        source = f"dataset-{rng.randint(1000,9999)}"
        stat = rng.randint(20, 80)
        question = "What is the strongest justified provenance conclusion?"
        context = f"{reports} separately written reports all quote statistic {stat} from the same original source {source}; none adds an independent measurement."
        correct = "There are multiple reports but only one underlying measurement source"
        wrongs = ["Each report is automatically an independent measurement", "Shared provenance proves the statistic false", "Different prose makes the evidence independent"]

    elif family == "evidence_overlap":
        analysts = rng.randint(2, 5)
        packet = f"packet-{rng.randint(100,999)}"
        model_run = f"run-{rng.randint(1000,9999)}"
        question = "How should the confirmations be counted?"
        context = f"{analysts} analyst summaries are all derived from the exact same model output {model_run} and the same source packet {packet}."
        correct = "Dependence cannot be excluded; do not count them as independent confirmations"
        wrongs = ["Count each analyst summary as fully independent", "Different wording guarantees independence", "Separate storage locations guarantee independence"]

    elif family == "future_leakage_boundary":
        lock = rng.randint(100, 500)
        later = lock + rng.randint(1, 50)
        field = f"signal-{rng.randint(10,99)}"
        question = "Is the claimed prospective evaluation valid if that fact influences the locked prediction?"
        context = f"Prediction lock T={lock}. {field} was first available at T={later} and was used when reconstructing the prediction."
        correct = "No; information first available after the lock is future leakage"
        wrongs = ["Yes; reconstruction permits future information", "Yes; only final accuracy matters", "Yes; later information is allowed if it is reliable"]

    elif family == "causal_confounding":
        treatment = rng.choice(["program A", "exposure X", "policy P", "training T"])
        outcome = rng.choice(["score Y", "recovery R", "output O", "retention Z"])
        confounder = rng.choice(["baseline skill", "site selection", "age", "prior demand", "risk preference"])
        question = "What causal conclusion is justified?"
        context = f"{treatment} and {outcome} are correlated observationally; assignment was not randomized, and unmeasured {confounder} may affect both."
        correct = "Causation is not established because confounding remains possible"
        wrongs = ["Any nonzero correlation proves causation", "The outcome must cause the treatment", "Confounding can be ignored in observational data"]

    elif family == "missing_information":
        mean = rng.randint(20, 90)
        total_n = rng.randint(30, 180)
        groups = rng.choice([2, 3])
        question = "Can the requested variance comparison be determined?"
        context = f"Across {groups} groups with total n={total_n}, only the combined sample mean {mean} is reported. Group assignments, group variances, and raw observations are unavailable."
        correct = "No; the available information is insufficient to compare group variances"
        wrongs = ["Yes; the combined mean determines every group variance", "Yes; the largest group must have the largest variance", "Yes; total sample size alone determines the ordering of variances"]

    elif family == "adversarial_negation":
        lock = rng.randint(100, 500)
        pre = lock - rng.randint(1, 30)
        post = lock + rng.randint(1, 30)
        question = "Which item is NOT a reason to reject the claimed prospective result?"
        context = (
            f"Lock T={lock}. Consider four facts: an independent source was genuinely available at T={pre}; "
            f"one record was edited at T={post} after outcome review; one claimed lock lacks authentic timestamp evidence; "
            f"and one outcome-derived field was inserted after T={lock}."
        )
        correct = f"The independent source genuinely available before the lock at T={pre}"
        wrongs = [f"The post-outcome edit at T={post}", "The claimed lock with no authentic timestamp evidence", "The outcome-derived field inserted after the lock"]

    elif family == "governance_threshold":
        required = rng.randint(45, 120)
        observed = rng.randint(5, required - 5)
        gate = f"gate-{rng.randint(100,999)}"
        question = "What is the correct promotion decision?"
        context = f"{gate} requires {required} prospectively locked qualifying cases; only {observed} exist. Engineering tests pass."
        correct = "Do not promote; the prospective evidence threshold is not met"
        wrongs = ["Promote because engineering tests replace prospective evidence", "Backfill historical cases and relabel them prospective", "Promote first and lower the threshold afterward"]

    else:
        raise ValueError(family)

    options, answer = _place_options(rng, correct, wrongs, forced_label)
    return Task(tid, family, question, context, options, answer)


def semantic_key(task: Task) -> str:
    return sha({
        "family": task.family,
        "question": task.question.strip().lower(),
        "context": task.context.strip().lower(),
        "option_values": sorted(v.strip().lower() for v in task.options.values()),
    })


def generate_tasks(seed: int, per_family: int) -> list[Task]:
    rng = random.Random(seed)
    tasks: list[Task] = []
    seen: set[str] = set()
    for family_index, family in enumerate(FAMILIES):
        for i in range(per_family):
            forced_label = LABELS[(family_index * per_family + i) % 4]
            for _attempt in range(100):
                task = _task(rng, family, i + 1, forced_label)
                key = semantic_key(task)
                if key not in seen:
                    seen.add(key)
                    tasks.append(task)
                    break
            else:
                raise RuntimeError(f"SEMANTIC_DUPLICATE_GENERATOR_STUCK:{family}:{i+1}")
    rng.shuffle(tasks)
    return tasks


def parse_answer(text: str) -> dict[str, Any]:
    raw = text.strip()
    choice = None
    explicit = re.search(r'["\']?choice["\']?\s*[:=]\s*["\']?([ABCD])\b', raw, flags=re.I)
    if explicit:
        choice = explicit.group(1).upper()
    if choice is None:
        leading = re.match(r'^\s*(?:answer\s*[:=]?\s*)?([ABCD])(?=\s|[\.\),;:\-]|$)', raw, flags=re.I)
        if leading:
            choice = leading.group(1).upper()
    cm = re.search(r'["\']?confidence["\']?\s*[:=]\s*([0-9]{1,3})', raw, flags=re.I)
    confidence = max(0, min(100, int(cm.group(1)))) if cm else None
    if choice not in set(LABELS):
        return {"choice": None, "confidence": confidence, "raw": raw, "parse_error": True}
    return {"choice": choice, "confidence": confidence, "raw": raw, "parse_error": False}


def task_text(task: dict[str, Any]) -> str:
    options = "\n".join(f"{k}. {v}" for k, v in task["options"].items())
    return (
        f"QUESTION: {task['question']}\nCONTEXT: {task['context']}\nOPTIONS:\n{options}\n"
        "Return JSON only: {\"choice\":\"A|B|C|D\",\"confidence\":0-100}."
    )


def majority_three(stages: list[dict[str, Any]]) -> dict[str, Any]:
    valid = [s.get("choice") for s in stages if s.get("choice") in set(LABELS)]
    if not valid:
        return {"choice": None, "state": "ABSTAIN"}
    counts = Counter(valid)
    ranked = counts.most_common()
    choice, support = ranked[0]
    second = ranked[1][1] if len(ranked) > 1 else 0
    if support >= 2 and support > second:
        return {"choice": choice, "state": "PARTIALLY_SUPPORTED" if support == 2 else "STRONGLY_SUPPORTED"}
    return {"choice": None, "state": "INCONCLUSIVE"}


def selftest() -> dict[str, Any]:
    tasks = generate_tasks(884422, 8)
    public = [t.public() for t in tasks]
    semantic = [semantic_key(t) for t in tasks]
    labels = Counter(t.answer for t in tasks)
    by_family_labels = {
        family: Counter(t.answer for t in tasks if t.family == family)
        for family in FAMILIES
    }
    checks = {
        "task_count_128": len(tasks) == 128,
        "all_16_families": set(t.family for t in tasks) == set(FAMILIES),
        "no_answer_in_public_payload": all("answer" not in p for p in public),
        "semantic_tasks_unique": len(semantic) == len(set(semantic)) == 128,
        "overall_answer_labels_balanced": labels == Counter({"A": 32, "B": 32, "C": 32, "D": 32}),
        "per_family_answer_labels_balanced": all(c == Counter({"A": 2, "B": 2, "C": 2, "D": 2}) for c in by_family_labels.values()),
        "candidate_verifier_override_false": v4.REASONING_VERIFIER_OVERRIDE is False,
        "candidate_policy_identity_v4": v4.POLICY_VERSION == "PRIME_ULTRA_V4",
        "strict_parser_rejects_ambiguous_prose": parse_answer("The discussion mentions A and B but gives no explicit choice.")["choice"] is None,
        "strict_parser_accepts_explicit_choice": parse_answer('{"choice":"C","confidence":61}')["choice"] == "C",
    }
    passed = sum(bool(x) for x in checks.values())
    return {"pass": passed == len(checks), "passed": passed, "total": len(checks), "checks": checks}


def execute(public_tasks: list[dict[str, Any]]) -> dict[str, Any]:
    import torch
    import transformers
    import huggingface_hub
    from huggingface_hub import model_info
    from transformers import AutoModelForCausalLM, AutoTokenizer

    torch.set_num_threads(max(1, min(2, os.cpu_count() or 1)))
    resolved_model_sha = str(model_info(MODEL_ID).sha)
    tokenizer = AutoTokenizer.from_pretrained(MODEL_ID, revision=resolved_model_sha)
    model = AutoModelForCausalLM.from_pretrained(MODEL_ID, revision=resolved_model_sha, torch_dtype=torch.float32)
    model.eval()

    calls = {"base": 0, "v4": 0}
    tokens = {"base": {"input": 0, "output": 0}, "v4": {"input": 0, "output": 0}}
    latency = {"base": 0.0, "v4": 0.0}
    parse_errors = {"base": 0, "v4": 0}
    execution_order: list[dict[str, Any]] = []

    def call(system: str, user: str, lane: str) -> dict[str, Any]:
        start = time.perf_counter()
        prompt = tokenizer.apply_chat_template([
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ], tokenize=False, add_generation_prompt=True)
        inputs = tokenizer(prompt, return_tensors="pt")
        with torch.inference_mode():
            out = model.generate(
                **inputs,
                max_new_tokens=44,
                do_sample=False,
                pad_token_id=tokenizer.eos_token_id,
            )
        gen = out[0, inputs["input_ids"].shape[1]:]
        text = tokenizer.decode(gen, skip_special_tokens=True).strip()
        parsed = parse_answer(text)
        calls[lane] += 1
        parse_errors[lane] += int(bool(parsed.get("parse_error")))
        latency[lane] += time.perf_counter() - start
        tokens[lane]["input"] += int(inputs["input_ids"].numel())
        tokens[lane]["output"] += int(gen.numel())
        return parsed

    prompts = v4.stage_prompts()
    base_final: dict[str, dict[str, Any]] = {}
    stage_out = {"draft": {}, "attack_a": {}, "attack_b": {}, "judge": {}, "three_stage": {}, "final": {}}
    traces: dict[str, Any] = {}

    def run_base(task: dict[str, Any]) -> dict[str, Any]:
        text = task_text(task)
        bd = call("Initial analyst. Solve the task and return only requested JSON.", text, "base")
        ba = call("Hostile critic. Check whether the draft is wrong; return your own requested JSON.", text + "\nDRAFT=" + json.dumps(bd), "base")
        bc = call("Counter-critic. Assess draft and attack; return requested JSON.", text + "\nDRAFT=" + json.dumps(bd) + "\nATTACK=" + json.dumps(ba), "base")
        bf = call("Final judge. Choose the best answer from the evidence and prior stages; return requested JSON.", text + "\nDRAFT=" + json.dumps(bd) + "\nATTACK=" + json.dumps(ba) + "\nCOUNTER=" + json.dumps(bc), "base")
        final = {
            "choice": bf.get("choice"),
            "confidence": bf.get("confidence") if isinstance(bf.get("confidence"), int) else 50,
            "state": "WEAK_EVIDENCE" if bf.get("choice") else "ABSTAIN",
        }
        return {"draft": bd, "attack_a": ba, "counter": bc, "final_raw": bf, "final": final}

    def run_v4(task: dict[str, Any]) -> dict[str, Any]:
        text = task_text(task)
        vd = call(prompts["draft"], text, "v4")
        va = call(prompts["attack_a"], text, "v4")
        vb = call(prompts["attack_b"], text, "v4")
        vj = call(prompts["judge"], text, "v4")
        three = majority_three([vd, va, vb])
        adjudicated = v4.adjudicate_choices([vd, va, vb, vj])
        final = {
            "choice": adjudicated.get("choice"),
            "confidence": v4.calibrated_confidence(adjudicated),
            "state": adjudicated.get("state"),
            "support": adjudicated.get("support"),
        }
        return {
            "draft": vd,
            "attack_a": va,
            "attack_b": vb,
            "judge": vj,
            "three_stage": {"choice": three.get("choice"), "confidence": 20 if three.get("choice") else 8, "state": three.get("state")},
            "final": final,
        }

    for idx, task in enumerate(public_tasks):
        tid = str(task["id"])
        if idx % 2 == 0:
            execution_order.append({"id": tid, "first": "base", "second": "v4"})
            b = run_base(task)
            n = run_v4(task)
        else:
            execution_order.append({"id": tid, "first": "v4", "second": "base"})
            n = run_v4(task)
            b = run_base(task)
        base_final[tid] = b["final"]
        for name in ("draft", "attack_a", "attack_b", "judge", "three_stage", "final"):
            raw = n[name]
            if name in {"draft", "attack_a", "attack_b", "judge"}:
                stage_out[name][tid] = {
                    "choice": raw.get("choice"),
                    "confidence": 20 if raw.get("choice") else 8,
                    "state": "WEAK_EVIDENCE" if raw.get("choice") else "ABSTAIN",
                }
            else:
                stage_out[name][tid] = raw
        traces[tid] = {"base": b, "v4": n}

    return {
        "base": base_final,
        **stage_out,
        "traces": traces,
        "calls": calls,
        "tokens": tokens,
        "latency_seconds": {k: round(v, 3) for k, v in latency.items()},
        "parse_errors": parse_errors,
        "execution_order": execution_order,
        "retries": {"base": 0, "v4": 0},
        "timeouts": {"base": 0, "v4": 0},
        "provider": "LOCAL_HUGGINGFACE_TRANSFORMERS",
        "model_id": MODEL_ID,
        "resolved_model_sha": resolved_model_sha,
        "environment": {
            "python": sys.version,
            "platform": platform.platform(),
            "torch": torch.__version__,
            "transformers": transformers.__version__,
            "huggingface_hub": huggingface_hub.__version__,
        },
    }


def score(outputs: dict[str, dict[str, Any]], public_tasks: list[dict[str, Any]], answer_key: dict[str, str]) -> dict[str, Any]:
    rows = []
    brier = []
    confs = []
    for task in public_tasks:
        tid = str(task["id"])
        out = outputs[tid]
        choice = out.get("choice")
        answer = answer_key[tid]
        ok = choice == answer
        confidence = int(out.get("confidence") or 0)
        p = confidence / 100.0
        brier.append((p - (1.0 if ok else 0.0)) ** 2)
        confs.append(confidence)
        rows.append({
            "id": tid,
            "family": task["category"],
            "choice": choice,
            "answer": answer,
            "ok": ok,
            "confidence": confidence,
            "state": str(out.get("state") or "UNKNOWN"),
        })
    n = len(rows)
    mean = sum(confs) / n
    variance = sum((x - mean) ** 2 for x in confs) / n
    family = {}
    for fam in FAMILIES:
        rr = [r for r in rows if r["family"] == fam]
        correct = sum(int(r["ok"]) for r in rr)
        family[fam] = {"correct": correct, "n": len(rr), "accuracy": round(correct / len(rr), 6)}
    correct = sum(int(r["ok"]) for r in rows)
    abstains = sum(int(r["choice"] is None) for r in rows)
    return {
        "correct": correct,
        "n": n,
        "accuracy": round(correct / n, 6),
        "abstains": abstains,
        "abstain_rate": round(abstains / n, 6),
        "confidence_brier": round(sum(brier) / n, 6),
        "confidence_mean": round(mean, 3),
        "confidence_variance": round(variance, 3),
        "family": family,
        "rows": rows,
    }


def paired(base_rows: list[dict[str, Any]], new_rows: list[dict[str, Any]]) -> dict[str, Any]:
    base = {r["id"]: r for r in base_rows}
    new = {r["id"]: r for r in new_rows}
    new_wins = base_wins = ties = 0
    for tid in base:
        b = bool(base[tid]["ok"])
        n = bool(new[tid]["ok"])
        if n and not b:
            new_wins += 1
        elif b and not n:
            base_wins += 1
        else:
            ties += 1
    discordant = new_wins + base_wins
    if discordant:
        k = min(new_wins, base_wins)
        tail = sum(math.comb(discordant, i) for i in range(k + 1)) / (2 ** discordant)
        p = min(1.0, 2 * tail)
    else:
        p = 1.0
    return {"new_wins": new_wins, "base_wins": base_wins, "ties": ties, "discordant": discordant, "exact_two_sided_p": p}


def diagnostics(execution: dict[str, Any], public_tasks: list[dict[str, Any]], answer_key: dict[str, str]) -> dict[str, Any]:
    d = Counter()
    patterns = Counter()
    verifier_disagreements = 0
    verifier_coverage = 0
    hybrid: dict[str, dict[str, Any]] = {}
    for task in public_tasks:
        tid = str(task["id"])
        ans = answer_key[tid]
        vd = execution["draft"][tid]
        va = execution["attack_a"][tid]
        vb = execution["attack_b"][tid]
        vj = execution["judge"][tid]
        three = execution["three_stage"][tid]
        final = execution["final"][tid]
        d_ok = vd.get("choice") == ans
        a_ok = va.get("choice") == ans
        b_ok = vb.get("choice") == ans
        j_ok = vj.get("choice") == ans
        three_ok = three.get("choice") == ans
        final_ok = final.get("choice") == ans
        d["attack_a_agreements"] += int(va.get("choice") == vd.get("choice"))
        d["attack_a_disagreements"] += int(va.get("choice") != vd.get("choice"))
        d["attack_a_rescues"] += int((not d_ok) and a_ok)
        d["attack_a_harms"] += int(d_ok and (not a_ok))
        d["attack_b_unique_rescues"] += int((not d_ok) and (not a_ok) and b_ok)
        d["attack_b_unique_harms"] += int(d_ok and a_ok and (not b_ok))
        d["judge_unique_rescues"] += int((not d_ok) and (not a_ok) and (not b_ok) and j_ok)
        d["judge_unique_harms"] += int(d_ok and a_ok and b_ok and (not j_ok))
        d["adjudication_rescues_vs_three"] += int((not three_ok) and final_ok)
        d["adjudication_harms_vs_three"] += int(three_ok and (not final_ok))
        raw_choices = [execution[x][tid].get("choice") for x in ("draft", "attack_a", "attack_b", "judge")]
        valid = [x for x in raw_choices if x in set(LABELS)]
        counts = sorted(Counter(valid).values(), reverse=True)
        patterns["-".join(map(str, counts)) if counts else "none"] += 1

        verifier = legacy.deterministic_verify(task)
        if verifier and verifier.get("choice") in set(LABELS):
            verifier_coverage += 1
            verifier_choice = verifier["choice"]
            verifier_disagreements += int(verifier_choice != final.get("choice"))
            hybrid[tid] = {"choice": verifier_choice, "confidence": int(verifier.get("confidence", 99)), "state": "PROVEN", "source": "DETERMINISTIC_VERIFIER"}
        else:
            hybrid[tid] = {**final, "source": "AI_REASONING_ONLY"}

    return {
        **dict(d),
        "four_way_patterns": dict(patterns),
        "verifier_coverage": verifier_coverage,
        "verifier_disagreements": verifier_disagreements,
        "hybrid": hybrid,
    }


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    preflight = selftest()
    if not preflight["pass"]:
        print(json.dumps({"preflight": preflight}, indent=2, sort_keys=True))
        raise SystemExit(2)

    tasks = generate_tasks(SEED, TASKS_PER_FAMILY)
    public_tasks = [t.public() for t in tasks]
    answer_key = {t.task_id: t.answer for t in tasks}
    taskset_hash = sha(public_tasks)
    answer_key_hash = sha(answer_key)
    semantic_hashes = [semantic_key(t) for t in tasks]
    taskset_id = f"PRIME_V4_FORENSIC_UNSEEN_{SEED}_{len(tasks)}"

    if taskset_hash in BURNED_TASKSET_HASHES:
        raise RuntimeError("TASKSET_HASH_ALREADY_BURNED")
    if len(semantic_hashes) != len(set(semantic_hashes)):
        raise RuntimeError("SEMANTIC_DUPLICATE_TASKS")

    # Inference receives PUBLIC TASKS ONLY. No answer key is passed to execute().
    execution = execute(public_tasks)

    locked = {
        "taskset_id": taskset_id,
        "taskset_hash": taskset_hash,
        "candidate_policy": v4.POLICY_VERSION,
        "candidate_source_sha256": file_sha256(Path(v4.__file__)),
        "base": execution["base"],
        "draft": execution["draft"],
        "attack_a": execution["attack_a"],
        "attack_b": execution["attack_b"],
        "judge": execution["judge"],
        "three_stage": execution["three_stage"],
        "final": execution["final"],
        "execution_order": execution["execution_order"],
    }
    locked_outputs_path = OUT / "locked_outputs.json"
    locked_outputs_path.write_text(json.dumps(locked, indent=2, sort_keys=True))
    locked_outputs_hash = file_sha256(locked_outputs_path)

    # Scoring begins only after locked outputs are durably written and hashed.
    scores = {
        "base": score(execution["base"], public_tasks, answer_key),
        "draft": score(execution["draft"], public_tasks, answer_key),
        "attack_a": score(execution["attack_a"], public_tasks, answer_key),
        "attack_b": score(execution["attack_b"], public_tasks, answer_key),
        "judge": score(execution["judge"], public_tasks, answer_key),
        "three_stage": score(execution["three_stage"], public_tasks, answer_key),
        "full_ai_reasoning": score(execution["final"], public_tasks, answer_key),
    }
    d = diagnostics(execution, public_tasks, answer_key)
    scores["hybrid_system"] = score(d["hybrid"], public_tasks, answer_key)
    pair = paired(scores["base"]["rows"], scores["full_ai_reasoning"]["rows"])

    checks = {
        "task_count_at_least_128": len(tasks) >= 128,
        "semantic_tasks_unique": len(semantic_hashes) == len(set(semantic_hashes)),
        "taskset_not_previously_burned": taskset_hash not in BURNED_TASKSET_HASHES,
        "balanced_answer_positions": Counter(answer_key.values()) == Counter({"A": 32, "B": 32, "C": 32, "D": 32}),
        "all_rows_present": all(len(execution[name]) == len(tasks) for name in ("base", "draft", "attack_a", "attack_b", "judge", "three_stage", "final")),
        "no_retries": execution["retries"] == {"base": 0, "v4": 0},
        "no_timeouts": execution["timeouts"] == {"base": 0, "v4": 0},
        "equal_call_budget": execution["calls"]["base"] == execution["calls"]["v4"] == len(tasks) * 4,
        "reasoning_lane_verifier_override_disabled": v4.REASONING_VERIFIER_OVERRIDE is False,
        "v4_strictly_better_than_base": scores["full_ai_reasoning"]["accuracy"] > scores["base"]["accuracy"],
        "paired_new_wins_exceed_base_wins": pair["new_wins"] > pair["base_wins"],
        "paired_exact_p_le_0_05": pair["exact_two_sided_p"] <= 0.05,
        "attack_a_net_positive": d["attack_a_rescues"] > d["attack_a_harms"],
        "attack_b_net_positive": d["attack_b_unique_rescues"] > d["attack_b_unique_harms"],
        "judge_not_net_harmful": d["judge_unique_rescues"] >= d["judge_unique_harms"],
        "final_not_worse_than_three_stage": scores["full_ai_reasoning"]["accuracy"] >= scores["three_stage"]["accuracy"],
        "adjudication_not_net_harmful": d["adjudication_rescues_vs_three"] >= d["adjudication_harms_vs_three"],
        "confidence_brier_improves_vs_base": scores["full_ai_reasoning"]["confidence_brier"] < scores["base"]["confidence_brier"],
        "abstain_rate_not_excessive": scores["full_ai_reasoning"]["abstain_rate"] <= 0.30,
        "attack_a_not_collapsed": d["attack_a_disagreements"] / len(tasks) >= 0.10,
    }
    qualified = all(checks.values())

    bundle = {
        "policy_version": POLICY_VERSION,
        "code_commit": os.getenv("GITHUB_SHA", "UNKNOWN"),
        "candidate_version": CANDIDATE_VERSION,
        "candidate_policy_version": v4.POLICY_VERSION,
        "candidate_source_sha256": file_sha256(Path(v4.__file__)),
        "base_version": BASE_VERSION,
        "taskset_id": taskset_id,
        "taskset_hash": taskset_hash,
        "answer_key_hash": answer_key_hash,
        "semantic_task_hashes_sha256": sha(semantic_hashes),
        "task_count": len(tasks),
        "tasks_per_family": TASKS_PER_FAMILY,
        "seed": SEED,
        "answers_not_passed_to_inference": True,
        "scoring_started_after_locked_outputs_written": True,
        "locked_outputs_file_sha256": locked_outputs_hash,
        "model_provider": execution["provider"],
        "model_id": execution["model_id"],
        "resolved_model_sha": execution["resolved_model_sha"],
        "environment": execution["environment"],
        "calls": execution["calls"],
        "tokens": execution["tokens"],
        "latency_seconds": execution["latency_seconds"],
        "parse_errors": execution["parse_errors"],
        "retries": execution["retries"],
        "timeouts": execution["timeouts"],
        "execution_order_policy": "ALTERNATE_BASE_FIRST_AND_V4_FIRST_BY_TASK_INDEX",
        "diagnostics": {k: v for k, v in d.items() if k != "hybrid"},
        "paired": pair,
        "scores": scores,
        "promotion_checks": checks,
        "qualification_verdict": "PROVEN_PASS" if qualified else "PROVEN_FAIL",
        "public_tasks": public_tasks,
        "hidden_answer_key_after_lock": answer_key,
        "traces": execution["traces"],
    }
    bundle["bundle_sha256"] = sha(bundle)
    bundle_path = OUT / "prime_v4_forensic_bundle.json"
    bundle_path.write_text(json.dumps(bundle, indent=2, sort_keys=True))

    summary = {k: v for k, v in bundle.items() if k not in {"public_tasks", "hidden_answer_key_after_lock", "traces"}}
    summary["scores"] = {name: {k: v for k, v in score_data.items() if k != "rows"} for name, score_data in scores.items()}
    summary["artifact_files"] = {
        "locked_outputs.json": file_sha256(locked_outputs_path),
        "prime_v4_forensic_bundle.json": file_sha256(bundle_path),
    }
    summary_path = OUT / "prime_v4_forensic_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True))
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args()
    if args.selftest:
        report = selftest()
        print(json.dumps(report, indent=2, sort_keys=True))
        raise SystemExit(0 if report["pass"] else 1)
    main()
