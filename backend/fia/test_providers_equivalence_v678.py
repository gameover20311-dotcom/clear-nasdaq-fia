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

# Recorded from unsplit providers.py IN CI, before the split. Never regenerated
# to match a new result: a changed digest means changed behaviour.
BASELINE_DIGEST = "__RECORD_IN_CI_ON_UNSPLIT_CODE__"

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
safe("calculate_source_confirmation_score", hub.calculate_source_confirmation_score, list(ARTICLES))
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
safe("_latest_candle_start", ProviderHub._latest_candle_start, hub, "60")


def canonical(value):
    return json.dumps(value, sort_keys=True, default=str, separators=(",", ":"))


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
