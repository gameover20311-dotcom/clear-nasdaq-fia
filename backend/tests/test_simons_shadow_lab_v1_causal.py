import copy
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from simons_shadow_lab_v1.causal_candidate import CausalCandidateLab, CausalCandidateSpec
from simons_shadow_lab_v1.causal_discovery import discover_causal_grid
from simons_shadow_lab_v1.causal_features import extract_lock_time_features, state_signature
from simons_shadow_lab_v1.durable_reader import verify_event_chain
from simons_shadow_lab_v1.experiment_registry import ExperimentRegistry
from simons_shadow_lab_v1.lab import _write_new_json, canonical_bytes, sha256_bytes


def row(fid="F1", locked="2026-09-10T13:00:00+00:00", outcome="BULLISH"):
    return {
        "forecast_id": fid,
        "lock_event_hash": "lockhash-" + fid,
        "locked_at_utc": locked,
        "base": {
            "direction": "BULLISH",
            "confidence": 62.0,
            "regime": "TREND",
            "status": "LIVE",
            "data_coverage": 0.9,
            "intelligence_coverage": 0.8,
            "h4": {"bullish_probability": 68.0, "bearish_probability": 32.0, "direction": "BULLISH", "confidence": 55.0, "state": "WATCH", "actionable": True},
            "h8": {"bullish_probability": 64.0, "bearish_probability": 36.0, "direction": "BULLISH", "confidence": 50.0, "state": "WATCH", "actionable": True},
            "signals": [
                {"name": "NQ structure", "score": 0.4, "freshness": "recent"},
                {"name": "DXY", "score": 0.2, "freshness": "live"},
                {"name": "US10Y", "score": -0.2, "freshness": "live"},
                {"name": "Mega-cap leadership", "score": 0.3, "freshness": "recent"},
                {"name": "Semiconductors", "score": 0.2, "freshness": "recent"},
            ],
            "source_status": {"macro": "FRED | missing", "dxy": "Yahoo | live"},
        },
        "outcomes": {"4h": {"actual_direction": outcome, "entry_price": 100.0, "outcome_price": 103.0, "resolution_event_hash": "rh"}},
    }


def make_snapshot(root: Path, sid: str, rows):
    core = {
        "schema_version": "SIMONS_SHADOW_LAB_V1",
        "snapshot_id": sid,
        "rows_sha256": sha256_bytes(canonical_bytes(rows)),
        "row_count": len(rows),
        "scientific_status": "DISCOVERY_ONLY_NOT_PROVEN",
    }
    manifest = dict(core)
    manifest["manifest_sha256"] = sha256_bytes(canonical_bytes(core))
    base = root / "snapshots" / sid
    _write_new_json(base / "manifest.json", manifest)
    _write_new_json(base / "rows.json", {"rows": rows, "rows_sha256": core["rows_sha256"]})


def event(seq, et, fid, prev, payload):
    unsigned = {"schema_version": "X", "seq": seq, "event_type": et, "forecast_id": fid, "created_at_utc": "2026-09-10T13:00:00+00:00", "prev_event_hash": prev, "payload": payload}
    return {**unsigned, "event_hash": sha256_bytes(canonical_bytes(unsigned))}


def test_lock_time_features_ignore_outcomes_completely():
    a = row(outcome="BULLISH")
    b = copy.deepcopy(a)
    b["outcomes"]["4h"]["actual_direction"] = "BEARISH"
    b["outcomes"]["4h"]["outcome_price"] = 1_000_000
    assert extract_lock_time_features(a, 4) == extract_lock_time_features(b, 4)
    assert extract_lock_time_features(a, 4)["component_alignment_is_independent_evidence"] is False


def test_state_signature_is_deterministic():
    f = extract_lock_time_features(row(), 4)
    assert state_signature(f) == state_signature(copy.deepcopy(f))


def test_causal_grid_never_auto_selects_and_small_n_is_not_proven():
    result = discover_causal_grid([row()], min_n=12)
    assert result["automatic_candidate_selection"] is False
    assert result["scientific_status"] == "DISCOVERY_ONLY_NOT_PROVEN"
    assert all(not r["eligible_min_n"] for r in result["results"])


def test_durable_chain_detects_tampering():
    first = event(1, "FORECAST_LOCK", "F1", "GENESIS", {"models": {}})
    second = event(2, "RESOLUTION_4H", "F1", first["event_hash"], {"actual_direction": "BULLISH"})
    assert verify_event_chain([first, second])["ok"] is True
    bad = copy.deepcopy(second); bad["payload"]["actual_direction"] = "BEARISH"
    audit = verify_event_chain([first, bad])
    assert audit["ok"] is False
    assert any("event_hash" in issue for issue in audit["issues"])


def test_experiment_registry_is_hash_chained(tmp_path):
    reg = ExperimentRegistry(tmp_path)
    a = reg.append("GRID", "S1", {"x": [1, 2]}, {"tests": 2})
    b = reg.append("GRID", "S1", {"x": [3]}, {"tests": 1})
    assert b["prev_event_hash"] == a["event_hash"]
    assert reg.audit()["experiments_registered"] == 2


def test_causal_candidate_freeze_lock_resolve_and_no_discovery_reuse(tmp_path):
    lab_root = tmp_path / "lab"
    source_root = tmp_path / "source"
    discovery_time = datetime(2026, 9, 10, 12, 0, tzinfo=timezone.utc)
    discovery = row("D1", "2026-09-10T11:00:00+00:00")
    make_snapshot(lab_root, "S1", [discovery])
    engine = CausalCandidateLab(source_root, lab_root)
    candidate = engine.freeze(CausalCandidateSpec(
        name="test",
        horizon_hours=4,
        conditions=[{"field": "bullish_probability", "op": "gte", "value": 60.0}],
        predicted_direction="FOLLOW_FIA",
        discovery_snapshot_id="S1",
        discovery_forecast_ids=["D1"],
        tests_run_before_selection=100,
    ), now=discovery_time)
    with pytest.raises(ValueError):
        engine.lock_from_row(candidate["candidate_id"], discovery)

    future = row("V1", "2026-09-10T13:00:00+00:00", "BULLISH")
    locked = engine.lock_from_row(candidate["candidate_id"], future, now=discovery_time + timedelta(hours=1, minutes=1))
    assert locked["payload"]["decision"] == "FIRE"
    assert locked["payload"]["outcome_information_read"] is False
    resolved = engine.resolve_from_row(candidate["candidate_id"], future, now=discovery_time + timedelta(hours=6))
    assert resolved["payload"]["correct"] is True
    report = engine.report(candidate["candidate_id"], 1.0)
    assert report["candidate_status"] == "INSUFFICIENT_SAMPLE_NOT_PROVEN"
    assert report["predictive_edge_proven"] is False
    assert report["automatic_production_promotion"] is False
