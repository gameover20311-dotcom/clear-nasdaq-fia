"""L-9 regression: a validator's evidence window must be a SUPERSET of every
citation it is asked to validate.

REPRODUCED IN A REAL RUN (3h14m, 27 gpt-oss:20b calls): all three judges raised
  judge1: "Unsupported evidence IDs"
  judge2: "Unsupported evidence references (e.g., E0091, E0090, etc.)"
  judge3: "Unsupported evidence references: ... not present in the supplied evidence set."
and the tribunal refused to publish. Those ids were NOT hallucinated. Specialists read
domain_text(ledger, domain, max_records=N) -- a wider view of the same ledger -- while
judges saw only the fact-card `compact` view. Correct citations therefore looked
unsupported, biasing the system toward spurious abstention.
"""
from pathlib import Path
import sys, json

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from fia_brain.evidence_intelligence import (
    validator_evidence_view, referenced_evidence_ids,
)
from fia_brain.util import sha256_obj


def ledger_of(n):
    recs = []
    for i in range(1, n + 1):
        body = {"source": "/api/dashboard", "path": f"live.snapshot.data.f{i}", "value": float(i)}
        r = dict(body); r["record_hash"] = sha256_obj(body); r["evidence_id"] = "E%04d" % i
        recs.append(r)
    L = {"snapshot_sha256": "S", "record_count": len(recs), "records": recs}
    L["ledger_sha256"] = sha256_obj({k: v for k, v in L.items()})
    return L


LED = ledger_of(120)
# The narrow fact-card view a judge used to receive.
COMPACT = "\n".join("E%04d | /api/dashboard | live.snapshot.data.f%d = %d" % (i, i, i)
                    for i in range(1, 25))

# Material under review cites ids from the WIDER specialist window plus one fake id.
MATERIAL = {
    "specialists": {"macro_rates": {"evidence_ids": ["E0089", "E0090", "E0091"]},
                    "tech_leadership": {"evidence_ids": ["E0120", "E0007"]}},
    "consensus": {"evidence_ids": ["E0003"]},
    "hallucinated": {"evidence_ids": ["E9999"]},
}

# --- id extraction ---
refs = referenced_evidence_ids(MATERIAL)
assert {"E0089", "E0090", "E0091", "E0120", "E0007", "E0003", "E9999"} <= refs, refs

# --- BEFORE: the narrow view does not cover the cited ids ---
for eid in ("E0089", "E0090", "E0091", "E0120"):
    assert eid not in COMPACT, "precondition: %s must be outside the narrow view" % eid

# --- AFTER: the validator view covers every REAL cited id ---
res = validator_evidence_view(COMPACT, MATERIAL, LED)
view = res["view"]
for eid in ("E0089", "E0090", "E0091", "E0120"):
    assert eid in view, "L-9 NOT FIXED: %s still invisible to the validator" % eid
    assert ("live.snapshot.data.f%d" % int(eid[1:])) in view, eid
# ids already visible are not duplicated into the appendix
assert res["already_visible"] >= 2, res
assert res["appended_ids"] == 4, res

# --- a genuinely fake id must remain flagged as unsupported ---
assert "E9999" in res["unresolvable_ids"], res
assert "UNRESOLVED CITED IDS" in view
assert "E9999" not in view.split("UNRESOLVED CITED IDS")[0].split("CITED-EVIDENCE APPENDIX")[-1], \
    "a hallucinated id must never be resolved as real evidence"

# --- the appendix must never fabricate evidence ---
for line in view.split("CITED-EVIDENCE APPENDIX")[-1].splitlines():
    if "|" not in line: continue
    eid = line.split("|")[0].strip()
    if not eid.startswith("E"): continue
    rec = next(r for r in LED["records"] if r["evidence_id"] == eid)
    assert rec["path"] in line, "appendix line must render the REAL ledger record"

# --- no silent truncation: capping is reported ---
small = validator_evidence_view(COMPACT, MATERIAL, LED, max_appendix_chars=40)
assert small["appendix_truncated_ids"], small
assert small["coverage_complete"] is False, small
assert res["coverage_complete"] is True, res

# --- base view unchanged when nothing extra is cited ---
none_extra = validator_evidence_view(COMPACT, {"evidence_ids": ["E0003"]}, LED)
assert none_extra["appended_ids"] == 0
assert none_extra["view"] == COMPACT

# --- hosted-ceiling path: exact cited subset is valid only if citation-complete ---
REAL_MATERIAL = {k: v for k, v in MATERIAL.items() if k != "hallucinated"}
exact = validator_evidence_view("", REAL_MATERIAL, LED, max_appendix_chars=24000)
assert exact["already_visible"] == 0, exact
assert exact["appended_ids"] == 6, exact
assert exact["coverage_complete"] is True, exact
assert exact["unresolvable_ids"] == [], exact
for eid in ("E0089", "E0090", "E0091", "E0120", "E0007", "E0003"):
    assert eid in exact["view"], (eid, exact)

bad = validator_evidence_view("", MATERIAL, LED, max_appendix_chars=24000)
assert bad["unresolvable_ids"] == ["E9999"], bad

tiny = validator_evidence_view("", REAL_MATERIAL, LED, max_appendix_chars=40)
assert tiny["coverage_complete"] is False and tiny["appendix_truncated_ids"], tiny

src = (ROOT / "fia_brain/final_three_brain.py").read_text(encoding="utf-8")
normalized = "".join(src.split())
assert 'skeptic_view=validator_evidence_view(compact,skeptic_advisory,ledger)' in normalized, "skeptic not widened"
assert 'judge_view=validator_evidence_view("",judge_input,ledger,max_appendix_chars=24000)' in normalized, "judge citation-complete view missing"
assert 'if(notjudge_view.get("coverage_complete"))orjudge_view.get("unresolvable_ids"):' in normalized, "judge window does not fail closed"
assert 'brain._ask_judge(judge_view["view"]' in normalized, "judges do not receive verified cited evidence"
assert 'prompts.SKEPTIC,skeptic_view["view"]' in normalized, "skeptic still receives the narrow view"
assert 'brain._ask_judge(compact' not in normalized, "judge bypasses verified evidence view"
assert "validator_evidence_window" in src, "coverage evidence not surfaced in passes"

print("PASS test_l9_validator_evidence_window_v74")
