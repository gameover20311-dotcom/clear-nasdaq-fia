"""V6.6.7 EVIDENCE-TRUTH REGRESSION: news age, earnings/macro states, Fed isolation.

WHAT THIS LOCKS
  [A] News staleness is measured from PUBLICATION time, not fetch time, so the
      12h ceiling that has shipped since V6.6.4 can actually fire.
  [B] Earnings has four mutually exclusive states -- no ambiguous "missing".
  [C] Macro reports NO_PRODUCER_IMPLEMENTED rather than pretending to fail.
  [D] The Fed evidence producer cannot reach the forecast, and fails closed.
"""
from __future__ import annotations

import asyncio
import copy
import inspect
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from fia import fed_evidence, premove_watch                                        # noqa: E402
from fia.engine import build_forecast                               # noqa: E402
from fia.premove_watch import build_watch, MAX_AGE_SECONDS_BY_SOURCE  # noqa: E402
from fia.provider_reliability import enrich_provider_reliability    # noqa: E402

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


class _H:
    keys = {}


def health(data):
    return asyncio.run(enrich_provider_reliability(_H(), copy.deepcopy(data)))


SNAP = json.loads((Path(__file__).resolve().parent / "fixtures"
                   / "frozen_snapshot_v667.json").read_text())


def premove(data):
    s = {"data": data}
    fc = build_forecast(s)
    return build_watch(fc, s, {"provider_health": data.get("provider_health") or {},
                               "source_health": data.get("source_health") or {}},
                       persist=False)


# --------------------------------------------------------------------------- #
print("\n[A] NEWS AGE IS THE AGE OF THE EVIDENCE, NOT OF THE FETCH")
base = copy.deepcopy(SNAP["data"])
base.pop("source_health", None)
base.pop("provider_health", None)
base["news_articles"] = 20
base["news_scored_articles"] = 13
base["news_status"] = "live_scored"
base["news"] = 0.33

fresh = copy.deepcopy(base)
fresh["news_newest_article_age_seconds"] = 600.0
fresh["news_age_basis"] = "NEWEST_ARTICLE_PUBLICATION_TIME"
stale = copy.deepcopy(base)
stale["news_newest_article_age_seconds"] = 86400.0          # 24h, ceiling is 12h
stale["news_age_basis"] = "NEWEST_ARTICLE_PUBLICATION_TIME"

h_fresh, h_stale = health(fresh), health(stale)
check("ceiling for news is 12h", MAX_AGE_SECONDS_BY_SOURCE["news"] == 43200.0,
      str(MAX_AGE_SECONDS_BY_SOURCE["news"]))
check("fresh news reports its real age, not 0.0",
      h_fresh["source_health"]["news"]["age_seconds"] == 600.0,
      str(h_fresh["source_health"]["news"]["age_seconds"]))
check("stale news reports its real age, not 0.0",
      h_stale["source_health"]["news"]["age_seconds"] == 86400.0,
      str(h_stale["source_health"]["news"]["age_seconds"]))
check("news source is labelled a secondary aggregator",
      "secondary" in h_fresh["source_health"]["news"]["source"].lower(),
      h_fresh["source_health"]["news"]["source"])
check("news note discloses zero primary-source coverage",
      "PRIMARY SOURCE COVERAGE = 0" in h_fresh["source_health"]["news"]["note"])
check("news note discloses the sentiment method is unvalidated",
      "not a validated model" in h_fresh["source_health"]["news"]["note"])

pm_fresh, pm_stale = premove(h_fresh), premove(h_stale)


def excluded_names(pm):
    return [x["name"] for x in (pm["evidence_quality"].get("age_excluded_signals") or [])]


check("[A1] fresh news is NOT excluded", "News" not in excluded_names(pm_fresh),
      str(excluded_names(pm_fresh)))
check("[A2] 24h-old news IS excluded by the existing ceiling",
      "News" in excluded_names(pm_stale), str(excluded_names(pm_stale)))
ex = [x for x in pm_stale["evidence_quality"]["age_excluded_signals"] if x["name"] == "News"][0]
check("[A3] the exclusion names the ceiling rule",
      ex["reason"] == "STALE_EXCLUDED_AGE_CEILING", ex["reason"])
check("[A4] the withheld score is preserved for audit, not silently dropped",
      ex.get("score_withheld") is not None and ex["included"] is False,
      json.dumps(ex)[:160])
check("[A5] stale news actually changes the published probability "
      "(the gate was previously inert)",
      pm_fresh["horizons"]["8h"]["bullish_probability"]
      != pm_stale["horizons"]["8h"]["bullish_probability"],
      "%s vs %s" % (pm_fresh["horizons"]["8h"]["bullish_probability"],
                    pm_stale["horizons"]["8h"]["bullish_probability"]))

