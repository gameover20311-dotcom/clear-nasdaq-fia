"""V7.4 regression: real NQ liquidity levels must not be reported as a MISSING source.

BEFORE: providers.snapshot() set liquidity_evidence_available ONLY on the exception
path. On success it was never set, and the only other writer
(forexcom_chart_liquidity.apply_forexcom_chart_liquidity) is dead code that main.py
never calls. provider_reliability.build_provider_health() therefore read a flag nobody
set and reported liquidity MISSING while nq_liquidity carried 14/14 priced levels from
an EXPLICIT_CONTRACT source (NQU6). Observed live: overall score 66.7 with
missing_sources ['macro','earnings','liquidity'].
"""
import sys
from pathlib import Path
BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
from fia.provider_reliability import _source_item

SRC = (BACKEND / "fia/providers.py").read_text(encoding="utf-8")

# the success path must set the flag
assert 'data["liquidity_evidence_available"] = _available' in SRC, \
    "success path still does not set liquidity_evidence_available"
assert "_quality in {\"EXPLICIT_CONTRACT\", \"CONTINUOUS_FALLBACK\"}" in SRC, \
    "availability must be derived from real source quality"

# honesty: a continuous-contract fallback must be disclosed as a proxy
assert '"is_proxy": _quality == "CONTINUOUS_FALLBACK"' in SRC, "proxy state not disclosed"
assert '"continuous_fallback_proxy"' in SRC


def evaluate(nq):
    """Mirror of the production predicate."""
    levels = nq.get("levels") or {}
    priced = sum(1 for v in levels.values() if v is not None)
    q = str(nq.get("source_quality") or "").upper()
    return bool(priced) and q in {"EXPLICIT_CONTRACT", "CONTINUOUS_FALLBACK"}, priced, q


full = {"symbol": "NQU6", "source_quality": "EXPLICIT_CONTRACT",
        "levels": {f"l{i}": 100.0 + i for i in range(14)}}
avail, priced, q = evaluate(full)
assert avail is True and priced == 14 and q == "EXPLICIT_CONTRACT"

fallback = dict(full, source_quality="CONTINUOUS_FALLBACK")
avail, _, _ = evaluate(fallback)
assert avail is True, "a continuous-contract fallback is still evidence (disclosed as proxy)"

missing_q = dict(full, source_quality="MISSING")
assert evaluate(missing_q)[0] is False, "MISSING source quality must not count as available"

no_levels = {"symbol": "NQU6", "source_quality": "EXPLICIT_CONTRACT", "levels": {}}
assert evaluate(no_levels)[0] is False, "zero priced levels must not count as available"

unpriced = {"symbol": "NQU6", "source_quality": "EXPLICIT_CONTRACT",
            "levels": {f"l{i}": None for i in range(14)}}
assert evaluate(unpriced)[0] is False, "all-None levels must not count as available"

# and the health item renders honestly in both directions
item = _source_item(available=True, source="NQ chart liquidity", freshness="request_live")
assert item["available"] is True and item["status"] == "live"
item = _source_item(available=False, source="NQ chart liquidity", freshness="missing")
assert item["available"] is False and item["status"] == "missing"

print("PASS test_liquidity_evidence_flag_v74")
