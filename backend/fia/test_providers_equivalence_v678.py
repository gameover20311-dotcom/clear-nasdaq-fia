#!/usr/bin/env python3
"""PROVIDERS BEHAVIOUR-EQUIVALENCE HARNESS (pre-split baseline)

PURPOSE
-------
The owner approved a 3-way split of providers.py. The split may only be called
behaviour-preserving if identical inputs still produce identical outputs. This
harness is that proof, and it is deliberately recorded BEFORE the split so the
baseline cannot be fitted to the result afterwards.

It exercises the DETERMINISTIC surface of ProviderHub — every method that
computes rather than fetches — with fixed inputs, and reduces the results to one
SHA-256. Nothing here touches the network, but providers.py imports yfinance at
module scope, so this harness is CI-only: it cannot even import in the offline
sandbox, and reports NOT TESTED (ENV) there rather than PASS.

WHAT IT COVERS AND WHAT IT DOES NOT
-----------------------------------
Covers: news scoring (the MODEL surface that produces data['news'] and therefore
the engine's News signal), news trust/recency/dedup/confirmation policy, value
transforms, session windows, article normalisation and staleness.

Does NOT cover: live transport, fallback chain selection under real provider
failure, or snapshot() assembly — those need network and real keys, and they are
exactly what the 8 CI-only provider tests exercise. This harness is a necessary
condition for the split, not a sufficient one. Do not read a PASS here as
"the split is safe"; the full CI suite is what decides that.

BASELINE_DIGEST below is recorded in CI from UNSPLIT providers.py, before the
split. If the split changes it, the split changed behaviour: HARD STOP.
"""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

try:
    from fia.providers import ProviderHub  # noqa: E402
except ModuleNotFoundError as _exc:        # pragma: no cover - environment gate
    # providers.py imports yfinance at module scope, so it cannot even be
    # IMPORTED without the real dependency set. This is independent confirmation
    # that a providers.py split can never be verified in the offline sandbox:
    # not partially, not at all. Reported as NOT TESTED (ENV), never as PASS.
    print(f"NOT_TESTED_ENV: providers.py is not importable here ({_exc})")
    print("ModuleNotFoundError — run this in CI where requirements.txt installs.")
    raise SystemExit(1)

# PINNED UNSPLIT BASELINE — owner-approved 2026-09-12.
#
# PROVENANCE
#   value        e2191da05e1a737c71ff88b3f5737b836d03974b6f784e9682a1595bd368e506
#   observations 131
#   recorded on  UNSPLIT providers.py at commit 087c889
#   reproduced   five consecutive local runs; PYTHONHASHSEED 1 / 999 / 12345;
#                and GitHub CI run 34661082160 on an independent runner.
#
# The first attempt to pin this failed honestly and is recorded so the value is
# not mistaken for something that always worked. Before commit 087c889 the digest
# was NOT reproducible: _news_normalized_words returns a set, json.dumps fell
# through to default=str, and str() on a set emits hash order, which Python
# randomises per process. Four runs produced four digests. Pinning any of them
# would have made the FIRST post-split comparison report a false HARD STOP.
# canonical() now sorts sets before serialising, which is lossless because set
# equality is order-independent.
#
# THIS VALUE IS NOT RECALCULATED AFTER THE SPLIT. A mismatch means the split
# changed behaviour, and the first differing observation must be identified and
# explained. It is never "fixed" by re-recording.
#
# Coverage added AFTER this pin lives in its own harness with its own pre-split
# baseline, so this observation set stays exactly 131 and stays comparable.
BASELINE_DIGEST = "e2191da05e1a737c71ff88b3f5737b836d03974b6f784e9682a1595bd368e506"

FIXED_NOW = datetime(2026, 6, 1, 17, 0, 0, tzinfo=timezone.utc)