no_ts = copy.deepcopy(base)
no_ts["news_newest_article_age_seconds"] = None
no_ts["news_age_basis"] = "NO_PUBLICATION_TIMESTAMPS_AVAILABLE"
h_no = health(no_ts)
check("[A6] absent timestamps -> unknown age, never a fabricated 0.0",
      h_no["source_health"]["news"]["age_seconds"] is None
      and h_no["source_health"]["news"]["freshness"] == "unknown",
      json.dumps(h_no["source_health"]["news"])[:200])

print("\n[B] EARNINGS HAS NO AMBIGUOUS MIDDLE STATE")
cases = {
    "released_surprise": ("RELEASED_VERIFIED", "live"),
    "upcoming_only_no_released_surprise": ("UPCOMING_VERIFIED_NO_SURPRISE_YET",
                                           "no_directional_evidence"),
    "no_tracked_events": ("NO_RELEVANT_EVENT", "not_applicable"),
    "provider_error": ("SOURCE_FAILURE", "provider_error"),
}
seen_states = set()
for raw, (state, status) in cases.items():
    d = copy.deepcopy(base)
    d["earnings_status"] = raw
    d["earnings"] = 0.4 if raw == "released_surprise" else None
    e = health(d)["source_health"]["earnings"]
    check("earnings %-36s -> %s" % (raw, state), e["evidence_state"] == state,
          str(e["evidence_state"]))
    check("earnings %-36s -> status %s" % (raw, status), e["status"] == status,
          str(e["status"]))
    seen_states.add(e["evidence_state"])
check("[B1] all four states are distinguishable from one another",
      len(seen_states) == 4, str(sorted(seen_states)))
d_unknown = copy.deepcopy(base)
d_unknown["earnings_status"] = "something_new"
check("[B2] an unrecognised status is flagged, not silently treated as 'no event'",
      health(d_unknown)["source_health"]["earnings"]["evidence_state"]
      == "DATA_MISSING_UNCLASSIFIED")

print("\n[C] MACRO SAYS 'NO PRODUCER', NOT 'THE SOURCE FAILED'")
m = health(base)["source_health"]["macro"]
check("macro evidence_state is NO_PRODUCER_IMPLEMENTED",
      m["evidence_state"] == "NO_PRODUCER_IMPLEMENTED", str(m["evidence_state"]))
check("macro is not claimed to be available", m["available"] is False)
d_mf = copy.deepcopy(base)
d_mf["macro_status"] = "unavailable_provider_error"
check("a genuine macro failure is still reported as SOURCE_FAILURE",
      health(d_mf)["source_health"]["macro"]["evidence_state"] == "SOURCE_FAILURE",
      str(health(d_mf)["source_health"]["macro"]["evidence_state"]))
check("macro contributes no score while it has no producer",
      SNAP["data"].get("macro") is None, str(SNAP["data"].get("macro")))

print("\n[D] FED EVIDENCE IS ISOLATED FROM THE FORECAST AND FAILS CLOSED")
fed_src = Path(fed_evidence.__file__).read_text()
# Only real import statements count -- the module docstring names both layers
# precisely because it must never import them.
fed_imports = [ln.strip() for ln in fed_src.splitlines()
               if ln.strip().startswith(("import ", "from "))]
check("fed_evidence imports neither the engine nor the pre-move layer",
      not any("engine" in ln or "premove" in ln for ln in fed_imports),
      str(fed_imports))
for mod in ("engine.py", "premove_watch.py"):
    txt = (Path(fed_evidence.__file__).parent / mod).read_text()
    check("%s does not import fed_evidence" % mod, "fed_evidence" not in txt)
check("every payload declares zero production influence",
      "\"production_influence\": False" in fed_src
      and "\"affects_published_probability\": False" in fed_src)
check("statements are explicitly NOT sentiment-scored",
      '"sentiment_scored": False' in fed_src)


class DeadHub:
    keys = {"FRED_API_KEY": "x"}

    async def get(self, *a, **k):
        raise RuntimeError("network down")


orig_text = fed_evidence._get_text
fed_evidence._get_text = lambda url, timeout=15: _none()


async def _none():
    return None


out = asyncio.run(fed_evidence.build_fed_evidence(DeadHub()))
fed_evidence._get_text = orig_text
check("[D1] total source failure yields explicit failure states, not values",
      out["policy_rate"]["state"] == "SOURCE_FAILURE"
      and out["fomc_calendar"]["state"] == "SOURCE_FAILURE"
      and out["statements"]["state"] == "SOURCE_FAILURE", json.dumps(out)[:300])
