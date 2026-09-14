#!/usr/bin/env python3
"""Targeted hostile mutation probes for the CNMI shadow adapter.

This is not a claim of exhaustive mutation testing. It attacks the exact
fail-closed properties that previously had plausible bypasses.

A mutation is counted as *killed* only when the mutated implementation violates
the safety property that the normal regression suite asserts. In other words,
we deliberately create the bug and require the test oracle to notice it.
"""

from __future__ import annotations

import json
from pathlib import Path

from research.cnmi_shadow.test_adapter import base_candidate, valid_materiality_identity

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "research" / "cnmi_shadow" / "adapter.py"


def load_mutant(old: str, new: str):
    source = SOURCE.read_text(encoding="utf-8")
    count = source.count(old)
    if count != 1:
        raise RuntimeError(f"mutation target count for {old!r} is {count}, expected 1")
    mutated = source.replace(old, new, 1)
    ns = {"__name__": "research.cnmi_shadow._mutant"}
    exec(compile(mutated, str(SOURCE), "exec"), ns, ns)
    return ns


def main() -> int:
    probes: list[tuple[str, bool, str]] = []

    ns = load_mutant("production_ok = False", "production_ok = production_structural_ok")
    out = ns["evaluate_candidate"](base_candidate())
    probes.append((
        "external_verifier_boundary",
        out["production_admissible"] is True,
        "mutant admitted a self-attested production candidate",
    ))

    ns = load_mutant(
        'if requested_level == "PRODUCTION":',
        'if False and requested_level == "PRODUCTION":',
    )
    c = base_candidate()
    c["applicable_hard_gates"].remove("H9")
    out = ns["evaluate_candidate"](c)
    probes.append((
        "omitted_production_hard_gate",
        out["production_structurally_eligible"] is True,
        "mutant allowed omitted H9",
    ))

    ns = load_mutant(
        "if ctype not in CLAIM_TYPES:",
        "if False and ctype not in CLAIM_TYPES:",
    )
    c = base_candidate("RESEARCH")
    c["claims"] = [{"type": "NEW_MAGIC_CLAIM", "explicit_evidence_rule": {"x": True}}]
    out = ns["evaluate_candidate"](c)
    probes.append((
        "unknown_claim_type",
        out["research_admissible"] is True,
        "mutant admitted unregistered claim type",
    ))

    ns = load_mutant(
        "elif completeness not in PRODUCTION_ALLOWED_PROVENANCE_STATES:",
        "elif False and completeness not in PRODUCTION_ALLOWED_PROVENANCE_STATES:",
    )
    c = base_candidate()
    c["provenance_completeness_state"] = "HISTORICALLY_UNRECOVERABLE"
    out = ns["evaluate_candidate"](c)
    probes.append((
        "unrecoverable_provenance",
        out["production_structurally_eligible"] is True,
        "mutant allowed historically unrecoverable provenance",
    ))

    ns = load_mutant(
        "if provided.get(gate) is not True:",
        "if False and provided.get(gate) is not True:",
    )
    c = base_candidate()
    c["hard_gates"]["H1"] = False
    out = ns["evaluate_candidate"](c)
    probes.append((
        "false_hard_gate",
        out["production_structurally_eligible"] is True,
        "mutant allowed H1=false",
    ))

    ns = load_mutant(
        "if len(normalized) != len(set(normalized)):",
        "if False and len(normalized) != len(set(normalized)):",
    )
    c = base_candidate()
    c["applicable_hard_gates"].append("H1")
    out = ns["evaluate_candidate"](c)
    probes.append((
        "duplicate_applicable_gate",
        out["production_structurally_eligible"] is True,
        "mutant allowed duplicate applicable gate",
    ))

    # M7: a RESEARCH request must not silently escalate to CORE just because the
    # candidate happens to contain CORE fields.
    ns = load_mutant(
        'requested in {"CORE", "PRODUCTION"}\n        and research_ok',
        'True\n        and research_ok',
    )
    c = base_candidate("RESEARCH")
    out = ns["evaluate_candidate"](c)
    probes.append((
        "requested_level_scope",
        out["core_admissible"] is True,
        "mutant escalated RESEARCH request into CORE",
    ))

    # M8: present-but-empty materiality identity values are not a valid frozen
    # identity. Removing the empty-value check must create an unsafe pass.
    ns = load_mutant("if empty:", "if False and empty:")
    c = base_candidate()
    identity = valid_materiality_identity()
    identity["freeze_identity"] = ""
    c["claims"] = [{
        "type": "EMPIRICAL_NONINFERIORITY",
        "requires_materiality": True,
        "materiality_identity": identity,
    }]
    out = ns["evaluate_candidate"](c)
    probes.append((
        "empty_materiality_identity",
        out["production_structurally_eligible"] is True,
        "mutant accepted empty freeze identity",
    ))

    report = {
        "oracle_semantics": "killed=true iff injected bug changes behavior into the unsafe state that regression is meant to reject",
        "mutations": [
            {"name": name, "killed": killed, "unsafe_effect": effect}
            for name, killed, effect in probes
        ],
        "killed": sum(1 for _, killed, _ in probes if killed),
        "total": len(probes),
    }
    report["status"] = "PASS" if report["killed"] == report["total"] else "FAIL"
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
