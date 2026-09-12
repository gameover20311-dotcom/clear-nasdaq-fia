#!/usr/bin/env python3
"""CLI for SIMONS SHADOW LAB V2 HYBRID.

Production Forward-OOS is read-only. All writes go under --lab-root.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

from simons_shadow_lab_v1.causal_candidate import CausalCandidateLab, CausalCandidateSpec
from simons_shadow_lab_v1.causal_discovery import discover_causal_grid, state_distribution, state_transition_candidates
from simons_shadow_lab_v1.durable_reader import DurableForwardOOSReader
from simons_shadow_lab_v1.experiment_registry import ExperimentRegistry
from simons_shadow_lab_v1.integrity import audit_lab_storage, package_manifest
from simons_shadow_lab_v1.isolation_guard import tree_seal
from simons_shadow_lab_v1.lab import ShadowLab, discover_threshold_grid
from simons_shadow_lab_v1.negative_controls import run_negative_control_harness
from simons_shadow_lab_v1.reporting import build_snapshot_report, render_html, render_markdown
from simons_shadow_lab_v1.research_metrics import candidate_forward_metrics, full_research_diagnostic, parameter_robustness_report
from simons_shadow_lab_v1.sequential_testing import AlphaSpendingPlan, SequentialAlphaLedger, alpha_schedule


def emit(value): print(json.dumps(value, indent=2, sort_keys=True))


def _row(lab: ShadowLab, snapshot_id: str, forecast_id: str):
    _, rows = lab.load_snapshot(snapshot_id)
    found = next((r for r in rows if str(r.get("forecast_id")) == str(forecast_id)), None)
    if found is None: raise KeyError("forecast_id not found in snapshot")
    return found


def _aware_dt(text: str | None):
    if not text: return None
    value = text[:-1] + "+00:00" if text.endswith("Z") else text
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None: raise ValueError("--as-of must include timezone/UTC offset")
    return dt


def _alpha_plan(path: str) -> AlphaSpendingPlan:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict): raise ValueError("alpha plan file must contain a JSON object")
    return AlphaSpendingPlan(**raw)


def main():
    parser = argparse.ArgumentParser(description="SIMONS SHADOW LAB V2 HYBRID")
    parser.add_argument("--source-root", default="fia_forward_oos")
    parser.add_argument("--lab-root", default="simons_shadow_lab_data")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("audit"); sub.add_parser("snapshot"); sub.add_parser("durable-campaigns"); sub.add_parser("experiment-audit"); sub.add_parser("final-audit"); sub.add_parser("package-manifest")
    seal = sub.add_parser("production-tree-seal"); seal.add_argument("--production-root", required=True)
    da = sub.add_parser("durable-audit"); da.add_argument("--campaign-id", required=True)
    ds = sub.add_parser("durable-snapshot"); ds.add_argument("--campaign-id", required=True); ds.add_argument("--as-of", default=None)
    d = sub.add_parser("discover"); d.add_argument("--snapshot-id", required=True); d.add_argument("--min-n", type=int, default=12)
    cd = sub.add_parser("causal-discover"); cd.add_argument("--snapshot-id", required=True); cd.add_argument("--min-n", type=int, default=12); cd.add_argument("--permutations", type=int, default=200); cd.add_argument("--seed", type=int, default=20260911); cd.add_argument("--max-tests", type=int, default=10000)
    nc = sub.add_parser("negative-control"); nc.add_argument("--snapshot-id", required=True); nc.add_argument("--trials", type=int, default=100); nc.add_argument("--min-n", type=int, default=12); nc.add_argument("--discovery-permutations", type=int, default=100); nc.add_argument("--alpha", type=float, default=0.05); nc.add_argument("--seed", type=int, default=20260911); nc.add_argument("--max-tests", type=int, default=10000)
    aps = sub.add_parser("alpha-schedule"); aps.add_argument("--plan-file", required=True)
    apf = sub.add_parser("alpha-freeze"); apf.add_argument("--plan-file", required=True)
    apl = sub.add_parser("alpha-look"); apl.add_argument("--hypothesis-id", required=True); apl.add_argument("--look-index", required=True, type=int); apl.add_argument("--p-value", required=True, type=float); apl.add_argument("--observed-n", required=True, type=int)
    sd = sub.add_parser("state-distribution"); sd.add_argument("--snapshot-id", required=True); sd.add_argument("--horizon", type=int, choices=(4, 8), required=True)
    tr = sub.add_parser("transitions"); tr.add_argument("--snapshot-id", required=True); tr.add_argument("--horizon", type=int, choices=(4, 8), required=True); tr.add_argument("--min-n", type=int, default=12)
    diag = sub.add_parser("diagnostic"); diag.add_argument("--snapshot-id", required=True); diag.add_argument("--horizon", type=int, choices=(4, 8), required=True)
    robust = sub.add_parser("robustness"); robust.add_argument("--candidate-id", required=True)
    fwd = sub.add_parser("forward-metrics"); fwd.add_argument("--candidate-id", required=True); fwd.add_argument("--cost-points", type=float, default=0.0)
    report = sub.add_parser("report"); report.add_argument("--candidate-id", required=True)
    sr = sub.add_parser("snapshot-report"); sr.add_argument("--snapshot-id", required=True); sr.add_argument("--format", choices=("json", "md", "html"), default="json")
    cf = sub.add_parser("causal-freeze"); cf.add_argument("--spec-file", required=True)
    cl = sub.add_parser("causal-lock"); cl.add_argument("--candidate-id", required=True); cl.add_argument("--snapshot-id", required=True); cl.add_argument("--forecast-id", required=True)
    cr = sub.add_parser("causal-resolve"); cr.add_argument("--candidate-id", required=True); cr.add_argument("--snapshot-id", required=True); cr.add_argument("--forecast-id", required=True)
    cp = sub.add_parser("causal-report"); cp.add_argument("--candidate-id", required=True); cp.add_argument("--cost-points", type=float, default=0.0)

    args = parser.parse_args(); source, root = Path(args.source_root), Path(args.lab_root)
    lab = ShadowLab(source, root); registry = ExperimentRegistry(root)

    if args.command == "audit": emit(lab.audit_source())
    elif args.command == "snapshot": emit(lab.create_snapshot())
    elif args.command == "production-tree-seal": emit(tree_seal(Path(args.production_root)))
    elif args.command == "durable-campaigns": emit(DurableForwardOOSReader().campaigns())
    elif args.command == "durable-audit": emit(DurableForwardOOSReader().audit(args.campaign_id))
    elif args.command == "durable-snapshot": emit(DurableForwardOOSReader().create_snapshot(args.campaign_id, root, now=_aware_dt(args.as_of)))
    elif args.command == "discover":
        manifest, rows = lab.load_snapshot(args.snapshot_id); result = discover_threshold_grid(rows, min_n=args.min_n); result["snapshot_id"] = manifest["snapshot_id"]; registry.append("PREDECLARED_THRESHOLD_GRID", args.snapshot_id, {"min_n": args.min_n}, result, search_family="BASE_THRESHOLD_GRID"); emit(result)
    elif args.command == "causal-discover":
        manifest, rows = lab.load_snapshot(args.snapshot_id)
        result = discover_causal_grid(rows, min_n=args.min_n, permutations=args.permutations, permutation_seed=args.seed, max_tests=args.max_tests)
        result["snapshot_id"] = manifest["snapshot_id"]
        event = registry.append(
            "PREDECLARED_CAUSAL_FEATURE_GRID_V2_HYBRID",
            args.snapshot_id,
            result["search_space"],
            result,
            origin="SYSTEMATIC",
            correction_method="BH+BONFERRONI+SEARCH_WIDE_PERMUTATION",
            acceptance_criteria={"bh_q_lte": 0.05, "search_wide_permutation_p_lte": 0.05, "candidate_freeze_required": True, "post_freeze_validation_required": True},
            search_family="REAL_SCHEMA_CAUSAL_GRID",
        )
        result["experiment_event_hash"] = event["event_hash"]; emit(result)
    elif args.command == "negative-control":
        manifest, rows = lab.load_snapshot(args.snapshot_id)
        result = run_negative_control_harness(rows, trials=args.trials, min_n=args.min_n, discovery_permutations=args.discovery_permutations, alpha=args.alpha, seed=args.seed, max_tests=args.max_tests)
        result["snapshot_id"] = manifest["snapshot_id"]
        event = registry.append(
            "SCRAMBLED_LABEL_NEGATIVE_CONTROL_V1",
            args.snapshot_id,
            {"trials": args.trials, "min_n": args.min_n, "discovery_permutations": args.discovery_permutations, "alpha": args.alpha, "seed": args.seed, "max_tests": args.max_tests},
            result,
            origin="SYSTEMATIC",
            correction_method="NEGATIVE_CONTROL_PIPELINE_DIAGNOSTIC",
            acceptance_criteria={"minimum_trials": 100, "wilson_95_upper_false_positive_rate_lte": args.alpha},
            search_family="NEGATIVE_CONTROL",
        )
        result["experiment_event_hash"] = event["event_hash"]; emit(result)
    elif args.command == "alpha-schedule": emit(alpha_schedule(_alpha_plan(args.plan_file)))
    elif args.command == "alpha-freeze":
        plan = _alpha_plan(args.plan_file); emit(SequentialAlphaLedger(root, plan.hypothesis_id).freeze_plan(plan))
    elif args.command == "alpha-look": emit(SequentialAlphaLedger(root, args.hypothesis_id).append_look(args.look_index, args.p_value, args.observed_n))
    elif args.command == "state-distribution": _, rows = lab.load_snapshot(args.snapshot_id); emit(state_distribution(rows, args.horizon))
    elif args.command == "transitions": _, rows = lab.load_snapshot(args.snapshot_id); emit(state_transition_candidates(rows, args.horizon, args.min_n))
    elif args.command == "diagnostic": manifest, rows = lab.load_snapshot(args.snapshot_id); result = full_research_diagnostic(rows, args.horizon); result["snapshot_id"] = manifest["snapshot_id"]; emit(result)
    elif args.command == "robustness": candidate = lab.load_candidate(args.candidate_id); _, rows = lab.load_snapshot(candidate["spec"]["discovery_snapshot_id"]); emit(parameter_robustness_report(candidate, rows))
    elif args.command == "forward-metrics": emit(candidate_forward_metrics(lab._shadow_events(args.candidate_id), round_trip_cost_points=args.cost_points))
    elif args.command == "report": emit(lab.candidate_report(args.candidate_id))
    elif args.command == "snapshot-report":
        _, rows = lab.load_snapshot(args.snapshot_id); out = build_snapshot_report(rows, args.snapshot_id)
        print(render_markdown(out) if args.format == "md" else render_html(out) if args.format == "html" else json.dumps(out, indent=2, sort_keys=True))
    elif args.command == "causal-freeze": raw = json.loads(Path(args.spec_file).read_text(encoding="utf-8")); emit(CausalCandidateLab(source, root).freeze(CausalCandidateSpec(**raw)))
    elif args.command == "causal-lock": emit(CausalCandidateLab(source, root).lock_from_row(args.candidate_id, _row(lab, args.snapshot_id, args.forecast_id)))
    elif args.command == "causal-resolve": emit(CausalCandidateLab(source, root).resolve_from_row(args.candidate_id, _row(lab, args.snapshot_id, args.forecast_id)))
    elif args.command == "causal-report": emit(CausalCandidateLab(source, root).report(args.candidate_id, args.cost_points))
    elif args.command == "experiment-audit": emit(registry.audit())
    elif args.command == "final-audit": emit(audit_lab_storage(root, source))
    elif args.command == "package-manifest": emit(package_manifest(Path(__file__).resolve().parent / "simons_shadow_lab_v1"))


if __name__ == "__main__": main()
