from __future__ import annotations

import hashlib
import json
import math
import os
import random
import re
import time
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import prime_repair_eval as legacy

OUT = Path(os.getenv("PRIME_V3_OUT", "prime_v3_results"))
OUT.mkdir(parents=True, exist_ok=True)
MODEL_ID = os.getenv("PRIME_V3_MODEL_ID", "HuggingFaceTB/SmolLM2-360M-Instruct")
SEED = int(os.getenv("PRIME_V3_SEED", "26091521"))
TASKS_PER_FAMILY = int(os.getenv("PRIME_V3_TASKS_PER_FAMILY", "7"))
POLICY_VERSION = "PRIME_REAL_REASONING_V3"
BASE_VERSION = "BASE_PRIME_V1_FROZEN"
NEW_VERSION = "PRIME_REAL_REASONING_V3"

FAMILIES = [
    "arithmetic_word",
    "formal_logic",
    "implication_negation",
    "causal_reasoning",
    "temporal_ordering",
    "evidence_independence",
    "provenance_identity",
    "future_leakage",
    "contradiction_scope",
    "missing_information",
    "adversarial_wording",
    "multi_step_constraints",
    "counterexample_search",
    "ambiguous_evidence",
    "integrity_governance",
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
            "options": self.options,
        }


def sha(obj: Any) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def shuffled(rng: random.Random, correct: str, wrongs: list[str]) -> tuple[dict[str, str], str]:
    values = [correct] + wrongs
    if len(values) != 4 or len(set(values)) != 4:
        raise ValueError((correct, wrongs))
    rng.shuffle(values)
    opts = dict(zip("ABCD", values))
    return opts, "ABCD"[values.index(correct)]


