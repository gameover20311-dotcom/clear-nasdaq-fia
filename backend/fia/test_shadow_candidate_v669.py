"""SHADOW CANDIDATE C1 — fairness and isolation contract.

The candidate exists to be BEATEN or to WIN on unseen rows. This suite does not
test whether it forecasts well (nothing can, at n=0). It pins the properties
that make the eventual comparison FAIR, and the isolation that keeps it out of
production.
"""
from __future__ import annotations

import inspect
import json
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from fia import shadow_candidate as C                                # noqa: E402

FAILURES = []


def check(name, cond, detail=""):
    if cond:
        print("  PASS  %s" % name)
    else:
        print("  FAIL  %s   %s" % (name, detail))
        FAILURES.append(name)


LIVE_8H = [
    {"name": "Semiconductors", "score": 0.656471, "effective_weight": 0.12},
    {"name": "Mega-cap leadership", "score": -0.311034, "effective_weight": 0.22},
    {"name": "US10Y", "score": -0.5, "effective_weight": 0.0875},
    {"name": "NQ structure", "score": 0.161039, "effective_weight": 0.19},
    {"name": "SPX confirmation", "score": -0.19015, "effective_weight": 0.1},
]


def base_prob(pkt):
    num = sum(d["score"] * d["effective_weight"] for d in pkt)
    den = sum(abs(d["effective_weight"]) for d in pkt)
    return round(50.0 + 25.0 * max(-1.0, min(1.0, num / den)), 3)


print("\n[A] THE CANDIDATE CANNOT RECEIVE DIFFERENT INFORMATION THAN BASE")
src = inspect.getsource(C.score_from_packet)
check("[A1] it reads a stored driver packet, it does not gather evidence",
      "drivers" in inspect.signature(C.score_from_packet).parameters)
for forbidden in ("requests", "httpx", "yfinance", "ProviderHub", "datetime.now",
                  "fetch", "urlopen"):
    check("[A2] no live access: %s" % forbidden, forbidden not in src)
mod = Path(C.__file__).read_text()
imports = [l.strip() for l in mod.splitlines() if l.strip().startswith(("import ", "from "))]
check("[A3] the module imports nothing that could fetch data",
      all("typing" in i or "__future__" in i for i in imports), str(imports))
check("[A4] it is a pure function of its argument",
      C.score_from_packet(LIVE_8H) == C.score_from_packet(LIVE_8H))

print("\n[B] IT CHANGES WEIGHTING ONLY, NOT THE PROBABILITY MAPPING")
r = C.score_from_packet(LIVE_8H)
# weighted_score is stored rounded to 6dp and bull to 3dp, so compare within
# the rounding, not to float equality.
check("[B1] same 50 + 25*score mapping BASE uses",
      abs(r["bullish_probability"] - (50.0 + 25.0 * r["weighted_score"])) < 1e-3,
      "%s vs %s" % (r["bullish_probability"], 50.0 + 25.0 * r["weighted_score"]))
check("[B2] probabilities sum to 100",
      abs(r["bullish_probability"] + r["bearish_probability"] - 100.0) < 1e-6)
check("[B3] score stays clamped to [-1, 1]", -1.0 <= r["weighted_score"] <= 1.0)
check("[B4] it produces a genuinely different answer than BASE",
      abs(r["bullish_probability"] - base_prob(LIVE_8H)) > 0.5,
      "BASE %.3f vs C1 %.3f" % (base_prob(LIVE_8H), r["bullish_probability"]))

print("\n[C] THE SHRINKAGE IS THE MEASURED ONE, NOT A GUESS")
check("[C1] lambda = measured effective / nominal",
      abs(C.EQUITY_LAMBDA - (1.32 / 5)) < 1e-9, str(C.EQUITY_LAMBDA))
check("[C2] the measurement provenance is recorded",
      C.MEASUREMENT["rows"] == 261 and "inverse-Herfindahl" in C.MEASUREMENT["method"])
check("[C3] the matrix is FROZEN (re-estimating after losses = fitting the test set)",
      C.MEASUREMENT["frozen"] is True)
check("[C4] only equity-family drivers are shrunk",
      all(C.cluster_lambda(n) == C.EQUITY_LAMBDA for n in C.EQUITY_CLUSTER)
      and all(C.cluster_lambda(n) == 1.0 for n in ("US10Y", "DXY", "News",
                                                   "Macro calendar", "Earnings/guidance")))
check("[C5] the equity cluster is the five measured drivers",
      len(C.EQUITY_CLUSTER) == 5 and "Semiconductors" in C.EQUITY_CLUSTER)

print("\n[D] IT ABSTAINS WHERE EVIDENCE IS ABSENT (no fabricated direction)")
check("[D1] empty packet -> None", C.score_from_packet([]) is None)
check("[D2] None packet -> None", C.score_from_packet(None) is None)
check("[D3] all-zero-weight packet -> None",
      C.score_from_packet([{"name": "US10Y", "score": 1.0, "effective_weight": 0.0}]) is None)
check("[D4] unparseable rows are skipped, not guessed",
      C.score_from_packet([{"name": "X", "score": "n/a", "effective_weight": 1.0}]) is None)

print("\n[E] EFFECTIVE EVIDENCE COUNTING IS HONEST")
check("[E1] five equity drivers count as ~1.32, not 5",
      abs(C.effective_evidence_count(list(C.EQUITY_CLUSTER)) - 1.32) < 0.01,
      str(C.effective_evidence_count(list(C.EQUITY_CLUSTER))))
check("[E2] one equity driver alone is still one real signal",
      C.effective_evidence_count(["NQ structure"]) == 1.0)
check("[E3] independent inputs each count fully",
      C.effective_evidence_count(["US10Y", "DXY"]) == 2.0)
check("[E4] mixed packet adds them",
      abs(C.effective_evidence_count(list(C.EQUITY_CLUSTER) + ["US10Y", "DXY"]) - 3.32) < 0.01,
      str(C.effective_evidence_count(list(C.EQUITY_CLUSTER) + ["US10Y", "DXY"])))
check("[E5] effective count never exceeds nominal",
      C.effective_evidence_count(["NQ structure", "SPX confirmation"]) <= 2.0)

print("\n[F] PRODUCTION IS UNTOUCHED")
check("[F1] every result declares zero production influence",
      r["production_influence"] is False)
# forward_oos has a PRE-EXISTING `shadow_candidate` parameter used by the seal
# policy; that name is unrelated. What matters is that no production module
# IMPORTS this candidate.
for m in ("premove_watch", "engine", "forward_oos", "dashboard_api"):
    txt = (BACKEND / "fia" / ("%s.py" % m)).read_text()
    imports = [l.strip() for l in txt.splitlines()
               if l.strip().startswith(("import ", "from ")) and "shadow_candidate" in l]
    check("[F2] %s does not import the candidate" % m, not imports, str(imports))
check("[F3] failure modes are documented BEFORE any result exists",
      "FAILURE MODES" in mod and "News" in mod and "regime-dependent" in mod)
check("[F4] the falsification rule is fixed in advance",
      "FALSIFICATION" in mod and "bootstrap" in mod and "does not exclude zero" in mod)

print("\n" + "=" * 66)
if FAILURES:
    print("FAILED %d check(s):" % len(FAILURES))
    for f in FAILURES:
        print("   -", f)
    sys.exit(1)
print("ALL SHADOW CANDIDATE C1 CONTRACT CHECKS PASSED")
print("  BASE %.3f  vs  C1 %.3f  on the live 8H packet"
      % (base_prob(LIVE_8H), r["bullish_probability"]))
