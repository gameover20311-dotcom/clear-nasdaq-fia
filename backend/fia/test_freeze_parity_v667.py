"""V6.6.7 PRE-FREEZE PROOFS: display/lock parity, abstention, proxy honesty,
research isolation, determinism.

Every check runs against a FROZEN provider snapshot, so a result here is
reproducible and is not a claim about whatever the market happened to be doing.

WHAT THIS PROVES
  [1] The ledger locks EXACTLY the per-horizon numbers the dashboard displayed.
  [2] With no pre-move view, the ledger says so instead of implying a
      per-horizon estimate it does not have.
  [3] A displayed abstention can never enter the directional record.
  [4] An abstention IS recorded, as an explicitly non-directional observation.
  [5] The two proxy signals describe what they actually measure.
  [6] The reasoning/Three-Brain layer cannot reach the published probability.
  [7] The published probability is deterministic given fixed evidence.
"""
from __future__ import annotations

import asyncio
import copy
import inspect
import json
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from fia import forward_oos, premove_watch          # noqa: E402
from fia.engine import build_forecast               # noqa: E402
from fia.premove_watch import build_watch, display_label, SIGNAL_DISPLAY  # noqa: E402

# ---------------------------------------------------------------------------
# REPRODUCIBILITY: the fixture carries absolute observation timestamps, so the
# session/venue decision depends on "now". Left unpinned, this suite would
# silently change meaning every time it ran. `now` is pinned to the instant the
# fixture was captured, which is what makes these results a fixed record.
# ---------------------------------------------------------------------------
from datetime import datetime as _dtc, timezone as _tzc               # noqa: E402
from fia import market_sessions as _ms                                # noqa: E402

FIXTURE_NOW = _dtc(2026, 9, 7, 8, 30, 57, tzinfo=_tzc.utc)
_real_session_state = _ms.session_state


def _pinned_session_state(source, age_seconds, live_ceiling_seconds, now=None):
    return _real_session_state(source, age_seconds, live_ceiling_seconds,
                               now=now or FIXTURE_NOW)


premove_watch.session_state = _pinned_session_state
_ms.session_state = _pinned_session_state
# The evidence-age clock must be pinned for the same reason.
premove_watch._utc = lambda: FIXTURE_NOW

FAILURES = []


def check(name, cond, detail=""):
    if cond:
        print("  PASS  %s" % name)
    else:
        print("  FAIL  %s   %s" % (name, detail))
        FAILURES.append(name)


SNAP_PATH = Path(__file__).resolve().parent / "fixtures" / "frozen_snapshot_v667.json"
snapshot = json.loads(SNAP_PATH.read_text())
data = snapshot["data"] if isinstance(snapshot.get("data"), dict) else snapshot
ph = {"provider_health": data.get("provider_health") or {},
      "source_health": data.get("source_health") or {}}


def watch(snap=None):
    snap = snap if snap is not None else snapshot
    d = snap["data"] if isinstance(snap.get("data"), dict) else snap
    fc = build_forecast(snap if isinstance(snap.get("data"), dict) else {"data": d})
    h = {"provider_health": d.get("provider_health") or {},
         "source_health": d.get("source_health") or {}}
    return fc, build_watch(fc, snap, h, persist=False)


forecast, premove = watch()

# --------------------------------------------------------------------------- #
print("\n[1] DISPLAY -> LOCK PARITY (per horizon, exact)")
# The base engine must be directional for _forecast_values to run at all; that
# is a separate guard and is proven in [3]. Force a directional base so the
# parity arithmetic itself is what is under test here.
# build_forecast returns a pydantic model; the ledger normalises it the same way.
base_fc = copy.deepcopy(forward_oos._primitive(forecast))
if str(base_fc.get("direction", "")).upper() not in {"BULLISH", "BEARISH"}:
    base_fc["direction"] = "BULLISH"
    base_fc["bullish_probability"] = 55.0
    base_fc["bearish_probability"] = 45.0
    base_fc["confidence"] = 40.0

vals = forward_oos._forecast_values(base_fc, premove)
hp = vals["horizon_probabilities"]
for h in ("4h", "8h"):
    shown = premove["horizons"][h]
    check("%s locked bullish == displayed bullish" % h.upper(),
          abs(hp[h]["bullish_probability"] - float(shown["bullish_probability"])) < 1e-9,
          "locked=%s shown=%s" % (hp[h]["bullish_probability"], shown["bullish_probability"]))
    check("%s locked bearish == displayed bearish" % h.upper(),
          abs(hp[h]["bearish_probability"] - float(shown["bearish_probability"])) < 1e-9)
    check("%s locked direction == displayed direction" % h.upper(),
          hp[h]["direction"] == str(shown["direction"]).upper(),
          "%s vs %s" % (hp[h]["direction"], shown["direction"]))
    check("%s locked confidence == displayed confidence" % h.upper(),
          hp[h]["confidence"] == shown["confidence"])
    check("%s locked raw == displayed raw" % h.upper(),
          hp[h]["raw_probability"] == shown["raw_probability"])
    check("%s provenance names the displayed pre-move layer" % h.upper(),
          hp[h]["source"] == "PREMOVE_WATCH_PER_HORIZON_AS_DISPLAYED", hp[h]["source"])
