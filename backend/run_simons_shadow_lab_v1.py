#!/usr/bin/env python3
"""CLI for SIMONS SHADOW LAB V1.

Production Forward-OOS is read-only. All writes go under --lab-root.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from simons_shadow_lab_v1.causal_candidate import CausalCandidateLab, CausalCandidateSpec
from simons_shadow_lab_v1.causal_discovery import discover_causal_grid, state_distribution, state_transition_candidates
from simons_shadow_lab_v1.durable_reader import DurableForwardOOSReader
from simons_shadow_lab_v1.experiment_registry import ExperimentRegistry
from simons_shadow_lab_v1.lab import ShadowLab, discover_threshold_grid
from simons_shadow_lab_v1.research_metrics import candidate_forward_metrics, full_research_diagnostic, parameter_robustness_report


def emit(value):
    print(json.dumps(value, indent=2, sort_keys=True))


def _row(lab: ShadowLab, snapshot_id: str, forecast_id: str):
    _, rows = lab.load_snapshot(snapshot_id)
    row = next((r for r in rows if str(r.get("forecast_id")) == str(forecast_id)), None)
    if row is None:
        raise KeyError("forecast_id not found in snapshot")
    return row


def main():
    parser = argparse.ArgumentParser(description="SIMONS SHADOW LAB V1")
    parser.add_argument("--source-root", default="fia_forward_oos")
    parser.add_argument("--lab-root", default="simons_shadow_lab_data")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("audit")
    sub.add_parser("snapshot")
    sub.add_parser("durable-campaigns")
    da = sub.add_parser("durable-audit"); da.add_argument("--campaign-id", required=True)
    ds = sub.add_parser("durable-snapshot"); ds.add_argument("--campaign-id", required=True)

    d = sub.add_parser("discover"); d.add_argument("--snapshot-id", required=True); d.add_argument("--min-n", type=int, default=12)
    cd = sub.add_parser("causal-discover"); cd.add_argument("--snapshot-id", required=True); cd.add_argument("--min-n", type=int, default=12)
    sd = sub.add_parser("state-distribution"); sd.add_argument("--snapshot-id", required=True); sd.add_argument("--horizon", type=int, choices=(4, 8), required=True)
    tr = sub.add_parser("transitions"); tr.add_argument("--snapshot-id", required=True); tr.add_argument("--horizon", type=int, choices=(4, 8), required=True); tr.add_argument("--min-n", type=int, default=12)

    diag = sub.add_parser("diagnostic"); diag.add_argument("--snapshot-id", required=True); diag.add_argument("--horizon", type=int, choices=(4, 8), required=True)
    robust = sub.add_parser("robustness"); robust.add_argument("--candidate-id", required=True)
    fwd = sub.add_parser("forward-metrics"); fwd.add_argument("--candidate-id", required=True); fwd.add_argument("--cost-points", type=float, default=0.0)
    report = sub.add_parser("report"); report.add_argument("--candidate-id", required=True)

    cf = sub.add_parser("causal-freeze"); cf.add_argument("--spec-file", required=True)
    cl = sub.add_parser("causal-lock"); cl.add_argument("--candidate-id", required=True); cl.add_argument("--snapshot-id", required=True); cl.add_argument("--forecast-id", required=True)
    cr = sub.add_parser("causal-resolve"); cr.add_argument("--candidate-id", required=True); cr.add_argument("--snapshot-id", required=True); cr.add_argument("--forecast-id", required=True)
    cp = sub.add_parser("causal-report"); cp.add_argument("--candidate-id", required=True); cp.add_argument("--cost-points", type=float, default=0.0)
    sub.add_parser("experiment-audit")

    args = parser.parse_args()
    source, root = Path(args.source_root), Path(args.lab_root)
    lab = ShadowLab(source, root)
    registry = ExperimentRegistry(root)

    if args.command == "audit": emit(lab.audit_source())
    elif args.command == "snapshot": emit(lab.create_snapshot())
    elif args.command == "durable-campaigns": emit(DurableForwardOOSReader().campaigns())
    elif args.command == "durable-audit": emit(DurableForwardOOSReader().audit(args.campaign_id))
    elif args.command == "durable-snapshot": emit(DurableForwardOOSReader().create_snapshot(args.campaign_id, root))
    elif args.command == "discover":
        manifest, rows = lab.load_snapshot(args.snapshot_id)
        result = discover_threshold_grid(rows, min_n=args.min_n); result["snapshot_id"] = manifest["snapshot_id"]
        registry.append("PREDECLARED_THRESHOLD_GRID", args.snapshot_id, {"min_n": args.min_n}, result)
        emit(result)
    elif args.command == "causal-discover":
        manifest, rows = lab.load_snapshot(args.snapshot_id)
        result = discover_causal_grid(rows, min_n=args.min_n); result["snapshot_id"] = manifest["snapshot_id"]
        event = registry.append("PREDECLARED_CAUSAL_FEATURE_GRID_V1", args.snapshot_id, result["search_space"], result)
        result["experiment_event_hash"] = event["event_hash"]
        emit(result)
    elif args.command == "state-distribution":
        _, rows = lab.load_snapshot(args.snapshot_id); emit(state_distribution(rows, args.horizon))
    elif args.command == "transitions":
        _, rows = lab.load_snapshot(args.snapshot_id); emit(state_transition_candidates(rows, args.horizon, args.min_n))
    elif args.command == "diagnostic":
        manifest, rows = lab.load_snapshot(args.snapshot_id); result = full_research_diagnostic(rows, args.horizon); result["snapshot_id"] = manifest["snapshot_id"]; emit(result)
    elif args.command == "robustness":
        candidate = lab.load_candidate(args.candidate_id); _, rows = lab.load_snapshot(candidate["spec"]["discovery_snapshot_id"]); emit(parameter_robustness_report(candidate, rows))
    elif args.command == "forward-metrics": emit(candidate_forward_metrics(lab._shadow_events(args.candidate_id), round_trip_cost_points=args.cost_points))
    elif args.command == "report": emit(lab.candidate_report(args.candidate_id))
    elif args.command == "causal-freeze":
        raw = json.loads(Path(args.spec_file).read_text(encoding="utf-8")); emit(CausalCandidateLab(source, root).freeze(CausalCandidateSpec(**raw)))
    elif args.command == "causal-lock": emit(CausalCandidateLab(source, root).lock_from_row(args.candidate_id, _row(lab, args.snapshot_id, args.forecast_id)))
    elif args.command == "causal-resolve": emit(CausalCandidateLab(source, root).resolve_from_row(args.candidate_id, _row(lab, args.snapshot_id, args.forecast_id)))
    elif args.command == "causal-report": emit(CausalCandidateLab(source, root).report(args.candidate_id, args.cost_points))
    elif args.command == "experiment-audit": emit(registry.audit())


if __name__ == "__main__":
    main()
