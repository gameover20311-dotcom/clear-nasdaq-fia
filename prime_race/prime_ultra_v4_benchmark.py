from __future__ import annotations

import hashlib
import json
import math
import os
import re
import time
from collections import Counter
from pathlib import Path
from typing import Any

import prime_repair_eval as legacy
import prime_ultra_v4 as v4

OUT = Path(os.getenv("PRIME_V4_OUT", "prime_v4_results"))
OUT.mkdir(parents=True, exist_ok=True)
MODEL_ID = os.getenv("PRIME_V4_MODEL_ID", "HuggingFaceTB/SmolLM2-360M-Instruct")
SEED = int(os.getenv("PRIME_V4_SEED", "2609152241"))
TASKS_PER_FAMILY = int(os.getenv("PRIME_V4_TASKS_PER_FAMILY", "8"))
BASE_VERSION = "BASE_PRIME_V1_FROZEN"
NEW_VERSION = "PRIME_ULTRA_V4"
BURNED_V3_TASKSET_HASH = "57f804594569815880f387883d92d0bd0b43f9ce46316e4b3babba55ba5bba07"


def sha(obj: Any) -> str:
    payload = json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return hashlib.sha256(payload).hexdigest()


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
    if choice not in set("ABCD"):
        return {"choice": None, "confidence": confidence, "raw": raw, "parse_error": True}
    return {"choice": choice, "confidence": confidence, "raw": raw, "parse_error": False}


def task_text(task: dict[str, Any]) -> str:
    options = "\n".join(f"{k}. {v}" for k, v in task["options"].items())
    return (
        f"QUESTION: {task['question']}\nCONTEXT: {task['context']}\nOPTIONS:\n{options}\n"
        "Return JSON only: {\"choice\":\"A|B|C|D\",\"confidence\":0-100}."
    )


def majority_three(stages: list[dict[str, Any]]) -> dict[str, Any]:
    valid = [s.get("choice") for s in stages if s.get("choice") in set("ABCD")]
    if not valid:
        return {"choice": None, "state": "ABSTAIN"}
    counts = Counter(valid)
    ranked = counts.most_common()
    choice, support = ranked[0]
    second = ranked[1][1] if len(ranked) > 1 else 0
    if support >= 2 and support > second:
        return {"choice": choice, "state": "PARTIALLY_SUPPORTED" if support == 2 else "STRONGLY_SUPPORTED"}
    return {"choice": None, "state": "INCONCLUSIVE"}