check("4H and 8H are NOT the same number copied twice",
      hp["4h"]["bullish_probability"] != hp["8h"]["bullish_probability"]
      or premove["horizons"]["4h"]["bullish_probability"]
      == premove["horizons"]["8h"]["bullish_probability"],
      "duplication would be a parity failure unless genuinely equal")
check("evidence hash recorded for independent re-verification",
      vals["premove"]["evidence_hash"] == premove["evidence_hash"],
      str(vals["premove"]["evidence_hash"]))
check("pre-move forecast id recorded",
      vals["premove"]["forecast_id"] == premove.get("forecast_id"))

print("\n[2] NO PRE-MOVE VIEW -> the ledger must NOT imply a per-horizon estimate")
vals_np = forward_oos._forecast_values(base_fc, None)
for h in ("4h", "8h"):
    check("%s falls back with an explicit shared-distribution tag" % h.upper(),
          vals_np["horizon_probabilities"][h]["source"]
          == "BASE_FIA_SHARED_PREMOVE_DISTRIBUTION",
          vals_np["horizon_probabilities"][h]["source"])
    check("%s fallback carries no fabricated per-horizon confidence" % h.upper(),
          "confidence" not in vals_np["horizon_probabilities"][h])

print("\n[3] DISPLAYED ABSTENTION CANNOT ENTER THE DIRECTIONAL RECORD")


class _Seal:
    """Neutralise the seal gate ONLY, so the abstention guard is what is tested.
    The real seal behaviour is proven separately in [3d]."""
    def __enter__(self):
        self._orig = forward_oos.verify_campaign_seal
        forward_oos.verify_campaign_seal = lambda *a, **k: {"ok": True, "policy": {}}
        return self

    def __exit__(self, *a):
        forward_oos.verify_campaign_seal = self._orig


def try_lock(pm, root, now, fc=None):
    return asyncio.run(forward_oos.lock_live_forecast(
        fc if fc is not None else lock_fc, snapshot, root=root, now=now, premove=pm))


import tempfile                                                     # noqa: E402
from datetime import datetime, timezone                             # noqa: E402

tmp = Path(tempfile.mkdtemp(prefix="foos_freeze_"))
# A moment inside the live checkpoint window, expressed deterministically.
state_probe = None
for hh in range(24):
    cand = datetime(2026, 9, 9, hh, 5, tzinfo=timezone.utc)
    if forward_oos.checkpoint_state(cand)["eligible_now"]:
        state_probe = cand
        break
check("a deterministic in-window checkpoint instant exists", state_probe is not None)

# The lock is also age-gated. Prove that gate fires, then stamp the fixture
# forecast at the probe instant so the ABSTENTION guard is what is under test.
stale_fc = copy.deepcopy(base_fc)
stale_fc["generated_at"] = (state_probe - __import__("datetime").timedelta(minutes=16)).isoformat()
with _Seal():
    stale_probe = try_lock(premove, tmp, state_probe, fc=stale_fc)
check("[3g] a forecast older than the lock window is refused",
      stale_probe["created"] is False
      and stale_probe["reason"] == "FORECAST_NOT_FRESH_ENOUGH_TO_LOCK",
      json.dumps(stale_probe)[:160])

lock_fc = copy.deepcopy(base_fc)
lock_fc["generated_at"] = state_probe.isoformat()

pm_no_edge = copy.deepcopy(premove)
pm_no_edge["state"] = "NO_EDGE"
with _Seal():
    r = try_lock(pm_no_edge, tmp, state_probe)
check("[3a] NO_EDGE pre-move state is refused",
      r["created"] is False and r["reason"] == "PREMOVE_STATE_NOT_LOCKABLE", json.dumps(r)[:200])

pm_abst = copy.deepcopy(premove)
pm_abst["state"] = "WATCH"
pm_abst["horizons"]["4h"]["direction"] = "NO_EDGE"
pm_abst["horizons"]["8h"]["direction"] = "BULLISH"
with _Seal():
    r2 = try_lock(pm_abst, tmp, state_probe)
