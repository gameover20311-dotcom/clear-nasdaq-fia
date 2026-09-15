from __future__ import annotations

from collections import Counter

import prime_real_reasoning_v3 as v3


def main() -> None:
    cases = {}
    tasks = v3.generate_tasks(424242, 2)
    cases["all_families_present"] = set(t.family for t in tasks) == set(v3.FAMILIES)
    cases["expected_task_count"] = len(tasks) == len(v3.FAMILIES) * 2
    cases["public_payload_has_no_answer_field"] = all("answer" not in t.public() for t in tasks)
    cases["four_unique_options_each"] = all(len(t.options) == 4 and len(set(t.options.values())) == 4 for t in tasks)
    labels = Counter(t.answer for t in tasks)
    cases["answer_positions_not_single_label"] = len(labels) == 4
    cases["parser_explicit"] = v3.parse_answer('{"choice":"C","confidence":71}')["choice"] == "C"
    cases["parser_prose_fail_closed"] = v3.parse_answer("A and B are discussed without a final choice.")["choice"] is None
    c1, s1 = v3.confidence_protocol("A", [{"choice":"A","confidence":50}] * 4)
    c2, s2 = v3.confidence_protocol("A", [{"choice":"A","confidence":50},{"choice":"B","confidence":50},{"choice":"C","confidence":50},{"choice":"A","confidence":50}])
    cases["confidence_protocol_nonconstant"] = c1 != c2
    cases["confidence_protocol_states_differ"] = s1 != s2
    m = v3.majority_three([{"choice":"A"},{"choice":"B"},{"choice":"C"}])
    cases["three_way_disagreement_inconclusive"] = m["choice"] is None and m["state"] == "INCONCLUSIVE"
    # The benchmark deliberately includes structures outside the legacy deterministic verifier.
    coverage = sum(v3.legacy.deterministic_verify(t.public()) is not None for t in tasks)
    cases["legacy_verifier_not_full_coverage"] = coverage < len(tasks)
    passed = sum(bool(x) for x in cases.values())
    result = {"pass": passed == len(cases), "passed": passed, "total": len(cases), "cases": cases, "answer_label_distribution": dict(labels), "legacy_verifier_coverage": coverage, "task_count": len(tasks)}
    print(result)
    if not result["pass"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
