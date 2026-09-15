from __future__ import annotations

from collections import Counter

import prime_ultra_v4 as v4


def main() -> None:
    cases = {}

    tasks = v4.generate_tasks(991337, 2)
    cases["all_families_present"] = set(t.family for t in tasks) == set(v4.FAMILIES)
    cases["expected_task_count"] = len(tasks) == len(v4.FAMILIES) * 2
    cases["public_payload_has_no_answer"] = all("answer" not in t.public() for t in tasks)
    cases["four_unique_options"] = all(len(t.options) == 4 and len(set(t.options.values())) == 4 for t in tasks)
    labels = Counter(t.answer for t in tasks)
    cases["answer_positions_cover_all_labels"] = set(labels) == set("ABCD")

    prompts = v4.stage_prompts()
    cases["attack_a_blind_to_draft_choice"] = "PROPOSED_DRAFT" not in prompts["attack_a"] and "draft choice" not in prompts["attack_a"].lower()
    cases["attack_b_blind_to_prior_choices"] = "DRAFT" not in prompts["attack_b"] and "ATTACK" not in prompts["attack_b"]
    cases["judge_blind_to_prior_choices"] = "LOCKED_CANDIDATES" not in prompts["judge"] and "candidate" not in prompts["judge"].lower()

    unanimous = v4.adjudicate_choices([
        {"choice": "B"}, {"choice": "B"}, {"choice": "B"}, {"choice": "B"}
    ])
    lone_judge = v4.adjudicate_choices([
        {"choice": "C"}, {"choice": "C"}, {"choice": "C"}, {"choice": "A"}
    ])
    split = v4.adjudicate_choices([
        {"choice": "A"}, {"choice": "A"}, {"choice": "B"}, {"choice": "B"}
    ])
    three_way = v4.adjudicate_choices([
        {"choice": "A"}, {"choice": "B"}, {"choice": "C"}, {"choice": None}
    ])
    cases["unanimous_consensus_kept"] = unanimous["choice"] == "B" and unanimous["state"] == "STRONGLY_SUPPORTED"
    cases["lone_judge_cannot_overwrite_three_votes"] = lone_judge["choice"] == "C"
    cases["two_two_tie_abstains"] = split["choice"] is None and split["state"] == "INCONCLUSIVE"
    cases["three_way_disagreement_abstains"] = three_way["choice"] is None

    c4 = v4.calibrated_confidence(unanimous)
    c3 = v4.calibrated_confidence(lone_judge)
    c0 = v4.calibrated_confidence(split)
    cases["confidence_monotonic_with_consensus"] = c4 > c3 > c0
    cases["confidence_conservative_cap"] = c4 <= 55
    cases["abstain_confidence_low"] = c0 <= 15

    cases["reasoning_lane_verifier_override_disabled"] = v4.REASONING_VERIFIER_OVERRIDE is False
    cases["hybrid_lane_explicitly_separate"] = v4.HYBRID_LANE_ENABLED is True

    passed = sum(bool(v) for v in cases.values())
    result = {"pass": passed == len(cases), "passed": passed, "total": len(cases), "cases": cases, "answer_label_distribution": dict(labels)}
    print(result)
    if not result["pass"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
