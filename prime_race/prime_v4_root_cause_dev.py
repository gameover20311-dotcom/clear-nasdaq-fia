from __future__ import annotations

import hashlib
import json
import os
import platform
import random
import re
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any

import prime_ultra_v4 as v4
import prime_v4_forensic_qualification as fq
import prime_v4_forensic_qualification_v2 as fqv2  # patches only conditional_logic generator

POLICY_VERSION = "PRIME_V4_ROOT_CAUSE_DEV_V1"
MODEL_ID = "HuggingFaceTB/SmolLM2-360M-Instruct"
MODEL_SHA = "a10cc1512eabd3dde888204e902eca88bddb4951"
DEV_SEED = 2609163107
OUT = Path(os.getenv("PRIME_V4_ROOT_CAUSE_OUT", "prime_v4_root_cause_dev_results"))
LABELS = "ABCD"


def canonical(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def sha(obj: Any) -> str:
    return hashlib.sha256(canonical(obj)).hexdigest()


def normalize(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


def parse_symbol(text: str, allowed: list[str]) -> str | None:
    raw = text.strip()
    try:
        obj = json.loads(raw)
        for key in ("choice", "label", "answer"):
            val = str(obj.get(key, "")).strip()
            if val in allowed:
                return val
    except Exception:
        pass
    pat = "|".join(re.escape(x) for x in sorted(allowed, key=len, reverse=True))
    m = re.search(rf'["\']?(?:choice|label|answer)["\']?\s*[:=]\s*["\']?({pat})\b', raw, flags=re.I)
    if m:
        val = m.group(1)
        for a in allowed:
            if val.lower() == a.lower():
                return a
    m = re.match(rf"^\s*({pat})(?=\s|[\.\),;:\-]|$)", raw, flags=re.I)
    if m:
        val = m.group(1)
        for a in allowed:
            if val.lower() == a.lower():
                return a
    return None


def parse_content(text: str, candidates: list[str]) -> str | None:
    raw = text.strip()
    value = None
    try:
        obj = json.loads(raw)
        for key in ("answer_text", "answer", "content"):
            if key in obj:
                value = str(obj[key]).strip()
                break
    except Exception:
        pass
    if value is None:
        m = re.search(r'["\']?(?:answer_text|answer|content)["\']?\s*[:=]\s*["\'](.+?)["\'](?:\s*[,}]|$)', raw, flags=re.I | re.S)
        if m:
            value = m.group(1).strip()
        else:
            value = raw
    nv = normalize(value)
    exact = [c for c in candidates if normalize(c) == nv]
    if len(exact) == 1:
        return exact[0]
    contained = [c for c in candidates if normalize(c) and normalize(c) in nv]
    if len(contained) == 1:
        return contained[0]
    return None


def task_text(task: dict[str, Any], labels: list[str] | None = None, values: list[str] | None = None) -> str:
    if labels is None:
        labels = list(task["options"].keys())
    if values is None:
        values = [task["options"][k] for k in task["options"]]
    opts = "\n".join(f"{lab}. {val}" for lab, val in zip(labels, values))
    return f"QUESTION: {task['question']}\nCONTEXT: {task['context']}\nOPTIONS:\n{opts}"


def permute_task(task: dict[str, Any], shift: int) -> tuple[list[str], list[str], str]:
    old_labels = list(task["options"].keys())
    values = [task["options"][k] for k in old_labels]
    correct_text = task["correct_text"]
    values = values[shift:] + values[:shift]
    correct_label = LABELS[values.index(correct_text)]
    return list(LABELS), values, correct_label


def consensus_two(a: str | None, b: str | None) -> str | None:
    return a if a and a == b else None


def majority_three(a: str | None, b: str | None, c: str | None) -> str | None:
    valid = [x for x in (a, b, c) if x in set(LABELS)]
    if not valid:
        return None
    counts = Counter(valid).most_common()
    if counts[0][1] >= 2 and (len(counts) == 1 or counts[0][1] > counts[1][1]):
        return counts[0][0]
    return None


def old_four(a: str | None, b: str | None, c: str | None, j: str | None) -> str | None:
    stages = [{"choice": x} for x in (a, b, c, j)]
    return v4.adjudicate_choices(stages).get("choice")


def proposed_protected_majority(a: str | None, b: str | None, c: str | None, j: str | None) -> str | None:
    three = majority_three(a, b, c)
    if three is not None:
        return three
    valid = [x for x in (a, b, c, j) if x in set(LABELS)]
    counts = Counter(valid).most_common()
    if counts and counts[0][1] >= 2 and (len(counts) == 1 or counts[0][1] > counts[1][1]):
        return counts[0][0]
    return None


def transitions(before: dict[str, str | None], after: dict[str, str | None], answers: dict[str, str]) -> dict[str, int]:
    out = Counter()
    for tid, ans in answers.items():
        b = before.get(tid)
        a = after.get(tid)
        bok = b == ans
        aok = a == ans
        if bok and aok:
            out["correct_to_correct"] += 1
        elif bok and not aok:
            out["correct_to_abstain" if a is None else "correct_to_wrong"] += 1
            out["harms"] += 1
        elif not bok and aok:
            out["abstain_to_correct" if b is None else "wrong_to_correct"] += 1
            out["rescues"] += 1
        else:
            out["wrong_to_wrong"] += 1
    out["net"] = out["rescues"] - out["harms"]
    return dict(out)


def score_choices(outputs: dict[str, str | None], answers: dict[str, str]) -> dict[str, Any]:
    n = len(answers)
    correct = sum(outputs.get(tid) == ans for tid, ans in answers.items())
    abstains = sum(outputs.get(tid) is None for tid in answers)
    return {
        "correct": correct,
        "n": n,
        "accuracy": correct / n,
        "abstains": abstains,
        "abstain_rate": abstains / n,
        "distribution": dict(Counter(outputs.get(tid) for tid in answers)),
    }


def main() -> None:
    import torch
    import transformers
    import huggingface_hub
    from transformers import AutoModelForCausalLM, AutoTokenizer

    OUT.mkdir(parents=True, exist_ok=True)
    torch.set_num_threads(max(1, min(2, os.cpu_count() or 1)))
    tokenizer = AutoTokenizer.from_pretrained(MODEL_ID, revision=MODEL_SHA)
    model = AutoModelForCausalLM.from_pretrained(MODEL_ID, revision=MODEL_SHA, torch_dtype=torch.float32)
    model.eval()

    calls = 0
    totals = {"input_tokens": 0, "output_tokens": 0, "latency_seconds": 0.0}
    raw_calls: list[dict[str, Any]] = []

    def call(system: str, user: str, tag: str) -> str:
        nonlocal calls
        start = time.perf_counter()
        prompt = tokenizer.apply_chat_template([
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ], tokenize=False, add_generation_prompt=True)
        inputs = tokenizer(prompt, return_tensors="pt")
        with torch.inference_mode():
            out = model.generate(**inputs, max_new_tokens=44, do_sample=False, pad_token_id=tokenizer.eos_token_id)
        gen = out[0, inputs["input_ids"].shape[1]:]
        text = tokenizer.decode(gen, skip_special_tokens=True).strip()
        elapsed = time.perf_counter() - start
        calls += 1
        totals["input_tokens"] += int(inputs["input_ids"].numel())
        totals["output_tokens"] += int(gen.numel())
        totals["latency_seconds"] += elapsed
        raw_calls.append({"tag": tag, "input_tokens": int(inputs["input_ids"].numel()), "output_tokens": int(gen.numel()), "latency_seconds": elapsed, "raw": text})
        return text

    # Fresh DEVELOPMENT tasks: new seed; V2 answers are not used.
    all_tasks = fqv2.base.generate_tasks(DEV_SEED, 2)
    dev = []
    for t in all_tasks:
        public = t.public()
        public["answer"] = t.answer
        public["correct_text"] = t.options[t.answer]
        dev.append(public)
    answers = {t["id"]: t["answer"] for t in dev}
    by_family_first = {}
    for t in dev:
        by_family_first.setdefault(t["category"], t)
    bind_tasks = list(by_family_first.values())

    # PHASE A: answer-selection / symbol-binding diagnostic.
    binding_rows = []
    for task in bind_tasks:
        tid = task["id"]
        correct_text = task["correct_text"]
        per_perm_contents = []
        for shift in range(4):
            labels, values, correct_label = permute_task(task, shift)
            user = task_text(task, labels, values) + '\nReturn JSON only: {"choice":"A|B|C|D"}.'
            text = call("Solve the semantic problem first, then bind the selected answer to the requested option label. Return JSON only.", user, f"binding:{tid}:abcd:{shift}")
            choice = parse_symbol(text, labels)
            chosen_text = values[labels.index(choice)] if choice in labels else None
            per_perm_contents.append(chosen_text)
            binding_rows.append({"id": tid, "condition": "ABCD_PERMUTATION", "shift": shift, "choice": choice, "chosen_text": chosen_text, "correct_text": correct_text, "correct": chosen_text == correct_text, "correct_symbol": correct_label, "raw": text})

        # Relabeled WXYZ, canonical ordering.
        values = [task["options"][k] for k in task["options"]]
        for cond, labels in (("WXYZ", list("WXYZ")), ("NUMERIC", ["1", "2", "3", "4"])):
            correct_symbol = labels[values.index(correct_text)]
            user = task_text(task, labels, values) + f'\nReturn JSON only with exactly one of {labels}: {{"choice":"..."}}.'
            text = call("Solve the semantic problem first, then bind the answer to the requested symbol. Return JSON only.", user, f"binding:{tid}:{cond}")
            choice = parse_symbol(text, labels)
            chosen_text = values[labels.index(choice)] if choice in labels else None
            binding_rows.append({"id": tid, "condition": cond, "shift": 0, "choice": choice, "chosen_text": chosen_text, "correct_text": correct_text, "correct": chosen_text == correct_text, "correct_symbol": correct_symbol, "raw": text})

        # Unlabeled content selection; deterministic external mapping afterward.
        values = [task["options"][k] for k in task["options"]]
        user = f"QUESTION: {task['question']}\nCONTEXT: {task['context']}\nCANDIDATE ANSWER TEXTS (unlabeled):\n" + "\n".join(f"- {v}" for v in values) + '\nReturn JSON only: {"answer_text":"copy one candidate answer exactly"}.'
        text = call("Solve the semantic problem without choosing an option symbol. Return the answer content itself.", user, f"binding:{tid}:CONTENT_FIRST")
        selected = parse_content(text, values)
        mapped_label = LABELS[values.index(selected)] if selected in values else None
        binding_rows.append({"id": tid, "condition": "CONTENT_FIRST_EXTERNAL_MAP", "shift": 0, "choice": mapped_label, "chosen_text": selected, "correct_text": correct_text, "correct": selected == correct_text, "raw": text})

        # Direct semantic response: no answer options. Conservative exact-content scorer.
        user = f"QUESTION: {task['question']}\nCONTEXT: {task['context']}\nReturn JSON only: {{\"answer_text\":\"your concise semantic answer\"}}."
        text = call("Solve directly. Do not use option labels because no options are provided.", user, f"binding:{tid}:DIRECT")
        selected = parse_content(text, [correct_text])
        binding_rows.append({"id": tid, "condition": "DIRECT_SEMANTIC", "shift": None, "choice": None, "chosen_text": selected, "correct_text": correct_text, "correct": selected == correct_text, "raw": text})

    binding_summary = {}
    for cond in sorted(set(r["condition"] for r in binding_rows)):
        rr = [r for r in binding_rows if r["condition"] == cond]
        binding_summary[cond] = {
            "correct": sum(r["correct"] for r in rr),
            "n": len(rr),
            "accuracy": sum(r["correct"] for r in rr) / len(rr),
            "parse_failures": sum(r["chosen_text"] is None for r in rr),
            "symbol_distribution": dict(Counter(r["choice"] for r in rr)),
        }
    perm_consistent = 0
    content_correct_label_wrong = 0
    for task in bind_tasks:
        rr = [r for r in binding_rows if r["id"] == task["id"] and r["condition"] == "ABCD_PERMUTATION"]
        chosen = [r["chosen_text"] for r in rr]
        perm_consistent += int(len(set(chosen)) == 1)
        content = next(r for r in binding_rows if r["id"] == task["id"] and r["condition"] == "CONTENT_FIRST_EXTERNAL_MAP")
        if content["correct"]:
            content_correct_label_wrong += sum(not r["correct"] for r in rr)
    binding_summary["PERMUTATION_CONSISTENCY"] = {"strict_consistent_tasks": perm_consistent, "n": len(bind_tasks), "rate": perm_consistent / len(bind_tasks)}
    binding_summary["CONTENT_CORRECT_BUT_LABEL_WRONG"] = {"count_across_abcd_permutations": content_correct_label_wrong}

    # PHASE B: matched BASE-single vs prompt-complexity ablation.
    prompts = {
        "BASE_SIMPLE": "Solve the task carefully. Return only requested JSON.",
        "VERBOSE_CONTROL": "Independent solver. Work only from the original task. Read every condition carefully, check the selected option once, and return only the requested JSON.",
        "V4_CORE": "Independent Draft solver. Work only from the original task. Solve carefully before selecting an option. Return JSON only.",
        "V4_REDERIVE": "Independent Draft solver. Work only from the original task. Re-derive quantities and logic before selecting an option. Return JSON only.",
        "V4_FULL": v4.stage_prompts()["draft"],
    }
    prompt_outputs: dict[str, dict[str, str | None]] = {k: {} for k in prompts}
    prompt_meta: dict[str, Any] = {k: {"input_tokens": 0, "output_tokens": 0, "latency_seconds": 0.0, "parse_failures": 0} for k in prompts}
    for task in dev:
        public = {k: task[k] for k in ("id", "category", "question", "context", "options")}
        user = fq.task_text(public)
        for name, system in prompts.items():
            before = len(raw_calls)
            text = call(system, user, f"complexity:{task['id']}:{name}")
            choice = fq.parse_answer(text).get("choice")
            prompt_outputs[name][task["id"]] = choice
            meta = raw_calls[before]
            prompt_meta[name]["input_tokens"] += meta["input_tokens"]
            prompt_meta[name]["output_tokens"] += meta["output_tokens"]
            prompt_meta[name]["latency_seconds"] += meta["latency_seconds"]
            prompt_meta[name]["parse_failures"] += int(choice is None)
    complexity_summary = {name: {**score_choices(out, answers), **prompt_meta[name]} for name, out in prompt_outputs.items()}

    # PHASE C: stage ablation; reuse V4_FULL as Draft and add independent A/B/Judge calls.
    stages: dict[str, dict[str, str | None]] = {
        "draft": dict(prompt_outputs["V4_FULL"]),
        "attack_a": {},
        "attack_b": {},
        "judge": {},
    }
    sp = v4.stage_prompts()
    for task in dev:
        public = {k: task[k] for k in ("id", "category", "question", "context", "options")}
        user = fq.task_text(public)
        for name in ("attack_a", "attack_b", "judge"):
            text = call(sp[name], user, f"stage:{task['id']}:{name}")
            stages[name][task["id"]] = fq.parse_answer(text).get("choice")

    policies: dict[str, dict[str, str | None]] = {
        "draft": stages["draft"],
        "attack_a": stages["attack_a"],
        "attack_b": stages["attack_b"],
        "judge": stages["judge"],
        "draft_plus_attack_a": {},
        "draft_plus_attack_b": {},
        "draft_plus_judge": {},
        "three_stage": {},
        "old_four_way_final": {},
        "protected_majority_candidate": {},
    }
    for tid in answers:
        d, a, b, j = (stages[x][tid] for x in ("draft", "attack_a", "attack_b", "judge"))
        policies["draft_plus_attack_a"][tid] = consensus_two(d, a)
        policies["draft_plus_attack_b"][tid] = consensus_two(d, b)
        policies["draft_plus_judge"][tid] = consensus_two(d, j)
        policies["three_stage"][tid] = majority_three(d, a, b)
        policies["old_four_way_final"][tid] = old_four(d, a, b, j)
        policies["protected_majority_candidate"][tid] = proposed_protected_majority(d, a, b, j)

    stage_scores = {name: score_choices(out, answers) for name, out in policies.items()}
    stage_transitions = {
        "draft_to_attack_a": transitions(stages["draft"], stages["attack_a"], answers),
        "draft_to_attack_b": transitions(stages["draft"], stages["attack_b"], answers),
        "draft_to_judge": transitions(stages["draft"], stages["judge"], answers),
        "draft_to_three_stage": transitions(stages["draft"], policies["three_stage"], answers),
        "three_to_old_final": transitions(policies["three_stage"], policies["old_four_way_final"], answers),
        "three_to_protected_majority": transitions(policies["three_stage"], policies["protected_majority_candidate"], answers),
        "old_to_protected_majority": transitions(policies["old_four_way_final"], policies["protected_majority_candidate"], answers),
    }

    adjudicator_mechanisms = Counter()
    for tid, ans in answers.items():
        d, a, b, j = (stages[x][tid] for x in ("draft", "attack_a", "attack_b", "judge"))
        three = policies["three_stage"][tid]
        old = policies["old_four_way_final"][tid]
        if three == ans and old != ans:
            vals = [x for x in (d, a, b, j) if x]
            pattern = tuple(sorted(Counter(vals).values(), reverse=True))
            if old is None and pattern == (2, 2):
                adjudicator_mechanisms["HARM_ABSTENTION_ESCALATION_2_2"] += 1
            else:
                adjudicator_mechanisms["HARM_OTHER"] += 1
        elif three != ans and old == ans:
            vals = [x for x in (d, a, b, j) if x]
            pattern = tuple(sorted(Counter(vals).values(), reverse=True))
            if pattern == (2, 1, 1):
                adjudicator_mechanisms["RESCUE_JUDGE_BREAKS_1_1_1"] += 1
            else:
                adjudicator_mechanisms["RESCUE_OTHER"] += 1

    report = {
        "policy_version": POLICY_VERSION,
        "development_only": True,
        "qualification_evidence": False,
        "v2_answers_used_for_development": False,
        "dev_seed": DEV_SEED,
        "dev_task_count": len(dev),
        "binding_semantic_task_count": len(bind_tasks),
        "model_id": MODEL_ID,
        "model_sha": MODEL_SHA,
        "candidate_policy_under_diagnosis": v4.POLICY_VERSION,
        "candidate_source_sha256": hashlib.sha256(Path(v4.__file__).read_bytes()).hexdigest(),
        "environment": {
            "python": sys.version,
            "platform": platform.platform(),
            "torch": torch.__version__,
            "transformers": transformers.__version__,
            "huggingface_hub": huggingface_hub.__version__,
        },
        "binding": binding_summary,
        "complexity": complexity_summary,
        "stage_scores": stage_scores,
        "stage_transitions": stage_transitions,
        "adjudicator_mechanisms": dict(adjudicator_mechanisms),
        "calls": calls,
        "totals": totals,
        "raw_call_hash": sha(raw_calls),
    }
    report["report_sha256"] = sha(report)
    (OUT / "root_cause_report.json").write_text(json.dumps(report, indent=2, sort_keys=True))
    (OUT / "binding_rows.json").write_text(json.dumps(binding_rows, indent=2, sort_keys=True))
    (OUT / "raw_calls.json").write_text(json.dumps(raw_calls, indent=2, sort_keys=True))
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