check("[3b] a single abstaining horizon blocks the whole directional lock",
      r2["created"] is False
      and r2["reason"] == "PREMOVE_HORIZON_ABSTENTION_NOT_LOCKED_AS_DIRECTIONAL"
      and r2["abstained_horizons"] == ["4h"], json.dumps(r2)[:200])

for bad in ("MISSING_DATA", "DEGRADED", "STALE"):
    pm_bad = copy.deepcopy(premove)
    pm_bad["state"] = bad
    with _Seal():
        rb = try_lock(pm_bad, tmp, state_probe)
    check("[3c] %s pre-move state is refused" % bad,
          rb["created"] is False and rb["reason"] == "PREMOVE_STATE_NOT_LOCKABLE")

# The seal gate must be proven by breaking it deliberately, not by relying on
# the campaign happening to be out of date -- that made the check pass for the
# wrong reason before the campaign was resealed.
_orig_seal = forward_oos.verify_campaign_seal
forward_oos.verify_campaign_seal = lambda *a, **k: {
    "ok": False, "seal_hash_valid": True, "model_fingerprint_match": False}
r_seal = try_lock(pm_abst, tmp, state_probe)
forward_oos.verify_campaign_seal = _orig_seal
check("[3d] a broken model fingerprint fails the lock closed",
      r_seal["ok"] is False
      and r_seal["reason"] == "CAMPAIGN_SEAL_OR_MODEL_FINGERPRINT_INVALID",
      json.dumps(r_seal)[:160])
_live_seal = forward_oos.verify_campaign_seal()
check("[3d2] historical campaign seal hash remains valid",
      _live_seal.get("seal_hash_valid") is True,
      json.dumps({k: _live_seal.get(k) for k in
                  ("ok", "seal_hash_valid", "model_fingerprint_match")}))
check("[3d3] modified candidate does NOT match historical campaign fingerprint",
      _live_seal.get("model_fingerprint_match") is False,
      json.dumps({k: _live_seal.get(k) for k in
                  ("ok", "seal_hash_valid", "model_fingerprint_match")}))

r_out = asyncio.run(forward_oos.lock_live_forecast(
    base_fc, snapshot, root=tmp, now=datetime(2026, 9, 9, 3, 0, tzinfo=timezone.utc),
    premove=premove))
check("[3e] no backfill outside the checkpoint window",
      r_out["created"] is False and r_out["reason"] == "OUTSIDE_LIVE_CHECKPOINT_NO_BACKFILL",
      json.dumps(r_out)[:160])
check("[3f] nothing was written to the ledger by any refused attempt",
      not any((tmp / "events").glob("*")) if (tmp / "events").exists() else True)

print("\n[4] AN ABSTENTION IS RECORDED, AND IS NEVER DIRECTIONAL")
src = inspect.getsource(forward_oos.lock_abstention_observation)
check("writes a distinct ABSTENTION_OBSERVATION event type",
      "ABSTENTION_OBSERVATION" in src)
check("marks the record non-directional", '"directional": False' in src)
check("marks the record unscoreable as directional",
      '"scoreable_as_directional": False' in src)
check("excludes the record from directional statistics",
      '"excluded_from_directional_statistics": True' in src)
check("abstention is deduplicated per checkpoint date",
      "CHECKPOINT_ABSTENTION_ALREADY_RECORDED" in src)
check("abstention obeys the same no-backfill rule",
      "OUTSIDE_LIVE_CHECKPOINT_NO_BACKFILL" in src)
check("abstention obeys the same seal rule",
      "CAMPAIGN_SEAL_OR_MODEL_FINGERPRINT_INVALID" in src)
r_ab = asyncio.run(forward_oos.lock_abstention_observation(
    base_fc, snapshot, premove, root=tmp,
    now=datetime(2026, 9, 9, 3, 0, tzinfo=timezone.utc)))
check("abstention cannot be backfilled either",
      r_ab["created"] is False
      and r_ab["reason"] == "OUTSIDE_LIVE_CHECKPOINT_NO_BACKFILL", json.dumps(r_ab)[:160])

print("\n[5] PROXY SIGNALS DESCRIBE WHAT THEY ACTUALLY MEASURE")
lbl_nq = display_label("NQ structure")
lbl_spx = display_label("SPX confirmation")
check("NQ structure is declared a proxy", lbl_nq["is_proxy"] is True)
check("NQ structure display name says QQQ, not NQ futures",
      "QQQ" in lbl_nq["display_name"] and "NQ futures" not in lbl_nq["display_name"],
      lbl_nq["display_name"])