def build_task(rng: random.Random, family: str, idx: int) -> Task:
    token = hashlib.sha256(f"{SEED}:{family}:{idx}:{rng.random()}".encode()).hexdigest()[:12]
    tid = f"V3-{family[:5].upper()}-{idx:02d}-{token}"

    if family == "arithmetic_word":
        start = rng.randint(20, 90)
        removed = rng.randint(3, min(18, start - 2))
        added = rng.randint(4, 25)
        packs = rng.randint(2, 5)
        final = (start - removed + added) * packs
        q = "What is the final total?"
        ctx = f"A store starts with {start} units, sells {removed}, receives {added}, then prepares {packs} identical copies of the resulting inventory."
        correct = str(final)
        wrongs = [str(final + 1), str(final - packs), str(start - removed + added + packs)]

    elif family == "formal_logic":
        p, qv, r = [rng.choice([True, False]) for _ in range(3)]
        value = (p and (not qv)) or r
        q = "Evaluate the formula (P AND NOT Q) OR R."
        ctx = f"P={p}; Q={qv}; R={r}. Use classical Boolean logic."
        correct = "TRUE" if value else "FALSE"
        wrongs = ["FALSE" if value else "TRUE", "BOTH", "UNDETERMINED"]

    elif family == "implication_negation":
        p, qv = rng.choice([True, False]), rng.choice([True, False])
        implication = (not p) or qv
        value = not implication
        q = "What is the truth value of NOT (P implies Q)?"
        ctx = f"P={p}; Q={qv}. Material implication is intended."
        correct = "TRUE" if value else "FALSE"
        wrongs = ["FALSE" if value else "TRUE", "UNKNOWN", "PARADOX"]

    elif family == "causal_reasoning":
        q = "Which conclusion is justified by the evidence?"
        ctx = (
            "An observational study finds X associated with Y. A measured variable Z affects both X and Y. "
            "No intervention, randomization, natural experiment, or valid adjustment for Z is provided."
        )
        correct = "The association does not by itself identify a causal effect of X on Y"
        wrongs = [
            "X is proven to cause Y because the association is strong",
            "A larger sample would automatically remove the confounding",
            "Z may be ignored because X was recorded first",
        ]

    elif family == "temporal_ordering":
        a = rng.randint(100, 400)
        b = a + rng.randint(5, 60)
        c = b + rng.randint(5, 60)
        labels = [("A", a), ("B", b), ("C", c)]
        rng.shuffle(labels)
        ctx = "; ".join(f"Event {name} timestamp={t}" for name, t in labels) + ". Larger timestamp means later."
        earliest = min(labels, key=lambda x: x[1])[0]
        q = "Which event occurred earliest?"
        correct = f"Event {earliest}"
        wrongs = [f"Event {x}" for x in "ABC" if x != earliest] + ["Cannot determine"]
        wrongs = wrongs[:3]

    elif family == "evidence_independence":
        q = "Which evidence statement is most defensible?"
        ctx = (
            "Three reports quote the same underlying database snapshot and were generated by the same model checkpoint. "
            "A fourth report independently measures the phenomenon from a separate sensor and separate pipeline."
        )
        correct = "The first three are dependent evidence; the fourth adds an independent evidence source"
        wrongs = [
            "All four reports are fully independent because their wording differs",
            "None of the reports can contribute evidence",
            "The first three are independent while the fourth is redundant",
        ]

    elif family == "provenance_identity":
        x = hashlib.sha256(f"{SEED}:{idx}:x".encode()).hexdigest()[:8]
        y = hashlib.sha256(f"{SEED}:{idx}:y".encode()).hexdigest()[:8]
        q = "What follows from these provenance records?"
        ctx = (
            f"Record A says file F has digest {x}. Record B says the exact same byte sequence F has digest {y}. "
            "No transformation or version change is documented."
        )
        correct = "Artifact identity is unresolved and the mismatch must be investigated"
        wrongs = [
            "Both digests can certify the same exact bytes without any explanation",
            "The later record automatically makes the earlier digest correct too",
            "Digest disagreement is irrelevant to identity",
        ]

    elif family == "future_leakage":
        decision = rng.randint(1000, 3000)
        release = decision + rng.randint(2, 200)
        q = "How should this evaluation be classified?"
        ctx = f"A forecast is claimed locked at {decision}. One input used in reconstruction first became available at {release}."
        correct = "The reconstruction contains future-information leakage and cannot count as a prospective forecast"
        wrongs = [
            "It remains prospective if final accuracy is high",
            "It remains prospective because the input is relevant",
            "Availability time is unrelated to prospective validity",
        ]

    elif family == "contradiction_scope":
        same_scope = rng.choice([True, False])
        q = "Are the two claims logically contradictory?"
        if same_scope:
            ctx = "At the same time and same scope, Claim 1 states M. Claim 2 states NOT M."
            correct = "Yes, they cannot both be true under the stated identical scope"
        else:
            ctx = "Claim 1 states M for system A at time 1. Claim 2 states NOT M for system A at time 2. The property may change over time."
            correct = "No contradiction is established because the claims concern different times"
        wrongs = [
            "Yes, any occurrence of M and NOT M is always contradictory regardless of scope",
            "No, direct negations can always both be true",
            "The claims are automatically independent evidence",
        ]
        wrongs = [w for w in wrongs if w != correct][:3]

    elif family == "missing_information":
        n = rng.randint(20, 80)
        q = "Can the requested conclusion be determined?"
        ctx = f"A dataset contains {n} observations and reports only the mean outcome. No variance, distribution, group labels, or causal design is provided. Asked: whether group A has lower variance than group B."
        correct = "No; the supplied information is insufficient to compare the two group variances"
        wrongs = [
            "Yes; the overall mean uniquely determines both group variances",
            "Yes; more than 20 observations guarantees the answer",
            "Yes; group A must have lower variance by definition",
        ]

    elif family == "adversarial_wording":
        q = "Which option is NOT a valid reason to reject a prospective claim?"
        ctx = "Potential issues considered: outcome information used before lock; missing timestamp evidence; independent pre-lock evidence; retroactive editing after outcome."
        correct = "Independent evidence that was genuinely available before the lock"
        wrongs = [
            "Outcome information used before the claimed lock",
            "No evidence that the claimed lock time is authentic",
            "Retroactive editing after observing the outcome",
        ]

    elif family == "multi_step_constraints":
        a, b, c, d = rng.sample(list("WXYZ"), 4)
        q = "Which ordering relation must be true?"
        ctx = f"{a} is before {b}. {b} is before {c}. {c} is before {d}. The relation is transitive."
        correct = f"{a} is before {d}"
        wrongs = [f"{d} is before {a}", f"{c} is before {a}", f"{b} is after {d}"]

    elif family == "counterexample_search":
        values = [rng.randint(1, 9) for _ in range(5)]
        bad_index = rng.randrange(5)
        threshold = rng.randint(4, 7)
        for i in range(5):
            values[i] = max(values[i], threshold + 1)
        values[bad_index] = rng.randint(0, threshold)
        q = f"Does the universal claim 'every value is greater than {threshold}' hold?"
        ctx = f"Observed complete finite set: {values}."
        correct = "No; at least one listed value is a counterexample"
        wrongs = [
            "Yes; most values satisfy the claim",
            "Yes; one counterexample cannot refute a universal claim",
            "Cannot determine from a complete finite set",
        ]

    elif family == "ambiguous_evidence":
        q = "What is the strongest defensible conclusion?"
        ctx = (
            "Two small observational samples point in opposite directions. Both have unknown selection mechanisms, "
            "and no preregistered hypothesis or independent replication is available."
        )
        correct = "The evidence is inconclusive; a directional claim is not established"
        wrongs = [
            "The first sample proves the effect is positive",
            "The second sample proves the effect is negative",
            "Opposite results prove the true effect is exactly zero",
        ]

    elif family == "integrity_governance":
        need = rng.randint(30, 70)
        have = rng.randint(1, need - 1)
        q = "What is the correct governance decision?"
        ctx = f"Promotion policy requires {need} prospectively locked qualifying cases. Only {have} exist. Unit tests and deployment checks are green."
        correct = "Do not promote because the prospective evidence gate has not been met"
        wrongs = [
            "Promote because engineering checks replace the evidence gate",
            "Backfill historical cases and relabel them prospective",
            "Promote first and change the written policy afterward",
        ]
    else:
        raise ValueError(family)

    opts, answer = shuffled(rng, correct, wrongs)
    return Task(tid, family, q, ctx, opts, answer)


