from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

import requests
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

MANUAL_BASE = os.getenv("MANUAL_CHALLENGE_BASE", "https://prime-zero-budget-manual-20260915.onrender.com").rstrip("/")
MODEL_ID = os.getenv("BATTLE_MODEL_ID", "HuggingFaceTB/SmolLM2-360M-Instruct")
OUT = Path(os.getenv("BATTLE_OUT", "battle_results"))
OUT.mkdir(parents=True, exist_ok=True)


def fetch_json(url: str) -> dict[str, Any]:
    r = requests.get(url, timeout=60)
    r.raise_for_status()
    return r.json()


def post_json(url: str, payload: dict[str, Any]) -> dict[str, Any]:
    r = requests.post(url, json=payload, timeout=60)
    if r.status_code >= 400:
        raise RuntimeError(f"POST_FAILED:{r.status_code}:{r.text[:1000]}")
    return r.json()


def task_text(task: dict[str, Any]) -> str:
    options = "\n".join(f"{k}. {v}" for k, v in task["options"].items())
    return (
        f"TASK {task['id']}\nCATEGORY: {task['category']}\nQUESTION:\n{task['question']}\n\n"
        f"EVIDENCE/CONTEXT:\n{task['context']}\n\nOPTIONS:\n{options}\n\n"
        "Choose exactly one option. Return JSON only: {\"choice\":\"A|B|C|D\",\"confidence\":0-100}."
    )


def parse_answer(text: str) -> dict[str, Any]:
    choice = None
    confidence = 50
    m = re.search(r'["\']?choice["\']?\s*[:=]\s*["\']?([ABCD])\b', text, flags=re.I)
    if m:
        choice = m.group(1).upper()
    if choice is None:
        candidates = re.findall(r'(?<![A-Z])([ABCD])(?![A-Z])', text.upper())
        if candidates:
            choice = candidates[-1]
    cm = re.search(r'["\']?confidence["\']?\s*[:=]\s*([0-9]{1,3})', text, flags=re.I)
    if cm:
        confidence = max(0, min(100, int(cm.group(1))))
    if choice not in {"A", "B", "C", "D"}:
        raise RuntimeError(f"UNPARSEABLE_MODEL_OUTPUT:{text[:500]}")
    return {"choice": choice, "confidence": confidence, "raw": text}


