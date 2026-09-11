#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import json
import os
import stat
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from fia.forward_oos import (
    DEFAULT_ROOT,
    MODEL_NAME,
    _append_event,
    _completed_close_from_polygon_payload,
    _write_evidence_once,
    checkpoint_state,
    forward_report,
    lock_live_forecast,
    promotion_gate,
    records,
    resolve_due_forecasts,
    sha256_file,
    verify_ledger,
    verify_campaign_seal,
)

PASS = 0


def check(name, cond):
    global PASS
    if not cond:
        raise AssertionError(name)
    PASS += 1
    print("PASS", name)


def fc(ts, direction="BULLISH", bull=65.0, conf=70.0, regime="TREND"):
    return {
        "symbol": "NQ",
        "horizon_hours": 8,
        "direction": direction,
        "bullish_probability": bull,
        "bearish_probability": 100.0 - bull,
        "confidence": conf,
        "regime": regime,
        "status": "LIVE",
        "score": 0.2 if direction == "BULLISH" else -0.2,
        "signals": [{"name": "News", "score": .2, "weight": .07, "freshness": "live"}],
        "invalidation": [],
        "generated_at": ts.isoformat(),
        "data_coverage": .9,
        "intelligence_coverage": .7,
        "source_status": {"news": "live"},
    }


def snap(contract="NQU6", quality="EXPLICIT_CONTRACT"):
    return {
        "status": "LIVE",
        "provider": "test",
        "timestamp": 0,
        "data": {
            "nq_liquidity": {
                "symbol": contract,
                "source_quality": quality,
                "source": "Polygon/Massive explicit NQ contract " + contract,
                "current_price": 25000.0,
            },
            "nq_futures_price": 25000.0,
            "news": .2,
        },
    }


async def fake_entry(contract, as_of):
    return {"close": 25000.0, "bar_end_utc": (as_of - timedelta(minutes=1)).isoformat(), "age_minutes": 1.0}