ARTICLES = [
    {"title": "Nvidia beats on AI datacenter revenue, raises guidance",
     "description": "Chipmaker reports record quarter driven by accelerator demand.",
     "source": {"name": "Reuters"}, "publishedAt": "2026-06-01T15:30:00Z", "url": "https://r/1"},
    {"title": "Fed holds rates steady, signals patience on cuts",
     "description": "FOMC keeps target range unchanged; Powell cites sticky services inflation.",
     "source": {"name": "Bloomberg"}, "publishedAt": "2026-06-01T14:00:00Z", "url": "https://b/2"},
    {"title": "NVIDIA beats on AI data center revenue and raises guidance",
     "description": "Near-duplicate of the Reuters item, different outlet.",
     "source": {"name": "CNBC"}, "publishedAt": "2026-06-01T15:45:00Z", "url": "https://c/3"},
    {"title": "Apple supplier warns on component shortage into H2",
     "description": "Guidance cut on constrained display supply.",
     "source": {"name": "WSJ"}, "publishedAt": "2026-05-31T09:00:00Z", "url": "https://w/4"},
    {"title": "Random unrelated celebrity story",
     "description": "No market relevance whatsoever.",
     "source": {"name": "TabloidDaily"}, "publishedAt": "2026-06-01T16:00:00Z", "url": "https://t/5"},
]

hub = ProviderHub()
obs: dict = {}


def rec(key, value):
    obs[key] = value


def safe(key, fn, *a, **kw):
    try:
        rec(key, fn(*a, **kw))
    except Exception as exc:               # signature drift must itself be visible
        rec(key, f"__RAISED__:{type(exc).__name__}")


# ---- value transforms (MODEL) -------------------------------------------
for v in (-3.0, -1.25, -0.4, 0.0, 0.4, 1.25, 3.0):
    safe(f"normalize_change[{v}]", ProviderHub.normalize_change, v)
for y in (3.2, 3.9, 4.25, 4.73, 5.5):
    safe(f"normalize_yield[{y}]", ProviderHub.normalize_yield, y)
for v in (-9.0, -0.5, 0.0, 0.5, 9.0):
    safe(f"clamp[{v}]", ProviderHub.clamp, v)
for v in ("1.5", None, "", "abc", 2, 2.5):
    safe(f"safe_float[{v!r}]", ProviderHub.safe_float, v)

# ---- article normalisation + staleness (PROTOCOL) ------------------------
for i, a in enumerate(ARTICLES):
    safe(f"_normalize_live_news_article[{i}]", ProviderHub._normalize_live_news_article, a, "newsapi")
    safe(f"_news_article_age_seconds[{i}]", ProviderHub._news_article_age_seconds, a, FIXED_NOW)

# ---- news quality / trust / recency policy (PROTOCOL) --------------------
for i, a in enumerate(ARTICLES):
    safe(f"evaluate_news_quality[{i}]", hub.evaluate_news_quality, a)
    safe(f"calculate_news_recency_score[{i}]", hub.calculate_news_recency_score, a)
    safe(f"calculate_news_trust_score[{i}]", hub.calculate_news_trust_score, a)
safe("filter_news_quality", hub.filter_news_quality, list(ARTICLES))
safe("apply_news_trust_scores", hub.apply_news_trust_scores, list(ARTICLES))
safe("detect_duplicate_news", hub.detect_duplicate_news, list(ARTICLES))
# Takes a single article, not a list. Passing a list recorded __RAISED__ and
# left this method with no real coverage at all.
for i, a in enumerate(ARTICLES):
    safe(f"calculate_source_confirmation_score[{i}]",
         hub.calculate_source_confirmation_score, a)
for _n in (0, 1, 2, 3, 4, 5, 9):
    safe(f"calculate_source_confirmation_score[count:{_n}]",
         hub.calculate_source_confirmation_score,
         {"fia_source_confirmation_count": _n})
safe("news_headline_similarity[0v2]", hub.news_headline_similarity,
     ARTICLES[0]["title"], ARTICLES[2]["title"])
safe("news_headline_similarity[0v1]", hub.news_headline_similarity,
     ARTICLES[0]["title"], ARTICLES[1]["title"])
safe("_news_normalized_words", hub._news_normalized_words, ARTICLES[0]["title"])

# ---- news scoring: the MODEL surface feeding data['news'] ---------------
for i, a in enumerate(ARTICLES):
    safe(f"analyze_news_context[{i}]", hub.analyze_news_context, a)
    safe(f"analyze_news_context_v3[{i}]", hub.analyze_news_context_v3, a)
    safe(f"analyze_news_context_v3_weighted[{i}]", hub.analyze_news_context_v3_weighted, a)
    safe(f"analyze_news_context_v3_calibrated[{i}]", hub.analyze_news_context_v3_calibrated, a)
    safe(f"analyze_nasdaq_relevance_v3[{i}]", hub.analyze_nasdaq_relevance_v3, a)