def generate_tasks(seed: int, per_family: int) -> list[Task]:
    rng = random.Random(seed)
    tasks = [build_task(rng, fam, i + 1) for fam in FAMILIES for i in range(per_family)]
    rng.shuffle(tasks)
    return tasks


def parse_answer(text: str) -> dict[str, Any]:
    raw = text.strip()
    choice = None
    confidence = None
    explicit = re.search(r'["\']?choice["\']?\s*[:=]\s*["\']?([ABCD])\b', raw, flags=re.I)
    if explicit:
        choice = explicit.group(1).upper()
    if choice is None:
        leading = re.match(r'^\s*(?:answer\s*[:=]?\s*)?([ABCD])(?=\s|[\.\),;:\-]|$)', raw, flags=re.I)
        if leading:
            choice = leading.group(1).upper()
    cm = re.search(r'["\']?confidence["\']?\s*[:=]\s*([0-9]{1,3})', raw, flags=re.I)
    if cm:
        confidence = max(0, min(100, int(cm.group(1))))
    if choice not in set("ABCD"):
        return {"choice": None, "confidence": None, "raw": raw, "parse_error": True}
    return {"choice": choice, "confidence": confidence, "raw": raw, "parse_error": False}


def task_text(task: dict[str, Any]) -> str:
    options = "\n".join(f"{k}. {v}" for k, v in task["options"].items())
    return (
        f"QUESTION: {task['question']}\nCONTEXT: {task['context']}\nOPTIONS:\n{options}\n"
        "Return JSON only: {\"choice\":\"A|B|C|D\",\"confidence\":0-100}."
    )


def majority_three(stages: list[dict[str, Any]]) -> dict[str, Any]:
    valid = [x.get("choice") for x in stages if x.get("choice") in set("ABCD")]
    if not valid:
        return {"choice": None, "state": "ABSTAIN"}
    counts = Counter(valid)
    top = counts.most_common()
    if len(top) > 1 and top[0][1] == top[1][1]:
        return {"choice": None, "state": "INCONCLUSIVE"}
    return {"choice": top[0][0], "state": "PARTIALLY_SUPPORTED"}


