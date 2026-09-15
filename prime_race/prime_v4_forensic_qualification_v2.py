from __future__ import annotations

import random

import prime_v4_forensic_qualification as base

base.POLICY_VERSION = "PRIME_V4_FORENSIC_QUALIFICATION_V2"
_original_task = base._task


def _patched_task(rng: random.Random, family: str, index: int, forced_label: str) -> base.Task:
    if family != "conditional_logic":
        return _original_task(rng, family, index, forced_label)

    p = rng.choice([True, False])
    q = rng.choice([True, False])
    r = rng.choice([True, False])
    variant = (index - 1) % 8

    if variant == 0:
        antecedent, consequent, expr = p, q, "P -> Q"
    elif variant == 1:
        antecedent, consequent, expr = q, p, "Q -> P"
    elif variant == 2:
        antecedent, consequent, expr = p and q, r, "(P AND Q) -> R"
    elif variant == 3:
        antecedent, consequent, expr = p or q, r, "(P OR Q) -> R"
    elif variant == 4:
        antecedent, consequent, expr = (not p), q, "(NOT P) -> Q"
    elif variant == 5:
        antecedent, consequent, expr = p, (not q), "P -> (NOT Q)"
    elif variant == 6:
        antecedent, consequent, expr = (p != q), r, "(P XOR Q) -> R"
    else:
        antecedent, consequent, expr = p and (not q), q or r, "(P AND NOT Q) -> (Q OR R)"

    value = (not antecedent) or consequent
    question = f"Evaluate the material implication {expr}."
    context = f"P={p}; Q={q}; R={r}."
    correct = "True" if value else "False"
    wrongs = [x for x in ["True", "False", "Cannot be evaluated", "Both true and false"] if x != correct][:3]
    options, answer = base._place_options(rng, correct, wrongs, forced_label)
    return base.Task(f"FV4-{family}-{index:03d}", family, question, context, options, answer)


base._task = _patched_task


if __name__ == "__main__":
    import argparse
    import json

    parser = argparse.ArgumentParser()
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args()
    if args.selftest:
        report = base.selftest()
        print(json.dumps(report, indent=2, sort_keys=True))
        raise SystemExit(0 if report["pass"] else 1)
    base.main()
