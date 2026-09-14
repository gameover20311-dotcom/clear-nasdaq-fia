#!/usr/bin/env python3
"""Targeted hostile mutation probes for the CNMI shadow adapter.

This is not a claim of exhaustive mutation testing. It attacks the exact
fail-closed properties that previously had plausible bypasses.
"""

from __future__ import annotations

import json
from pathlib import Path

from research.cnmi_shadow.test_adapter import base_candidate

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
    probes = []

    # M1: self-attested structural eligibility must never become admission.
    ns = load_mutant("production_ok = False", "production_ok = production_structural_ok")
    out = ns["evaluate_candidate"](base_candidate())
    probes.append(("external_verifier_boundary", out["production_admissible"] is False))

    # M2: production cannot omit a hard gate from the caller-declared applicable set.
    ns = load_mutant(
        'if requested_level == "PRODUCTION":',
        'if False and requested_level == "PRODUCTION":',
    )
    c = base_candidate()
    c["applicable_hard_gates"].remove("H9")
    out = ns["evaluate_candidate"](c)
    probes.append(("omitted_production_hard_gate", out["production_structurally_eligible"] is False))

    # M3: unknown claim type cannot authorize itself with a local evidence rule.
    ns = load_mutant(
        "if ctype not in CLAIM_TYPES:",
        "if False and ctype not in CLAIM_TYPES:",
    )
    c = base_candidate("RESEARCH")
    c["claims"] = [{"type": "NEW_MAGIC_CLAIM", "explicit_evidence_rule": {"x": True}}]
    out = ns["evaluate_candidate"](c)
    probes.append(("unknown_claim_type", out["research_admissible"] is False))

    # M4: incomplete/unrecoverable provenance must not be structurally production eligible.
    ns = load_mutant(
        "elif completeness not in PRODUCTION_ALLOWED_PROVENANCE_STATES:",
        "elif False and completeness not in PRODUCTION_ALLOWED_PROVENANCE_STATES:",
    )
    c = base_candidate()
    c["provenance_completeness_state"] = "HISTORICALLY_UNRECOVERABLE"
    out = ns["evaluate_candidate"](c)
    probes.append(("unrecoverable_provenance", out["production_structurally_eligible"] is False))

    # M5: a false hard gate must remain non-compensable.
    ns = load_mutant(
        "if provided.get(gate) is not True:",
        "if False and provided.get(gate) is not True:",
    )
    c = base_candidate()
    c["hard_gates"]["H1"] = False
    out = ns["evaluate_candidate"](c)
    probes.append(("false_hard_gate", out["production_structurally_eligible"] is False))

    # M6: duplicate applicability declarations are rejected instead of normalized away.
    ns = load_mutant(
        "if len(normalized) != len(set(normalized)):",
        "if False and len(normalized) != len(set(normalized)):",
    )
    c = base_candidate()
    c["applicable_hard_gates"].append("H1")
    out = ns["evaluate_candidate"](c)
    probes.append(("duplicate_applicable_gate", out["production_structurally_eligible"] is False))

    report = {
        "mutations": [{"name": name, "killed": killed} for name, killed in probes],
        "killed": sum(1 for _, killed in probes if killed),
        "total": len(probes),
    }
    report["status"] = "PASS" if report["killed"] == report["total"] else "FAIL"
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