def main() -> None:
    root = fetch_json(MANUAL_BASE + "/")
    challenge = fetch_json(MANUAL_BASE + "/challenge")
    if root.get("status") != "READY":
        raise RuntimeError(f"MANUAL_NOT_READY:{root}")
    if challenge.get("challenge_id") != root.get("challenge_id"):
        raise RuntimeError("CHALLENGE_ID_CHANGED_DURING_FETCH")
    if challenge.get("answers_exposed") is not False:
        raise RuntimeError("ANSWER_KEY_EXPOSURE_FLAG_NOT_FALSE")
    tasks = challenge.get("tasks", [])
    if len(tasks) != 8 or any("answer" in t for t in tasks):
        raise RuntimeError("PUBLIC_TASK_CONTRACT_FAILED")

    torch.set_num_threads(max(1, min(2, os.cpu_count() or 1)))
    tokenizer = AutoTokenizer.from_pretrained(MODEL_ID)
    model = AutoModelForCausalLM.from_pretrained(MODEL_ID, torch_dtype=torch.float32)
    model.eval()

    call_counter = {"plain_4x": 0, "prime_4x": 0}

    def call(system: str, user: str, lane: str) -> dict[str, Any]:
        messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        prompt = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        inputs = tokenizer(prompt, return_tensors="pt")
        with torch.inference_mode():
            output = model.generate(
                **inputs,
                max_new_tokens=80,
                do_sample=False,
                pad_token_id=tokenizer.eos_token_id,
            )
        generated = output[0, inputs["input_ids"].shape[1]:]
        text = tokenizer.decode(generated, skip_special_tokens=True).strip()
        call_counter[lane] += 1
        return parse_answer(text)

    plain: dict[str, dict[str, Any]] = {}
    prime: dict[str, dict[str, Any]] = {}
    traces: dict[str, Any] = {}

    for task in tasks:
        base = task_text(task)
        neutral = (
            "Blind benchmark. Use only supplied evidence. Do not assume missing facts. "
            "Reason neutrally and choose exactly one supplied option."
        )
        p1 = call(neutral + " PASS 1/4.", base, "plain_4x")
        p2 = call(neutral + " PASS 2/4. Re-evaluate independently.", base, "plain_4x")
        p3 = call(neutral + " PASS 3/4. Re-evaluate independently.", base, "plain_4x")
        pf = call(
            neutral + " PASS 4/4. Synthesize the three prior attempts and choose the best-supported answer.",
            base + "\n\nATTEMPT_1=" + json.dumps(p1) + "\nATTEMPT_2=" + json.dumps(p2) + "\nATTEMPT_3=" + json.dumps(p3),
            "plain_4x",
        )

        policy = (
            "ULTRA MODE: evidence over confidence; falsification over confirmation; no fake PASS; "
            "separate fact from assumption; attack the current answer before accepting it. "
            "Repeated calls to the same model/provider are not independent evidence."
        )
        draft = call(policy + " ROLE: initial analyst.", base, "prime_4x")
        attack = call(
            policy + " ROLE: hostile attacker. Try to prove the draft wrong. Prefer the strongest alternative if warranted.",
            base + "\n\nDRAFT=" + json.dumps(draft),
            "prime_4x",
        )
        counter = call(
            policy + " ROLE: counter-attacker. Try to prove the attack wrong and identify what survives both sides.",
            base + "\n\nDRAFT=" + json.dumps(draft) + "\nATTACK=" + json.dumps(attack),
            "prime_4x",
        )
        final = call(
            policy + " ROLE: final judge. Choose the weakest defensible answer supported by the supplied evidence.",
            base + "\n\nDRAFT=" + json.dumps(draft) + "\nATTACK=" + json.dumps(attack) + "\nCOUNTER=" + json.dumps(counter),
            "prime_4x",
        )

        plain[task["id"]] = {"choice": pf["choice"], "confidence": pf["confidence"]}
        prime[task["id"]] = {"choice": final["choice"], "confidence": final["confidence"]}
        traces[task["id"]] = {
            "plain": {"pass1": p1, "pass2": p2, "pass3": p3, "final": pf},
            "prime": {"draft": draft, "attack": attack, "counter": counter, "final": final},
        }

    expected_calls = len(tasks) * 4
    if call_counter != {"plain_4x": expected_calls, "prime_4x": expected_calls}:
        raise RuntimeError(f"CALL_BUDGET_MISMATCH:{call_counter}:expected={expected_calls}")

    submission = {
        "challenge_id": challenge["challenge_id"],
        "prime": prime,
        "challenger": plain,
        "metadata": {
            "prime_label": f"PRIME_4X_ON_{MODEL_ID}",
            "challenger_label": f"PLAIN_MATCHED_4X_ON_{MODEL_ID}",
            "same_call_budget_attested": True,
        },
    }
    receipt = post_json(MANUAL_BASE + "/score", submission)

    bundle = {
        "battle_type": "DEVELOPMENT_SAME_MODEL_ARCHITECTURE_TEST",
        "model_id": MODEL_ID,
        "challenge_id": challenge["challenge_id"],
        "source_public_task_sha256": challenge.get("source_public_task_sha256"),
        "task_count": len(tasks),
        "answer_key_seen_by_model": False,
        "same_model_lineage": True,
        "evidence_independence": "DEPENDENCE_NOT_EXCLUDABLE",
        "prime_calls": call_counter["prime_4x"],
        "challenger_calls": call_counter["plain_4x"],
        "submission": submission,
        "receipt": receipt,
        "traces": traces,
        "claims_not_allowed": challenge.get("claims_not_allowed", []),
    }
    (OUT / "battle_bundle.json").write_text(json.dumps(bundle, indent=2, sort_keys=True))
    (OUT / "receipt.json").write_text(json.dumps(receipt, indent=2, sort_keys=True))
    print(json.dumps({
        "model_id": MODEL_ID,
        "challenge_id": challenge["challenge_id"],
        "prime_calls": call_counter["prime_4x"],
        "challenger_calls": call_counter["plain_4x"],
        "receipt": receipt,
        "evidence_independence": "DEPENDENCE_NOT_EXCLUDABLE",
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