safe("resolve_news_event_conflicts_v3", hub.resolve_news_event_conflicts_v3, list(ARTICLES))

# ---- instrument eligibility + sessions (PROTOCOL) -----------------------
safe("current_nq_futures_symbol", hub.current_nq_futures_symbol)
for name in ("asia", "london", "new_york"):
    safe(f"session_window_for_date[{name}]", hub.session_window_for_date, name, FIXED_NOW.date())
# Takes the candles payload alone. The old call passed (hub, "60") and raised
# TypeError, so this method had no real coverage either.
for _label, _payload in (
    ("empty", {}),
    ("none", None),
    ("ordered", {"t": [1748790000, 1748793600, 1748797200]}),
    ("unordered", {"t": [1748797200, 1748790000, 1748793600]}),
    ("dirty", {"t": [1748790000, "x", None, 1748797200]}),
    ("no_t", {"c": [1, 2, 3]}),
):
    safe(f"_latest_candle_start[{_label}]",
         ProviderHub._latest_candle_start, _payload)

# ---- phase20 provider path (TEST-FIXTURE-ONLY) --------------------------
# WHY THIS SECTION EXISTS
# fia_backtest_phase20/full_backtest.py is permanently blocked on
# MISSING_CANONICAL_DATA: polygon_news_20250901_20260831.json is unrecoverable,
# so phase20 dies at load_polygon_archive_cache() and never reaches the provider
# surface it would otherwise exercise. That leaves a hole in the pre-split
# evidence exactly where a provider refactor is riskiest.
#
# Resolved statically, phase20 touches eight ProviderHub methods after imports:
#   analyze_nasdaq_relevance_v3      analyze_news_context
#   analyze_news_context_v3_calibrated  apply_news_trust_scores
#   detect_duplicate_news            filter_news_quality
#   calculate_news_recency_score     get
# The first seven are already covered above. get() is the transport entry point
# and was the only one with no deterministic coverage at all.
#
# THESE FIXTURES ARE NOT EVIDENCE. They are refactor-equivalence inputs and
# nothing else: not historical data, not predictive data, not a substitute for
# the missing archive. They do NOT and must NOT make phase20 or phase28 green;
# both stay honestly red on MISSING_CANONICAL_DATA.
import asyncio                                                    # noqa: E402
import types                                                      # noqa: E402

import httpx                                                      # noqa: E402


class _StubResponse:
    def __init__(self, payload, status=200, raise_exc=None):
        self._payload, self.status_code, self._raise = payload, status, raise_exc

    def raise_for_status(self):
        if self._raise is not None:
            raise self._raise

    def json(self):
        return self._payload


class _StubClient:
    """Deterministic stand-in for httpx.AsyncClient. No socket is ever opened."""

    def __init__(self, response=None, exc=None, **_kw):
        self._response, self._exc = response, exc

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_a):
        return False

    async def get(self, url, params=None, headers=None):
        if self._exc is not None:
            raise self._exc
        return self._response


def _with_transport(response=None, exc=None):
    """Run hub.get() against a stubbed transport and capture stdout."""
    import io, contextlib
    real = httpx.AsyncClient
    httpx.AsyncClient = lambda **kw: _StubClient(response=response, exc=exc, **kw)
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            out = asyncio.run(hub.get(
                "https://finnhub.io/api/v1/company-news",
                params={"symbol": "AAPL", "token": "SECRET-TOKEN-VALUE"},
                headers={"X-Test": "1"}))
    finally:
        httpx.AsyncClient = real
    return {"returned": out, "printed": buf.getvalue().strip()}


# Branch 1: success -> the decoded JSON body is returned unchanged.
safe("get[success]", _with_transport, _StubResponse({"ok": True, "rows": [1, 2, 3]}))

# Branch 2: HTTP status error -> None, and the status is reported.
_status_exc = httpx.HTTPStatusError(
    "429 Too Many Requests",
    request=httpx.Request("GET", "https://finnhub.io/api/v1/company-news?token=SECRET-TOKEN-VALUE"),
    response=httpx.Response(429))
safe("get[http_status_error]", _with_transport, None, _status_exc)

# Branch 3: transport error -> None, and only the exception type is reported.
safe("get[transport_error]", _with_transport, None, httpx.ConnectError("refused"))