async def main():
    # DST: 13:00 ET is 17:00 UTC in EDT, 18:00 UTC in EST.
    summer = datetime(2026, 9, 3, 17, 5, tzinfo=timezone.utc)
    winter = datetime(2026, 1, 15, 18, 5, tzinfo=timezone.utc)
    check("summer checkpoint DST", checkpoint_state(summer)["eligible_now"] is True)
    check("winter checkpoint DST", checkpoint_state(winter)["eligible_now"] is True)
    check("summer wrong UTC hour blocked", checkpoint_state(datetime(2026, 9, 3, 18, 5, tzinfo=timezone.utc))["eligible_now"] is False)
    check("weekend blocked", checkpoint_state(datetime(2026, 9, 5, 17, 5, tzinfo=timezone.utc))["eligible_now"] is False)
    check("missed backfill explicitly false", checkpoint_state(datetime(2026, 9, 3, 20, 0, tzinfo=timezone.utc))["missed_backfill_allowed"] is False)
    # The V6 campaign (CLEAR-NASDAQ-FORWARD-OOS-V6-V672, sealed 2026-09-08) is
    # RETIRED. Step A repaired the canonical signal identity and A6/A7 added the
    # artifact guard and the three-identity split; between them eight files
    # inside the sealed production fingerprint changed and three were added, so
    # the pinned model fingerprint can never match again. The seal FILE itself
    # is untouched and still hashes correctly.
    #
    # This asserted "campaign seal valid". Making that true again would require
    # resealing a retired campaign against code that is not the code its results
    # came from. The correct assertion is that the legacy campaign stays invalid
    # and validation-ineligible, and that no successor has started.
    seal = verify_campaign_seal()
    check("retired V6 seal FILE is untampered", seal["seal_hash_valid"] is True)
    check("retired V6 campaign is NOT valid under the repaired identity",
          seal["ok"] is False and seal["model_fingerprint_match"] is False)
    check("still the V6 campaign; no successor sealed",
          seal["campaign_id"] == "CLEAR-NASDAQ-FORWARD-OOS-V6-V672")
    check("historical tuning after seal forbidden", seal["policy"]["historical_tuning_after_seal_allowed"] is False)
    check("no directional forecast locked (alpha spent = 0)",
          verify_ledger(DEFAULT_ROOT)["forecast_locks"] == 0)

    # With the retired V6 seal in force every lock is refused fail-closed. That
    # refusal is the correct production behaviour and is asserted here against
    # the REAL seal. The ledger, evidence and resolution mechanics below are a
    # different subject, so the seal gate is then neutralised for them exactly
    # as test_freeze_parity_v667 does. Nothing is resealed, no fingerprint is
    # altered, and the production ledger is never written: every lock below
    # runs inside a temporary directory.
    import fia.forward_oos as _foos
    _refused = await lock_live_forecast(fc(summer), snap(), Path(tempfile.mkdtemp()),
                                        now=summer, entry_lookup=fake_entry)
    check("retired V6 seal refuses every live lock fail-closed",
          _refused["created"] is False
          and _refused["reason"] == "CAMPAIGN_SEAL_OR_MODEL_FINGERPRINT_INVALID")

    # Neutralise the seal gate for the remainder of main(). This process runs
    # this test and nothing else, and every lock below writes into a temporary
    # directory, so the production ledger is never touched. Restored at the end.
    _real_seal = _foos.verify_campaign_seal
    _foos.verify_campaign_seal = lambda *a, **k: {"ok": True, "policy": {}}

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        first = await lock_live_forecast(fc(summer), snap(), root, now=summer, entry_lookup=fake_entry)
        check("first live forecast locked", first["ok"] and first["created"])
        check("ledger has exactly one lock", verify_ledger(root)["forecast_locks"] == 1)
        rec = records(root)[0]
        check("forecast marked genuinely new", rec["forecast_id"].startswith("NQ-FOOS-20260903"))
        base_locked = rec["models"][MODEL_NAME]
        check("4h probability explicitly locked", base_locked["horizon_probabilities"]["4h"]["bullish_probability"] == 65.0)
        check("8h probability explicitly locked", base_locked["horizon_probabilities"]["8h"]["bullish_probability"] == 65.0)
        check("shared horizon probability source disclosed", base_locked["horizon_probabilities"]["4h"]["source"] == "BASE_FIA_SHARED_PREMOVE_DISTRIBUTION")
        evidence_path = root / rec["evidence"]["path"]
        check("evidence exists", evidence_path.exists())
        check("evidence hash matches lock", sha256_file(evidence_path) == rec["evidence"]["sha256"])
        mode = stat.S_IMODE(evidence_path.stat().st_mode)
        check("evidence made read-only", mode & 0o222 == 0)

        duplicate = await lock_live_forecast(fc(summer), snap(), root, now=summer + timedelta(minutes=1), entry_lookup=fake_entry)
        check("duplicate checkpoint does not rewrite", duplicate["created"] is False and verify_ledger(root)["forecast_locks"] == 1)

        before_lock_hash = rec["lock_event_hash"]
        before_evidence_hash = rec["evidence"]["sha256"]
        seen_contracts = []

        async def resolver(contract, target):
            seen_contracts.append(contract)
            # Bullish outcomes for both horizons.
            px = 25100.0 if len(seen_contracts) == 1 else 25200.0
            return {"close": px, "bar_end_utc": target.isoformat(), "age_minutes": 0.0}

        res = await resolve_due_forecasts(None, root, now=summer + timedelta(hours=9), price_lookup=resolver)
        check("4h and 8h resolution events appended", res["resolved"] == 2)
        post = records(root)[0]
        check("frozen entry contract reused", seen_contracts == ["NQU6", "NQU6"])
        check("forecast lock hash unchanged after outcomes", post["lock_event_hash"] == before_lock_hash)
        check("evidence unchanged after outcomes", post["evidence"]["sha256"] == before_evidence_hash and sha256_file(evidence_path) == before_evidence_hash)
        check("4h actual attached separately", post["4h"]["actual_direction"] == "BULLISH")
        check("8h actual attached separately", post["8h"]["actual_direction"] == "BULLISH")
        check("ledger remains valid after resolution", verify_ledger(root)["ok"])
        check("loss/win event count retained", verify_ledger(root)["events"] == 3)

        report = forward_report(root)
        check("forward report counts real lock", report["new_forward_forecasts_locked"] == 1)
        check("sample remains collecting below 30", report["stage"] == "COLLECTING_NEW_UNSEEN_FORECASTS")
        check("base metrics have one observation", report["base_fia"]["4h"]["n"] == 1 and report["base_fia"]["8h"]["n"] == 1)
        check("no candidate means no promotion", report["promotion"]["verdict"] == "NO_PROMOTION")
        check("old holdout permanently excluded", report["scientific_policy"]["old_observed_holdout_untouched_rows"] == 0)

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        outside = datetime(2026, 9, 3, 19, 0, tzinfo=timezone.utc)
        r = await lock_live_forecast(fc(outside), snap(), root, now=outside, entry_lookup=fake_entry)
        check("outside checkpoint creates no historical backfill", r["created"] is False and verify_ledger(root)["events"] == 0)

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        r = await lock_live_forecast(fc(summer), snap("NQ=F", "CONTINUOUS_FALLBACK"), root, now=summer, entry_lookup=fake_entry)
        check("continuous futures proxy rejected for scientific lock", r["created"] is False and r["reason"] == "EXPLICIT_NQ_CONTRACT_REQUIRED")

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        r = await lock_live_forecast(
            fc(summer), snap(), root, now=summer, entry_lookup=fake_entry,
            shadow_candidate={"direction":"BULLISH","bullish_probability":70,"bearish_probability":30},
        )
        check("unsealed candidate cannot join campaign later", r["created"] is False and r["reason"] == "UNSEALED_SHADOW_CANDIDATE_FORBIDDEN")

    # Completed-bar policy: a 17:05 bar start ends 17:10 and is future at 17:07.
    as_of = datetime(2026, 9, 3, 17, 7, tzinfo=timezone.utc)
    payload = {
        "t": [
            datetime(2026, 9, 3, 16, 55, tzinfo=timezone.utc).timestamp(),
            datetime(2026, 9, 3, 17, 0, tzinfo=timezone.utc).timestamp(),
            datetime(2026, 9, 3, 17, 5, tzinfo=timezone.utc).timestamp(),
        ],
        "c": [24900, 25000, 26000],
    }
    px = _completed_close_from_polygon_payload(payload, as_of, 15)
    check("only completed 5m bar used", px["close"] == 25000.0 and px["bar_end_utc"].startswith("2026-09-03T17:05:00"))
    stale = _completed_close_from_polygon_payload({"t": [datetime(2026, 9, 3, 16, 0, tzinfo=timezone.utc).timestamp()], "c": [25000]}, as_of, 15)
    check("stale entry bar rejected", stale is None)

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        await lock_live_forecast(fc(summer), snap(), root, now=summer, entry_lookup=fake_entry)
        ep = root / records(root)[0]["evidence"]["path"]
        ep.chmod(0o644)
        ep.write_text("tampered", encoding="utf-8")
        check("evidence tampering detected", verify_ledger(root)["ok"] is False and any("evidence_hash" in x for x in verify_ledger(root)["issues"]))

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        await lock_live_forecast(fc(summer), snap(), root, now=summer, entry_lookup=fake_entry)
        event = sorted((root / "events").glob("*.json"))[0]
        event.chmod(0o644)
        obj = json.loads(event.read_text())
        obj["payload"]["models"][MODEL_NAME]["bullish_probability"] = 99
        event.write_text(json.dumps(obj), encoding="utf-8")
        audit = verify_ledger(root)
        check("forecast event tampering detected", audit["ok"] is False and any("event_hash" in x for x in audit["issues"]))

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        await lock_live_forecast(fc(summer), snap(), root, now=summer, entry_lookup=fake_entry)
        async def one_resolver(contract, target):
            return {"close": 24900.0, "bar_end_utc": target.isoformat(), "age_minutes": 0.0}
        await resolve_due_forecasts(None, root, now=summer + timedelta(hours=5), price_lookup=one_resolver)
        event_files = sorted((root / "events").glob("*.json"))
        check("tail deletion fixture has resolution", len(event_files) == 2)
        event_files[-1].unlink()
        audit = verify_ledger(root)
        check("tail event deletion detected by head anchor", audit["ok"] is False and any("ledger_head" in x for x in audit["issues"]))

    # Promotion gate is paired on the same NEW records and cannot use old holdout.
    synthetic = []
    for i in range(50):
        actual = "BULLISH" if i % 2 == 0 else "BEARISH"
        base_dir = actual if i < 35 else ("BEARISH" if actual == "BULLISH" else "BULLISH")
        cand_dir = actual if i < 40 else ("BEARISH" if actual == "BULLISH" else "BULLISH")
        y = 75.0 if actual == "BULLISH" else 25.0
        # candidate more calibrated than base, with >=2pp accuracy advantage.
        synthetic.append({
            "models": {
                MODEL_NAME: {"direction": base_dir, "bullish_probability": 65.0 if actual == "BULLISH" else 35.0, "confidence": 70, "regime": "TREND"},
                "SHADOW_CANDIDATE": {"direction": cand_dir, "bullish_probability": y, "confidence": 70, "regime": "TREND"},
            },
            "4h": {"actual_direction": actual},
            "8h": {"actual_direction": actual},
        })
    gate = promotion_gate(synthetic)
    check("promotion needs same 50 new rows", gate["details"]["4h"]["candidate"]["n"] == 50 and gate["details"]["8h"]["base"]["n"] == 50)
    check("strong paired candidate can become eligible but not auto-deploy", gate["verdict"] == "PROMOTION_ELIGIBLE_NOT_AUTO_DEPLOYED")
    check("promotion gate still excludes old holdout", gate["old_holdout_permanently_disqualified_as_untouched"] is True)

    _foos.verify_campaign_seal = _real_seal
    _restored = _foos.verify_campaign_seal()
    check("real seal restored and still correctly invalid",
          _restored["ok"] is False and _restored["seal_hash_valid"] is True)
    check("production ledger untouched by this test",
          verify_ledger(DEFAULT_ROOT)["forecast_locks"] == 0)

    print("=" * 72)
    print(f"SOL56 NEW FORWARD OOS INTEGRITY PASS {PASS}/{PASS}")
    print("historical_backfill = BLOCKED")
    print("forecast_mutation = BLOCKED_BY_ARCHITECTURE")
    print("old_holdout_as_untouched = BLOCKED")
    print("base_auto_replacement = BLOCKED")
    print("=" * 72)


if __name__ == "__main__":
    asyncio.run(main())