check("NQ structure states what it is NOT", "NQ futures" in lbl_nq["not"], lbl_nq["not"])
check("SPX confirmation is declared a proxy", lbl_spx["is_proxy"] is True)
check("SPX confirmation display name says SPY", "SPY" in lbl_spx["display_name"],
      lbl_spx["display_name"])
check("SPX confirmation denies being a divergence statistic",
      "divergence" in lbl_spx["not"].lower(), lbl_spx["not"])
check("the participation factor no longer claims to be market breadth",
      "Breadth" in SIGNAL_DISPLAY
      and "breadth" not in SIGNAL_DISPLAY["Breadth"]["display_name"].lower(),
      SIGNAL_DISPLAY["Breadth"]["display_name"])
drivers = premove["horizons"]["8h"]["drivers"]
check("every displayed driver carries a display name", all("display_name" in d for d in drivers))
check("every displayed driver declares proxy status", all("is_proxy" in d for d in drivers))
proxies = [d for d in drivers if d.get("is_proxy")]
check("each proxy driver states what it measures and what it is not",
      all(d.get("measures") and d.get("not") for d in proxies),
      json.dumps(proxies)[:200])
check("the internal identity key is unchanged (weights still resolve)",
      all(d["name"] in premove_watch.HORIZON_WEIGHTS["8h"] for d in drivers),
      str([d["name"] for d in drivers]))

print("\n[6] THE REASONING / THREE-BRAIN LAYER CANNOT REACH THE FORECAST")
sig = inspect.signature(build_watch)
check("build_watch takes no cognitive/brain input",
      not any(k in sig.parameters for k in ("cognitive", "brain", "three_brain", "reasoning")),
      str(list(sig.parameters)))
pw_src = Path(premove_watch.__file__).read_text()
cog_imports = [ln.strip() for ln in pw_src.splitlines()
               if "cognitive" in ln and ("import" in ln)]
check("premove_watch imports nothing from the reasoning layer except calibration",
      all("calibration" in ln for ln in cog_imports), str(cog_imports))
eng_src = (Path(premove_watch.__file__).parent / "engine.py").read_text()
check("the base engine imports nothing from the reasoning layer",
      not any("cognitive" in ln and "import" in ln for ln in eng_src.splitlines()))
# Behavioural proof: drive the reasoning layer to both extremes; the published
# numbers must be byte-identical because it is not an input at all.
snap_bull = copy.deepcopy(snapshot)
snap_bear = copy.deepcopy(snapshot)
for s, v in ((snap_bull, {"stance": "BULLISH", "conviction": 5.0, "hard_hold": False}),
             (snap_bear, {"stance": "BEARISH", "conviction": 9.9, "hard_hold": True})):
    tgt = s["data"] if isinstance(s.get("data"), dict) else s
    tgt["cognitive"] = v
    tgt["three_brain"] = v
_, pm_bull = watch(snap_bull)
_, pm_bear = watch(snap_bear)
check("maximal bullish vs maximal bearish reasoning -> identical evidence hash",
      pm_bull["evidence_hash"] == pm_bear["evidence_hash"] == premove["evidence_hash"])
for h in ("4h", "8h"):
    check("%s published probability is unmoved by the reasoning layer" % h.upper(),
          pm_bull["horizons"][h]["bullish_probability"]
          == pm_bear["horizons"][h]["bullish_probability"]
          == premove["horizons"][h]["bullish_probability"])
    check("%s confidence is unmoved by the reasoning layer" % h.upper(),
          pm_bull["horizons"][h]["confidence"] == pm_bear["horizons"][h]["confidence"])

print("\n[7] DETERMINISM ON FIXED EVIDENCE")
_, again = watch()
check("same frozen evidence -> same evidence hash",
      again["evidence_hash"] == premove["evidence_hash"])
for h in ("4h", "8h"):
    check("%s probability is reproducible" % h.upper(),
          again["horizons"][h]["bullish_probability"]
          == premove["horizons"][h]["bullish_probability"])
    check("%s confidence is reproducible" % h.upper(),
          again["horizons"][h]["confidence"] == premove["horizons"][h]["confidence"])

print("\n" + "=" * 66)
print("frozen premove state=%s  4H=%s%% conf=%s  8H=%s%% conf=%s" % (
    premove.get("state"),
    premove["horizons"]["4h"]["bullish_probability"], premove["horizons"]["4h"]["confidence"],
    premove["horizons"]["8h"]["bullish_probability"], premove["horizons"]["8h"]["confidence"]))
if FAILURES:
    print("FAILED %d check(s):" % len(FAILURES))
    for f in FAILURES:
        print("   -", f)
    sys.exit(1)
print("ALL V6.6.7 PRE-FREEZE PARITY / ABSTENTION / ISOLATION CHECKS PASSED")