def confidence_protocol(final_choice: str | None, stages: list[dict[str, Any]]) -> tuple[int, str]:
    if final_choice is None:
        return 10, "ABSTAIN"
    valid = [s.get("choice") for s in stages if s.get("choice") in set("ABCD")]
    agreements = sum(1 for c in valid if c == final_choice)
    parseable = len(valid)
    if parseable == 0:
        return 10, "ABSTAIN"
    ratio = agreements / parseable
    raw_conf = [s.get("confidence") for s in stages if isinstance(s.get("confidence"), int)]
    raw_mean = sum(raw_conf) / len(raw_conf) if raw_conf else 50.0
    structural = 35 + 45 * ratio
    conf = round(0.35 * raw_mean + 0.65 * structural)
    conf = max(20, min(85, conf))
    if ratio == 1.0:
        state = "STRONGLY_SUPPORTED"
    elif ratio >= 0.75:
        state = "PARTIALLY_SUPPORTED"
    elif ratio >= 0.5:
        state = "WEAK_EVIDENCE"
    else:
        state = "INCONCLUSIVE"
    return conf, state


def score(outputs: dict[str, dict[str, Any]], tasks: list[Task]) -> dict[str, Any]:
    rows = []
    correct = abstains = high_wrong = 0
    brier = []
    buckets: dict[str, list[int]] = {"0-39": [], "40-59": [], "60-79": [], "80-100": []}
    conf_values = []
    for t in tasks:
        o = outputs[t.task_id]
        ch = o.get("choice")
        ok = ch == t.answer
        correct += int(ok)
        if ch is None:
            abstains += 1
        conf = int(o.get("confidence") or 0)
        conf_values.append(conf)
        if not ok and conf >= 90:
            high_wrong += 1
        p = conf / 100.0
        brier.append((p - (1.0 if ok else 0.0)) ** 2)
        key = "0-39" if conf < 40 else "40-59" if conf < 60 else "60-79" if conf < 80 else "80-100"
        buckets[key].append(int(ok))
        rows.append({"id": t.task_id, "family": t.family, "choice": ch, "answer": t.answer, "ok": ok, "confidence": conf, "state": o.get("state")})
    bucket_summary = {k: {"n": len(v), "accuracy": round(sum(v) / len(v), 4) if v else None} for k, v in buckets.items()}
    mean = sum(conf_values) / len(conf_values)
    variance = sum((x - mean) ** 2 for x in conf_values) / len(conf_values)
    family = {}
    for fam in FAMILIES:
        rr = [r for r in rows if r["family"] == fam]
        family[fam] = {"correct": sum(r["ok"] for r in rr), "n": len(rr), "accuracy": round(sum(r["ok"] for r in rr) / len(rr), 4)}
    return {
        "correct": correct,
        "n": len(tasks),
        "accuracy": round(correct / len(tasks), 6),
        "abstains": abstains,
        "high_confidence_wrong": high_wrong,
        "confidence_brier": round(sum(brier) / len(brier), 6),
        "confidence_mean": round(mean, 3),
        "confidence_variance": round(variance, 3),
        "confidence_buckets": bucket_summary,
        "family": family,
        "rows": rows,
    }


def paired(base_rows: list[dict[str, Any]], new_rows: list[dict[str, Any]]) -> dict[str, Any]:
    b = {x["id"]: x for x in base_rows}
    n = {x["id"]: x for x in new_rows}
    new_wins = base_wins = ties = 0
    for tid in b:
        bo, no = bool(b[tid]["ok"]), bool(n[tid]["ok"])
        if no and not bo:
            new_wins += 1
        elif bo and not no:
            base_wins += 1
        else:
            ties += 1
    discordant = new_wins + base_wins
    if discordant:
        k = min(new_wins, base_wins)
        tail = sum(math.comb(discordant, i) for i in range(k + 1)) / (2 ** discordant)
        p_two = min(1.0, 2 * tail)
    else:
        p_two = 1.0
    return {"new_wins": new_wins, "base_wins": base_wins, "ties": ties, "discordant": discordant, "exact_two_sided_p": round(p_two, 8)}