# Branch 4: malformed body -> None rather than a raised decode error.
class _BadJSON(_StubResponse):
    def json(self):
        raise ValueError("not json")


safe("get[undecodable_body]", _with_transport, _BadJSON(None))

# The security contract this method exists to hold: a provider credential in the
# query string must never reach the log, on ANY branch. Asserted as a recorded
# observation so a refactor that reintroduces the leak changes the digest.
_leak = []
for _k in ("get[http_status_error]", "get[transport_error]", "get[undecodable_body]"):
    _printed = obs.get(_k, {})
    _printed = _printed.get("printed", "") if isinstance(_printed, dict) else str(_printed)
    if "SECRET-TOKEN-VALUE" in _printed or "token=" in _printed:
        _leak.append(_k)
rec("get[credential_never_logged]", not _leak)
rec("get[failure_branches_return_none]", all(
    isinstance(obs.get(k), dict) and obs[k].get("returned") is None
    for k in ("get[http_status_error]", "get[transport_error]", "get[undecodable_body]")))

# The composition order phase20 applies to its news pool, pinned end to end so a
# split cannot reorder the pipeline without changing the digest.
_pool = list(ARTICLES)
safe("phase20_pipeline[dedup]", hub.detect_duplicate_news, list(_pool))
safe("phase20_pipeline[quality]", hub.filter_news_quality, list(_pool))
safe("phase20_pipeline[trust]", hub.apply_news_trust_scores, list(_pool))
for _i, _a in enumerate(ARTICLES):
    safe(f"phase20_pipeline[recency:{_i}]", hub.calculate_news_recency_score, _a)
    safe(f"phase20_pipeline[context:{_i}]", hub.analyze_news_context, _a)
    safe(f"phase20_pipeline[calibrated:{_i}]", hub.analyze_news_context_v3_calibrated, _a)
    safe(f"phase20_pipeline[relevance:{_i}]", hub.analyze_nasdaq_relevance_v3, _a)


def _stable(value):
    """Make a value order-stable before it is serialised.

    Some provider methods return a set. json.dumps cannot encode a set, so it
    fell through to default=str, and str() on a set emits its elements in hash
    order — which Python randomises per process via PYTHONHASHSEED. One
    observation, _news_normalized_words, was therefore different on every run
    and randomised the whole digest: four runs of this harness produced four
    different digests, so BASELINE_DIGEST could never have matched anything and
    every post-split comparison would have reported a false HARD STOP.

    Sorting a set loses nothing. Set equality is order-independent by
    definition, so comparing sorted elements is exactly equivalent to comparing
    the sets. Tuples are normalised to lists for the same reason: so an
    equivalent value cannot differ only by container type.
    """
    if isinstance(value, (set, frozenset)):
        return sorted(_stable(v) for v in value)
    if isinstance(value, (list, tuple)):
        return [_stable(v) for v in value]
    if isinstance(value, dict):
        return {k: _stable(v) for k, v in value.items()}
    return value


def canonical(value):
    return json.dumps(_stable(value), sort_keys=True, default=str,
                      separators=(",", ":"))


payload = {k: canonical(v) for k, v in sorted(obs.items())}
digest = hashlib.sha256(canonical(payload).encode("utf-8")).hexdigest()

print(f"observations : {len(payload)}")
print(f"digest       : {digest}")

if BASELINE_DIGEST == "__RECORD_IN_CI_ON_UNSPLIT_CODE__":
    print()
    print("BASELINE NOT YET PINNED. Record this digest into BASELINE_DIGEST, in the "
          "same commit, BEFORE the providers.py split.")
    raise SystemExit(0)

if digest != BASELINE_DIGEST:
    print()
    print("=" * 60)
    print("PROVIDERS EQUIVALENCE: FAIL — behaviour changed")
    print(f"expected {BASELINE_DIGEST}")
    print(f"got      {digest}")
    print("This is a HARD STOP. The split is NOT behaviour-preserving.")
    print("=" * 60)
    raise SystemExit(1)

print()
print("=" * 60)
print(f"PROVIDERS EQUIVALENCE: PASS ({len(payload)} observations)")
print("deterministic provider surface unchanged")
print("NOTE: necessary, not sufficient. Live transport, real fallback chains and")
print("      snapshot() assembly are proven only by the full CI provider suite.")
print("=" * 60)
