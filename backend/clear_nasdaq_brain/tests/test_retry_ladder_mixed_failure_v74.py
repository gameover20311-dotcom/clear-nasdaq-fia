"""V7.4 regression: a contract-recovery retry must not consume the degraded fallback.

REPRODUCED IN A REAL 2h48m / 26-call gpt-oss:20b run. Every stage of the Three-Brain
pipeline completed -- 6 role pipelines, freeze, 4 specialists, causal graph, hypotheses,
both scenario lattices, skeptic, all 3 judges and CHIEF_FIA_4H -- and then the run died
on the very last stage:

    RuntimeError: CHIEF_FIA_8H failed: timeout: timed out
    runtime_events: CHIEF_FIA_8H PROBABILITY_CONTRACT_RETRY

Attempt 1 failed the probability-sum contract. That triggered PROBABILITY_CONTRACT_RETRY,
which re-asks at the SAME effort with the SAME evidence (correctly -- it must not loosen
the validator). Attempt 2 then hit the 900s wall clock, the 2-attempt loop was exhausted,
and 2h48m of completed reasoning was thrown away.

A contract-recovery attempt is not a degradation, so it must not cost the run its one
degraded fallback. The ladder now allows three attempts with the LAST always degrading.
"""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from fia_brain.orchestrator import FIABrain, _is_timeout, _is_probability_contract_error
from fia_brain.local_llm import LocalModelError
from fia_brain.config import validate, DEFAULTS

base = dict(DEFAULTS)
base["shadow_ledger"] = str(ROOT / "data" / "shadow" / "brain_v6.jsonl")
base["calibration_profile"] = str(ROOT / "benchmarks" / "calibration_profile.json")
base["regime_profile"] = str(ROOT / "benchmarks" / "regime_profile.json")
base["failure_memory_ledger"] = str(ROOT / "data" / "memory" / "failure_memory.jsonl")
CFG = validate(base)

GOOD = {"direction": "NO_EDGE", "bullish_probability": 50.0, "bearish_probability": 50.0,
        "confidence": 10.0, "thesis": "t", "evidence_ids": ["E0001"],
        "counter_evidence_ids": [], "unknowns": [], "failure_conditions": []}

# classifiers behave as the ladder expects
assert _is_timeout(LocalModelError("timeout: timed out")) is True
assert _is_probability_contract_error(ValueError("probabilities do not sum to 100")) is True
assert _is_timeout(ValueError("probabilities do not sum to 100")) is False


def run(seq):
    """seq: list of exceptions-or-None; returns (result_or_error, recorded_calls)."""
    calls = []
    b = FIABrain(CFG)
    b._runtime_events = []

    class C:
        def ask_json(self, system, user, **kw):
            i = len(calls)
            calls.append({"effort": kw.get("reasoning_effort"), "chars": len(user)})
            item = seq[i] if i < len(seq) else None
            if isinstance(item, Exception):
                raise item
            return dict(GOOD)
    b.client = C()
    try:
        return b._ask_analysis("CHIEF_FIA_8H", "instr", "E0001 | s | p = 1", {"E0001"},
                               effort="medium"), calls, b._runtime_events
    except Exception as e:
        return e, calls, b._runtime_events


# ---- THE EXACT PRODUCTION SEQUENCE: contract error, then timeout ----
res, calls, events = run([ValueError("probabilities do not sum to 100"),
                          LocalModelError("timeout: timed out"),
                          None])
assert not isinstance(res, Exception), "ladder still dies on contract-then-timeout: %r" % (res,)
assert len(calls) == 3, calls
assert calls[0]["effort"] == "medium"
assert calls[1]["effort"] == "medium", "contract recovery must NOT degrade effort"
assert calls[2]["effort"] == "low", "final attempt must degrade: %r" % (calls,)
kinds = [e.get("event") for e in events]
assert "PROBABILITY_CONTRACT_RETRY" in kinds, kinds
# The third attempt degraded. It is labelled by whatever actually caused it
# (TIMEOUT_RETRY here, FINAL_DEGRADED_FALLBACK when the prior error is not itself
# a degradable class). What matters is that a degradation was recorded and applied.
assert any(k in ("TIMEOUT_RETRY", "OUTPUT_BUDGET_RETRY", "FINAL_DEGRADED_FALLBACK")
           for k in kinds), kinds
degraded = [e for e in events if e.get("to_effort") == "low"]
assert degraded, "no degradation event recorded: %r" % (events,)
assert degraded[-1].get("attempt") == 3, degraded

# ---- a plain timeout still degrades immediately on attempt 2 ----
res, calls, events = run([LocalModelError("timeout: timed out"), None])
assert not isinstance(res, Exception), res
assert calls[1]["effort"] == "low", calls
assert "TIMEOUT_RETRY" in [e.get("event") for e in events]

# ---- output-budget exhaustion still degrades immediately ----
res, calls, events = run([LocalModelError("done_reason=length; content_chars=0"), None])
assert not isinstance(res, Exception), res
assert calls[1]["effort"] == "low", calls
assert "OUTPUT_BUDGET_RETRY" in [e.get("event") for e in events]

# ---- first-attempt success must not retry at all ----
res, calls, _ = run([None])
assert not isinstance(res, Exception) and len(calls) == 1, calls

# ---- genuinely unrecoverable failure still fails closed (no infinite retry) ----
err = LocalModelError("timeout: timed out")
res, calls, _ = run([err, err, err])
assert isinstance(res, RuntimeError), "must still fail closed when every attempt fails"
assert len(calls) == 3, calls
assert "CHIEF_FIA_8H failed" in str(res)

# ---- the validator is never loosened: a bad-probability answer is still rejected ----
BAD = dict(GOOD, bullish_probability=70.0, bearish_probability=70.0)
calls2 = []
b = FIABrain(CFG); b._runtime_events = []
class C2:
    def ask_json(self, system, user, **kw):
        calls2.append(1); return dict(BAD)
b.client = C2()
try:
    b._ask_analysis("CHIEF_FIA_8H", "i", "E0001 | s | p = 1", {"E0001"}, effort="medium")
    raise SystemExit("FAIL: a probability-contract violation was accepted")
except RuntimeError:
    pass
assert len(calls2) == 3, "should exhaust its attempts, then fail closed"

print("PASS test_retry_ladder_mixed_failure_v74")