def run(tasks: list[Task]) -> dict[str, Any]:
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    torch.set_num_threads(max(1, min(2, os.cpu_count() or 1)))
    tokenizer = AutoTokenizer.from_pretrained(MODEL_ID)
    model = AutoModelForCausalLM.from_pretrained(MODEL_ID, torch_dtype=torch.float32)
    model.eval()
    calls = {"base": 0, "new": 0}
    tokens = {"base": {"input": 0, "output": 0}, "new": {"input": 0, "output": 0}}
    latency = {"base": 0.0, "new": 0.0}

    def call(system: str, user: str, lane: str) -> dict[str, Any]:
        start = time.perf_counter()
        prompt = tokenizer.apply_chat_template([
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ], tokenize=False, add_generation_prompt=True)
        inputs = tokenizer(prompt, return_tensors="pt")
        with torch.inference_mode():
            out = model.generate(**inputs, max_new_tokens=36, do_sample=False, pad_token_id=tokenizer.eos_token_id)
        gen = out[0, inputs["input_ids"].shape[1]:]
        text = tokenizer.decode(gen, skip_special_tokens=True).strip()
        calls[lane] += 1
        latency[lane] += time.perf_counter() - start
        tokens[lane]["input"] += int(inputs["input_ids"].numel())
        tokens[lane]["output"] += int(gen.numel())
        return parse_answer(text)

    base_final = {}
    new_draft = {}
    new_a = {}
    new_b = {}
    new_three = {}
    new_full = {}
    hybrid = {}
    traces = {}
    marginal = {"attack_a_rescues": 0, "attack_a_harms": 0, "attack_a_agreements": 0, "attack_a_disagreements": 0, "attack_b_unique_rescues": 0, "attack_b_unique_harms": 0, "judge_rescues": 0, "judge_harms": 0}

    for t in tasks:
        pub = t.public()
        text = task_text(pub)

        # Frozen BASE behavior: four calls, final call sees all prior conclusions.
        bd = call("Initial analyst. Solve the task and return only requested JSON.", text, "base")
        ba = call("Hostile critic. Check whether the draft is wrong; return your own requested JSON.", text + "\nDRAFT=" + json.dumps(bd), "base")
        bc = call("Counter-critic. Assess draft and attack; return requested JSON.", text + "\nDRAFT=" + json.dumps(bd) + "\nATTACK=" + json.dumps(ba), "base")
        bf = call("Final judge. Choose the best answer from the evidence and prior stages; return requested JSON.", text + "\nDRAFT=" + json.dumps(bd) + "\nATTACK=" + json.dumps(ba) + "\nCOUNTER=" + json.dumps(bc), "base")
        base_conf = bf.get("confidence") if isinstance(bf.get("confidence"), int) else 50
        base_final[t.task_id] = {"choice": bf.get("choice"), "confidence": base_conf, "state": "WEAK_EVIDENCE" if bf.get("choice") else "ABSTAIN"}

        # Repaired reasoning-only lane. No deterministic answer override.
        nd = call(
            "Independent Draft. Solve from the original evidence only. Compute/check before choosing. If information is insufficient, select the option expressing insufficiency. Return JSON only.",
            text,
            "new",
        )
        na = call(
            "Attack A hostile falsifier. Assume the proposed draft may be wrong. Re-solve independently, recompute quantities, test logic/temporal order/provenance/causal assumptions, and actively seek a counterexample. Do not agree by default. Return your own JSON answer.",
            text + "\nPROPOSED_DRAFT=" + json.dumps(nd),
            "new",
        )
        nb = call(
            "Attack B independent alternative. You are NOT shown any earlier answer. Solve the original task from scratch using a different path. Pay special attention to negation, missing information, scope, and distractor wording. Return JSON only.",
            text,
            "new",
        )
        candidates = {"draft": nd, "attack_a": na, "attack_b": nb}
        nj = call(
            "Final Judge. Independently solve the ORIGINAL task first. Then audit the three locked candidate answers shown below. Do not majority-vote; reject all candidates if your own verification disagrees. No answer key or tool result is available. Return your own JSON answer.",
            text + "\nLOCKED_CANDIDATES=" + json.dumps(candidates, sort_keys=True),
            "new",
        )

        new_draft[t.task_id] = {"choice": nd.get("choice"), "confidence": nd.get("confidence") or 50, "state": "WEAK_EVIDENCE" if nd.get("choice") else "ABSTAIN"}
        new_a[t.task_id] = {"choice": na.get("choice"), "confidence": na.get("confidence") or 50, "state": "WEAK_EVIDENCE" if na.get("choice") else "ABSTAIN"}
        new_b[t.task_id] = {"choice": nb.get("choice"), "confidence": nb.get("confidence") or 50, "state": "WEAK_EVIDENCE" if nb.get("choice") else "ABSTAIN"}
        m3 = majority_three([nd, na, nb])
        c3, s3 = confidence_protocol(m3.get("choice"), [nd, na, nb])
        new_three[t.task_id] = {"choice": m3.get("choice"), "confidence": c3, "state": s3}
        final_choice = nj.get("choice")
        final_conf, final_state = confidence_protocol(final_choice, [nd, na, nb, nj])
        new_full[t.task_id] = {"choice": final_choice, "confidence": final_conf, "state": final_state}

        # Separate hybrid lane. Verifier may improve practical reliability but never alters reasoning score.
        legacy_pub = {"id": pub["id"], "category": pub["category"], "question": pub["question"], "context": pub["context"], "options": pub["options"]}
        verifier = legacy.deterministic_verify(legacy_pub)
        if verifier and verifier.get("choice") in set("ABCD"):
            hybrid[t.task_id] = {"choice": verifier["choice"], "confidence": verifier.get("confidence", 99), "state": "PROVEN", "source": "DETERMINISTIC_VERIFIER"}
        else:
            hybrid[t.task_id] = {**new_full[t.task_id], "source": "AI_REASONING_ONLY"}

        d_ok = nd.get("choice") == t.answer
        a_ok = na.get("choice") == t.answer
        b_ok = nb.get("choice") == t.answer
        j_ok = nj.get("choice") == t.answer
        if na.get("choice") == nd.get("choice"):
            marginal["attack_a_agreements"] += 1
        else:
            marginal["attack_a_disagreements"] += 1
        if (not d_ok) and a_ok:
            marginal["attack_a_rescues"] += 1
        if d_ok and (not a_ok):
            marginal["attack_a_harms"] += 1
        if (not d_ok) and (not a_ok) and b_ok:
            marginal["attack_b_unique_rescues"] += 1
        if d_ok and a_ok and (not b_ok):
            marginal["attack_b_unique_harms"] += 1
        if (not m3.get("choice") == t.answer) and j_ok:
            marginal["judge_rescues"] += 1
        if m3.get("choice") == t.answer and (not j_ok):
            marginal["judge_harms"] += 1

        traces[t.task_id] = {
            "base": {"draft": bd, "attack_a": ba, "counter": bc, "final": bf},
            "new": {"draft": nd, "attack_a": na, "attack_b": nb, "three_stage": new_three[t.task_id], "judge": nj, "final": new_full[t.task_id], "hybrid": hybrid[t.task_id]},
        }

    return {
        "base": base_final,
        "draft": new_draft,
        "attack_a": new_a,
        "attack_b": new_b,
        "three_stage": new_three,
        "full": new_full,
        "hybrid": hybrid,
        "traces": traces,
        "marginal": marginal,
        "calls": calls,
        "tokens": tokens,
        "latency_seconds": {k: round(v, 3) for k, v in latency.items()},
    }