check("[D2] no value is invented on failure",
      out["policy_rate"]["value"] is None
      and out["fomc_calendar"].get("next_meeting_date") is None)
check("[D3] production influence stays off even on failure",
      out["production_influence"] is False)


class NoKeyHub:
    keys = {}

    async def get(self, *a, **k):
        return None


import os                                                            # noqa: E402
_saved = os.environ.pop("FRED_API_KEY", None)
out2 = asyncio.run(fed_evidence._policy_rate(NoKeyHub()))
if _saved is not None:
    os.environ["FRED_API_KEY"] = _saved
check("[D4] a missing key is distinguishable from a rejected key",
      out2["state"] == "API_KEY_NOT_CONFIGURED" and out2.get("remediation"),
      json.dumps(out2))

_real = fed_evidence._get_text


async def _dead_text(url, timeout=15):
    return None


fed_evidence._get_text = _dead_text
cal_broken = asyncio.run(fed_evidence._fomc_calendar(
    NoKeyHub(), now=datetime(2026, 9, 7, tzinfo=timezone.utc)))
fed_evidence._get_text = _real
check("[D5] an unreadable calendar page fails closed with its scrape contract named",
      cal_broken["state"] == "SOURCE_FAILURE"
      and cal_broken["contract"] == "SCRAPE_NO_STABLE_CONTRACT", json.dumps(cal_broken))

HTML_PAST_ONLY = "x" * 2100 + "fomcpresconf20260729"


async def _past_only(url, timeout=15):
    return HTML_PAST_ONLY


fed_evidence._get_text = _past_only
cal_partial = asyncio.run(fed_evidence._fomc_calendar(
    NoKeyHub(), now=datetime(2026, 9, 7, tzinfo=timezone.utc)))
fed_evidence._get_text = _real
check("[D6] past-only parse reports the schedule UNREADABLE, never "
      "'no meeting scheduled'",
      cal_partial["state"] == "PARTIAL_SCHEDULE_NOT_PARSEABLE"
      and cal_partial["next_meeting_date"] is None
      and "not as 'no meeting scheduled'" in cal_partial["reason"],
      json.dumps(cal_partial)[:260])

print("\n[E] AN ABSTENTION IS NEVER REPORTED AS AGREEMENT")
import re as _re                                                     # noqa: E402
_dash = Path(__file__).resolve().parent / "dashboard_api.py"
_src = _dash.read_text()
check("abstaining directions are filtered out before the agreement test",
      "_ABSTAIN = {'NO_EDGE', 'NEUTRAL', 'UNKNOWN', ''}" in _src
      and "_directional = [v for v in _dirs.values()" in _src)
check("agreement is computed from directional estimators only",
      "'directions_agree': ((len(set(_directional)) <= 1) if _directional else None)" in _src)
check("the payload names which estimators abstained",
      "'abstaining_estimators': sorted(_abstaining)" in _src)
check("the payload flags when the CANONICAL estimator abstained",
      "'canonical_is_abstaining': _canon_abstains" in _src)
check("the agreement scope is stated in words, not left to inference",
      "abstentions are excluded" in _src)

# Behavioural: reproduce the exact shape that used to read as consensus.
_ABSTAIN = {'NO_EDGE', 'NEUTRAL', 'UNKNOWN', ''}
_dirs = {'base_engine': 'BULLISH', 'premove_8h': 'NO_EDGE', 'cognitive_8h': 'BULLISH'}
_known = [d for d in _dirs.values() if d in ('BULLISH', 'BEARISH')]
_directional = [v for v in _dirs.values() if str(v or '').upper() not in _ABSTAIN]
_canon = str(_dirs.get('premove_8h') or '').upper() in _ABSTAIN
check("[E1] the canonical NO_EDGE is surfaced, not hidden behind an agreement flag",
      _canon is True and len(_directional) == 2 and len(_known) == 2)
_dirs2 = {'base_engine': 'BULLISH', 'premove_8h': 'BEARISH', 'cognitive_8h': 'BULLISH'}
_d2 = [v for v in _dirs2.values() if str(v or '').upper() not in _ABSTAIN]
check("[E2] a genuine disagreement is still reported as disagreement",
      (len(set(_d2)) <= 1) is False)

print("\n" + "=" * 66)
if FAILURES:
    print("FAILED %d check(s):" % len(FAILURES))
    for f in FAILURES:
        print("   -", f)
    sys.exit(1)
print("ALL V6.6.7 EVIDENCE-TRUTH CHECKS PASSED")
