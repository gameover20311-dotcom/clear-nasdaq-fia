#!/usr/bin/env python3
"""CLI for SIMONS SHADOW LAB V1.

This executable reads production Forward-OOS evidence and writes only under the
separate lab root supplied by the caller.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from simons_shadow_lab_v1.lab import ShadowLab, discover_threshold_grid
from simons_shadow_lab_v1.research_metrics import (
    candidate_forward_metrics,
    full_research_diagnostic,
    parameter_robustness_report,
)


def emit(value):
    print(json.dumps(value, indent=2, sort_keys=True))


def main():
    parser = argparse.ArgumentParser(description="SIMONS SHADOW LAB V1")
    parser.add_argument("--source-root", default="fia_forward_oos")
    parser.add_argument("--lab-root", default="simons_shadow_lab_data")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("audit")
    sub.add_parser("snapshot")

    d = sub.add_parser("discover")
    d.add_argument("--snapshot-id", required=True)
    d.add_argument("--min-n", type=int, default=12)

    diag = sub.add_parser("diagnostic")
    diag.add_argument("--snapshot-id", required=True)
    diag.add_argument("--horizon", type=int, choices=(4, 8), required=True)

    robust = sub.add_parser("robustness")
    robust.add_argument("--candidate-id", required=True)

    fwd = sub.add_parser("forward-metrics")
    fwd.add_argument("--candidate-id", required=True)
    fwd.add_argument("--cost-points", type=float, default=0.0)

    r = sub.add_parser("report")
    r.add_argument("--candidate-id", required=True)
    args = parser.parse_args()

    lab = ShadowLab(Path(args.source_root), Path(args.lab_root))
    if args.command == "audit":
        emit(lab.audit_source())
    elif args.command == "snapshot":
        emit(lab.create_snapshot())
    elif args.command == "discover":
        manifest, rows = lab.load_snapshot(args.snapshot_id)
        result = discover_threshold_grid(rows, min_n=args.min_n)
        result["snapshot_id"] = manifest["snapshot_id"]
        emit(result)
    elif args.command == "diagnostic":
        manifest, rows = lab.load_snapshot(args.snapshot_id)
        result = full_research_diagnostic(rows, args.horizon)
        result["snapshot_id"] = manifest["snapshot_id"]
        emit(result)
    elif args.command == "robustness":
        candidate = lab.load_candidate(args.candidate_id)
        snapshot_id = candidate["spec"]["discovery_snapshot_id"]
        _, rows = lab.load_snapshot(snapshot_id)
        emit(parameter_robustness_report(candidate, rows))
    elif args.command == "forward-metrics":
        events = lab._shadow_events(args.candidate_id)
        emit(candidate_forward_metrics(events, round_trip_cost_points=args.cost_points))
    elif args.command == "report":
        emit(lab.candidate_report(args.candidate_id))


if __name__ == "__main__":
    main()