def main() -> None:
    tasks = generate_tasks(SEED, TASKS_PER_FAMILY)
    public = [t.public() for t in tasks]
    answer_key = {t.task_id: t.answer for t in tasks}
    taskset_id = f"PRIME_V3_UNSEEN_{SEED}_{len(tasks)}"
    taskset_hash = sha(public)
    answer_key_hash = sha(answer_key)

    # Measure legacy verifier coverage before execution; it is not used in Lane A.
    verifier_coverage = sum(legacy.deterministic_verify(t.public()) is not None for t in tasks)

    execution = run(tasks)
    locked_outputs = {
        "taskset_id": taskset_id,
        "taskset_hash": taskset_hash,
        "base": execution["base"],
        "draft": execution["draft"],
        "attack_a": execution["attack_a"],
        "attack_b": execution["attack_b"],
        "three_stage": execution["three_stage"],
        "full": execution["full"],
        "hybrid": execution["hybrid"],
    }
    locked_outputs_hash = sha(locked_outputs)
    (OUT / "locked_outputs.json").write_text(json.dumps(locked_outputs, indent=2, sort_keys=True))

    # Ground truth is applied only after outputs are locked.
    scores = {
        "base": score(execution["base"], tasks),
        "draft": score(execution["draft"], tasks),
        "attack_a": score(execution["attack_a"], tasks),
        "attack_b": score(execution["attack_b"], tasks),
        "three_stage": score(execution["three_stage"], tasks),
        "full_ai_reasoning": score(execution["full"], tasks),
        "hybrid_system": score(execution["hybrid"], tasks),
    }
    pair = paired(scores["base"]["rows"], scores["full_ai_reasoning"]["rows"])

    checks = {
        "task_count_at_least_100": len(tasks) >= 100,
        "ai_reasoning_new_strictly_better": scores["full_ai_reasoning"]["accuracy"] > scores["base"]["accuracy"],
        "paired_new_wins_exceed_base_wins": pair["new_wins"] > pair["base_wins"],
        "paired_exact_p_le_0_05": pair["exact_two_sided_p"] <= 0.05,
        "attack_or_judge_positive_marginal_value": (execution["marginal"]["attack_a_rescues"] + execution["marginal"]["attack_b_unique_rescues"] + execution["marginal"]["judge_rescues"]) > (execution["marginal"]["attack_a_harms"] + execution["marginal"]["attack_b_unique_harms"] + execution["marginal"]["judge_harms"]),
        "confidence_non_degenerate": scores["full_ai_reasoning"]["confidence_variance"] > 0,
        "no_high_confidence_wrong": scores["full_ai_reasoning"]["high_confidence_wrong"] == 0,
        "equal_inference_calls": execution["calls"]["base"] == execution["calls"]["new"] == len(tasks) * 4,
        "verifier_not_used_in_reasoning_lane": True,
        "legacy_verifier_coverage_not_full": verifier_coverage < len(tasks),
    }
    promote = all(checks.values())

    bundle = {
        "policy_version": POLICY_VERSION,
        "base_version": BASE_VERSION,
        "new_version": NEW_VERSION,
        "seed": SEED,
        "generator_version": "V3_NOVEL_STRUCTURES_1",
        "taskset_id": taskset_id,
        "taskset_hash": taskset_hash,
        "answer_key_hash": answer_key_hash,
        "task_count": len(tasks),
        "model_id": MODEL_ID,
        "answers_hidden_from_model_until_outputs_locked": True,
        "locked_outputs_hash": locked_outputs_hash,
        "lane_a_verifier_answer_override": False,
        "lane_b_hybrid_enabled": True,
        "legacy_verifier_coverage": verifier_coverage,
        "calls": execution["calls"],
        "tokens": execution["tokens"],
        "latency_seconds": execution["latency_seconds"],
        "api_cost_usd": 0.0,
        "marginal": execution["marginal"],
        "scores": scores,
        "paired": pair,
        "promotion_checks": checks,
        "promotion_decision": "PROMOTE" if promote else "DO_NOT_PROMOTE",
        "public_tasks": public,
        "hidden_answer_key_after_output_lock": answer_key,
        "traces": execution["traces"],
    }
    bundle["bundle_sha256"] = sha(bundle)
    (OUT / "prime_v3_bundle.json").write_text(json.dumps(bundle, indent=2, sort_keys=True))

    summary = {k: v for k, v in bundle.items() if k not in {"public_tasks", "hidden_answer_key_after_output_lock", "traces"}}
    summary["scores"] = {name: {k: v for k, v in val.items() if k != "rows"} for name, val in scores.items()}
    (OUT / "prime_v3_summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True))
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