def score(outputs: dict[str, dict[str, Any]], tasks: list[v4.Task]) -> dict[str, Any]:
    rows = []
    correct = 0
    abstains = 0
    brier = []
    confs = []
    state_counts: Counter[str] = Counter()
    for task in tasks:
        out = outputs[task.task_id]
        choice = out.get("choice")
        ok = choice == task.answer
        correct += int(ok)
        abstains += int(choice is None)
        confidence = int(out.get("confidence") or 0)
        confs.append(confidence)
        p = confidence / 100.0
        brier.append((p - (1.0 if ok else 0.0)) ** 2)
        state = str(out.get("state") or "UNKNOWN")
        state_counts[state] += 1
        rows.append({
            "id": task.task_id,
            "family": task.family,
            "choice": choice,
            "answer": task.answer,
            "ok": ok,
            "confidence": confidence,
            "state": state,
        })
    mean = sum(confs) / len(confs)
    variance = sum((x - mean) ** 2 for x in confs) / len(confs)
    families = {}
    for family in v4.FAMILIES:
        rr = [r for r in rows if r["family"] == family]
        families[family] = {
            "correct": sum(int(r["ok"]) for r in rr),
            "n": len(rr),
            "accuracy": round(sum(int(r["ok"]) for r in rr) / len(rr), 4),
        }
    return {
        "correct": correct,
        "n": len(tasks),
        "accuracy": round(correct / len(tasks), 6),
        "abstains": abstains,
        "abstain_rate": round(abstains / len(tasks), 6),
        "confidence_brier": round(sum(brier) / len(brier), 6),
        "confidence_mean": round(mean, 3),
        "confidence_variance": round(variance, 3),
        "state_counts": dict(state_counts),
        "family": families,
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
    return {
        "new_wins": new_wins,
        "base_wins": base_wins,
        "ties": ties,
        "discordant": discordant,
        "exact_two_sided_p": round(p, 8),
    }


def run(tasks: list[v4.Task]) -> dict[str, Any]:
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    torch.set_num_threads(max(1, min(2, os.cpu_count() or 1)))
    tokenizer = AutoTokenizer.from_pretrained(MODEL_ID)
    model = AutoModelForCausalLM.from_pretrained(MODEL_ID, torch_dtype=torch.float32)
    model.eval()

    calls = {"base": 0, "v4": 0}
    tokens = {"base": {"input": 0, "output": 0}, "v4": {"input": 0, "output": 0}}
    latency = {"base": 0.0, "v4": 0.0}

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
        calls[lane] += 1
        latency[lane] += time.perf_counter() - start
        tokens[lane]["input"] += int(inputs["input_ids"].numel())
        tokens[lane]["output"] += int(gen.numel())
        return parse_answer(text)

    prompts = v4.stage_prompts()
    base_final: dict[str, dict[str, Any]] = {}
    stage_out = {"draft": {}, "attack_a": {}, "attack_b": {}, "judge": {}, "three_stage": {}, "final": {}, "hybrid": {}}
    traces = {}
    diagnostics = {
        "attack_a_agreements": 0,
        "attack_a_disagreements": 0,
        "attack_a_rescues": 0,
        "attack_a_harms": 0,
        "attack_b_unique_rescues": 0,
        "attack_b_unique_harms": 0,
        "judge_unique_rescues": 0,
        "judge_unique_harms": 0,
        "adjudication_rescues_vs_three": 0,
        "adjudication_harms_vs_three": 0,
        "four_way_patterns": Counter(),
    }

    for task in tasks:
        public = task.public()
        text = task_text(public)

        # Frozen BASE behavior from V3.
        bd = call("Initial analyst. Solve the task and return only requested JSON.", text, "base")
        ba = call("Hostile critic. Check whether the draft is wrong; return your own requested JSON.", text + "\nDRAFT=" + json.dumps(bd), "base")
        bc = call("Counter-critic. Assess draft and attack; return requested JSON.", text + "\nDRAFT=" + json.dumps(bd) + "\nATTACK=" + json.dumps(ba), "base")
        bf = call("Final judge. Choose the best answer from the evidence and prior stages; return requested JSON.", text + "\nDRAFT=" + json.dumps(bd) + "\nATTACK=" + json.dumps(ba) + "\nCOUNTER=" + json.dumps(bc), "base")
        base_final[task.task_id] = {
            "choice": bf.get("choice"),
            "confidence": bf.get("confidence") if isinstance(bf.get("confidence"), int) else 50,
            "state": "WEAK_EVIDENCE" if bf.get("choice") else "ABSTAIN",
        }

        # V4: all four roles see only the original task.
        vd = call(prompts["draft"], text, "v4")
        va = call(prompts["attack_a"], text, "v4")
        vb = call(prompts["attack_b"], text, "v4")
        vj = call(prompts["judge"], text, "v4")

        for name, raw in (("draft", vd), ("attack_a", va), ("attack_b", vb), ("judge", vj)):
            stage_out[name][task.task_id] = {
                "choice": raw.get("choice"),
                "confidence": 20 if raw.get("choice") else 8,
                "state": "WEAK_EVIDENCE" if raw.get("choice") else "ABSTAIN",
            }

        three = majority_three([vd, va, vb])
        stage_out["three_stage"][task.task_id] = {
            "choice": three.get("choice"),
            "confidence": 20 if three.get("choice") else 8,
            "state": three.get("state"),
        }

        adjudicated = v4.adjudicate_choices([vd, va, vb, vj])
        final = {
            "choice": adjudicated.get("choice"),
            "confidence": v4.calibrated_confidence(adjudicated),
            "state": adjudicated.get("state"),
            "support": adjudicated.get("support"),
        }
        stage_out["final"][task.task_id] = final

        verifier = legacy.deterministic_verify(public)
        if verifier and verifier.get("choice") in set("ABCD"):
            stage_out["hybrid"][task.task_id] = {
                "choice": verifier["choice"],
                "confidence": verifier.get("confidence", 99),
                "state": "PROVEN",
                "source": "DETERMINISTIC_VERIFIER",
            }
        else:
            stage_out["hybrid"][task.task_id] = {**final, "source": "AI_REASONING_ONLY"}

        d_ok = vd.get("choice") == task.answer
        a_ok = va.get("choice") == task.answer
        b_ok = vb.get("choice") == task.answer
        j_ok = vj.get("choice") == task.answer
        three_ok = three.get("choice") == task.answer
        final_ok = final.get("choice") == task.answer

        diagnostics["attack_a_agreements"] += int(va.get("choice") == vd.get("choice"))
        diagnostics["attack_a_disagreements"] += int(va.get("choice") != vd.get("choice"))
        diagnostics["attack_a_rescues"] += int((not d_ok) and a_ok)
        diagnostics["attack_a_harms"] += int(d_ok and (not a_ok))
        diagnostics["attack_b_unique_rescues"] += int((not d_ok) and (not a_ok) and b_ok)
        diagnostics["attack_b_unique_harms"] += int(d_ok and a_ok and (not b_ok))
        diagnostics["judge_unique_rescues"] += int((not d_ok) and (not a_ok) and (not b_ok) and j_ok)
        diagnostics["judge_unique_harms"] += int(d_ok and a_ok and b_ok and (not j_ok))
        diagnostics["adjudication_rescues_vs_three"] += int((not three_ok) and final_ok)
        diagnostics["adjudication_harms_vs_three"] += int(three_ok and (not final_ok))

        choices = [x.get("choice") for x in (vd, va, vb, vj) if x.get("choice") in set("ABCD")]
        counts = sorted(Counter(choices).values(), reverse=True)
        diagnostics["four_way_patterns"]["-".join(map(str, counts)) if counts else "none"] += 1

        traces[task.task_id] = {
            "base": {"draft": bd, "attack_a": ba, "counter": bc, "final": bf},
            "v4": {"draft": vd, "attack_a": va, "attack_b": vb, "judge": vj, "three_stage": stage_out["three_stage"][task.task_id], "final": final},
        }

    diagnostics["four_way_patterns"] = dict(diagnostics["four_way_patterns"])
    return {
        "base": base_final,
        **stage_out,
        "traces": traces,
        "diagnostics": diagnostics,
        "calls": calls,
        "tokens": tokens,
        "latency_seconds": {k: round(v, 3) for k, v in latency.items()},
    }


def main() -> None:
    tasks = v4.generate_tasks(SEED, TASKS_PER_FAMILY)
    public_tasks = [t.public() for t in tasks]
    answer_key = {t.task_id: t.answer for t in tasks}
    taskset_id = f"PRIME_ULTRA_V4_UNSEEN_{SEED}_{len(tasks)}"
    taskset_hash = sha(public_tasks)
    answer_key_hash = sha(answer_key)

    execution = run(tasks)
    locked = {
        "taskset_id": taskset_id,
        "taskset_hash": taskset_hash,
        "base": execution["base"],
        "draft": execution["draft"],
        "attack_a": execution["attack_a"],
        "attack_b": execution["attack_b"],
        "judge": execution["judge"],
        "three_stage": execution["three_stage"],
        "final": execution["final"],
        "hybrid": execution["hybrid"],
    }
    locked_outputs_hash = sha(locked)
    (OUT / "locked_outputs.json").write_text(json.dumps(locked, indent=2, sort_keys=True))

    scores = {
        "base": score(execution["base"], tasks),
        "draft": score(execution["draft"], tasks),
        "attack_a": score(execution["attack_a"], tasks),
        "attack_b": score(execution["attack_b"], tasks),
        "judge": score(execution["judge"], tasks),
        "three_stage": score(execution["three_stage"], tasks),
        "full_ai_reasoning": score(execution["final"], tasks),
        "hybrid_system": score(execution["hybrid"], tasks),
    }
    pair = paired(scores["base"]["rows"], scores["full_ai_reasoning"]["rows"])
    d = execution["diagnostics"]
    verifier_coverage = sum(1 for x in execution["hybrid"].values() if x.get("source") == "DETERMINISTIC_VERIFIER")

    checks = {
        "task_count_at_least_128": len(tasks) >= 128,
        "fresh_taskset_not_burned_v3": taskset_hash != BURNED_V3_TASKSET_HASH,
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
        "equal_call_budget": execution["calls"]["base"] == execution["calls"]["v4"] == len(tasks) * 4,
        "reasoning_lane_verifier_override_disabled": v4.REASONING_VERIFIER_OVERRIDE is False,
    }
    promote = all(checks.values())

    bundle = {
        "policy_version": v4.POLICY_VERSION,
        "base_version": BASE_VERSION,
        "new_version": NEW_VERSION,
        "model_id": MODEL_ID,
        "seed": SEED,
        "tasks_per_family": TASKS_PER_FAMILY,
        "task_count": len(tasks),
        "taskset_id": taskset_id,
        "taskset_hash": taskset_hash,
        "answer_key_hash": answer_key_hash,
        "burned_v3_taskset_hash": BURNED_V3_TASKSET_HASH,
        "answers_hidden_until_outputs_locked": True,
        "locked_outputs_hash": locked_outputs_hash,
        "reasoning_verifier_override": v4.REASONING_VERIFIER_OVERRIDE,
        "hybrid_lane_enabled": v4.HYBRID_LANE_ENABLED,
        "hybrid_verifier_coverage": verifier_coverage,
        "calls": execution["calls"],
        "tokens": execution["tokens"],
        "latency_seconds": execution["latency_seconds"],
        "api_cost_usd": 0.0,
        "diagnostics": execution["diagnostics"],
        "paired": pair,
        "scores": scores,
        "promotion_checks": checks,
        "promotion_decision": "PROMOTE" if promote else "DO_NOT_PROMOTE",
        "public_tasks": public_tasks,
        "hidden_answer_key_after_output_lock": answer_key,
        "traces": execution["traces"],
    }
    bundle["bundle_sha256"] = sha(bundle)
    (OUT / "prime_ultra_v4_bundle.json").write_text(json.dumps(bundle, indent=2, sort_keys=True))

    summary = {k: v for k, v in bundle.items() if k not in {"public_tasks", "hidden_answer_key_after_output_lock", "traces"}}
    summary["scores"] = {name: {k: v for k, v in data.items() if k != "rows"} for name, data in scores.items()}
    (OUT / "prime_ultra_v4_summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True))
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
