from __future__ import annotations

import hashlib
import json
import os
import py_compile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path.cwd()
BACKEND = ROOT / "backend"
BRAIN = BACKEND / "clear_nasdaq_brain"
MANIFEST = BRAIN / "MANIFEST.json"


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


# Refuse to hide any unexpected release-manifest drift.
obj = json.loads(MANIFEST.read_text(encoding="utf-8"))
listed = {x["path"]: x for x in obj["files"]}
mismatches, missing = [], []
for rel, exp in listed.items():
    p = BRAIN / rel
    if not p.is_file():
        missing.append(rel)
        continue
    actual = {"size": p.stat().st_size, "sha256": sha256(p)}
    if actual["size"] != exp["size"] or actual["sha256"] != exp["sha256"]:
        mismatches.append(
            {
                "path": rel,
                "expected_size": exp["size"],
                "actual_size": actual["size"],
                "expected_sha256": exp["sha256"],
                "actual_sha256": actual["sha256"],
            }
        )
expected_drift = {
    "fia_brain/cloud_llm.py",
    "fia_brain/final_three_brain.py",
    "fia_brain/prompts.py",
}
found_drift = {x["path"] for x in mismatches}
assert not missing, missing
assert found_drift == expected_drift, (found_drift, expected_drift, mismatches)
assert obj.get("manifest_revision") == 2, obj.get("manifest_revision")
pre_manifest_sha = sha256(MANIFEST)
pre_manifest_size = MANIFEST.stat().st_size
assert pre_manifest_sha == "564b43d0a116021a10f6380fb325b358fd57b50e7abb63fe7b6408dc1842a093", pre_manifest_sha
assert pre_manifest_size == 32017, pre_manifest_size

# Repair Phase20: use the already-frozen, hash-pinned Polygon archive.
p20 = BACKEND / "fia_backtest_phase20" / "full_backtest.py"
text = p20.read_text(encoding="utf-8")
marker = "def load_polygon_archive_cache():\n    if not POLYGON_CACHE_PATH.exists():"
assert marker in text, "Phase20 loader shape changed; refusing blind patch"
replacement = '''_FROZEN_NEWS = (Path(__file__).resolve().parents[1] / "fia_backtest_frozen"
                / "data" / "polygon_news_minimal_20250901_20260831.jsonl.gz")
_FROZEN_NEWS_MANIFEST = (Path(__file__).resolve().parents[1] / "fia_backtest_frozen"
                         / "FROZEN_NEWS_MANIFEST.json")


def _load_frozen_news():
    if not _FROZEN_NEWS.exists():
        return None
    if not _FROZEN_NEWS_MANIFEST.exists():
        raise RuntimeError("Frozen Polygon archive exists but its manifest is missing")
    import gzip
    import hashlib
    manifest = json.loads(_FROZEN_NEWS_MANIFEST.read_text(encoding="utf-8"))
    actual_gz = hashlib.sha256(_FROZEN_NEWS.read_bytes()).hexdigest()
    expected_gz = str(manifest.get("sha256_gz") or "")
    if actual_gz != expected_gz:
        raise RuntimeError(
            f"Frozen Polygon archive hash mismatch: expected={expected_gz} actual={actual_gz}"
        )
    rows = []
    with gzip.open(_FROZEN_NEWS, "rt", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    expected_records = int(manifest.get("records") or -1)
    if len(rows) != expected_records:
        raise RuntimeError(
            f"Frozen Polygon archive record mismatch: expected={expected_records} actual={len(rows)}"
        )
    if rows:
        first = str(rows[0].get("published_utc") or "")
        last = str(rows[-1].get("published_utc") or "")
        if first != str(manifest.get("coverage_first_published_utc") or ""):
            raise RuntimeError("Frozen Polygon first timestamp disagrees with manifest")
        if last != str(manifest.get("coverage_last_published_utc") or ""):
            raise RuntimeError("Frozen Polygon last timestamp disagrees with manifest")
    return rows, manifest


def load_polygon_archive_cache():
    frozen = _load_frozen_news()
    if frozen is not None:
        rows, manifest = frozen
        return rows, {
            "status": "frozen_minimal_archive_verified",
            "raw": len(rows),
            "path": str(_FROZEN_NEWS),
            "start": manifest.get("coverage_first_published_utc"),
            "end": manifest.get("coverage_last_published_utc"),
            "windows": 0,
            "sha256_gz": manifest.get("sha256_gz"),
        }
    if not POLYGON_CACHE_PATH.exists():'''
text = text.replace(marker, replacement, 1)
p20.write_text(text, encoding="utf-8")
py_compile.compile(str(p20), doraise=True)

# Repair Phase28: verify canonical frozen artifact instead of obsolete raw path.
p28 = BACKEND / "fia_backtest_phase28" / "phase28_integrity_test.py"
text = p28.read_text(encoding="utf-8")
old = 'ok("Polygon one-year news archive present",(ROOT/"fia_backtest_phase20/data/polygon_news_20250901_20260831.json").exists())'
assert old in text, "Phase28 stale Polygon check not found; refusing blind patch"
new = '''frozen_news=ROOT/"fia_backtest_frozen/data/polygon_news_minimal_20250901_20260831.jsonl.gz"
frozen_manifest_path=ROOT/"fia_backtest_frozen/FROZEN_NEWS_MANIFEST.json"
ok("Frozen Polygon archive present",frozen_news.exists())
ok("Frozen Polygon manifest present",frozen_manifest_path.exists())
frozen_manifest=json.loads(frozen_manifest_path.read_text(encoding="utf-8"))
ok("Frozen Polygon gzip hash pinned",sha(frozen_news)==frozen_manifest.get("sha256_gz"))
ok("Frozen Polygon record count pinned",int(frozen_manifest.get("records") or 0)==64851)
ok("Frozen Polygon source count preserved",int(frozen_manifest.get("source_articles") or 0)==64851)'''
text = text.replace(old, new, 1)
p28.write_text(text, encoding="utf-8")
py_compile.compile(str(p28), doraise=True)

# Repair stale L9 regression. Current hosted-safe runtime sends an exact
# citation-complete judge view and fails closed on truncation/unresolvable ids.
l9 = BRAIN / "tests" / "test_l9_validator_evidence_window_v74.py"
text = l9.read_text(encoding="utf-8")
old_block = '''# --- the Three-Brain flow must actually use it for BOTH validators ---
src = (ROOT / "fia_brain/final_three_brain.py").read_text(encoding="utf-8")
assert "validator_evidence_view(compact,judge_input,ledger)" in src, "judges not widened"
assert "validator_evidence_view(compact,skeptic_advisory,ledger)" in src, "skeptic not widened"
assert 'brain._ask_judge(judge_view["view"]' in src, "judges still receive the narrow view"
assert 'prompts.SKEPTIC,skeptic_view["view"]' in src, "skeptic still receives the narrow view"
assert "validator_evidence_window" in src, "coverage evidence not surfaced in passes"
'''
assert old_block in text, "L9 regression shape changed; refusing blind rewrite"
new_block = '''# --- hosted-ceiling path: exact cited subset is valid only if citation-complete ---
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
'''
text = text.replace(old_block, new_block, 1)
l9.write_text(text, encoding="utf-8")
py_compile.compile(str(l9), doraise=True)

# Attack the repaired test itself against the real runtime shape.
flow = (BRAIN / "fia_brain" / "final_three_brain.py").read_text(encoding="utf-8")
norm = "".join(flow.split())
assert 'judge_view=validator_evidence_view("",judge_input,ledger,max_appendix_chars=24000)' in norm
assert 'if(notjudge_view.get("coverage_complete"))orjudge_view.get("unresolvable_ids"):' in norm
assert 'brain._ask_judge(judge_view["view"]' in norm
assert 'brain._ask_judge(compact' not in norm

# Preserve stale r2 instead of rewriting history, and issue r3 for exact bytes.
release_test = BRAIN / "tests" / "test_release_manifest_v661.py"
text = release_test.read_text(encoding="utf-8")
assert "assert obj['manifest_revision'] == 2" in text
text = text.replace(
    "assert obj['manifest_revision'] == 2, obj.get('manifest_revision')",
    "assert obj['manifest_revision'] == 3, obj.get('manifest_revision')",
    1,
)
anchor = "assert r1['superseded_by_commit']\n"
assert anchor in text
r2_block = '''
# Revision 2 later became stale after real hosted-runtime hardening changed
# three shipped brain files. Keep that failure visible rather than rewriting history.
r2 = [h for h in history if h['revision'] == 2]
assert len(r2) == 1, 'revision 2 must be recorded exactly once'
r2 = r2[0]
assert r2['status'] == 'SUPERSEDED_STALE_AFTER_RUNTIME_HARDENING', r2['status']
assert r2['manifest_sha256'] == (
    '564b43d0a116021a10f6380fb325b358fd57b50e7abb63fe7b6408dc1842a093'), r2['manifest_sha256']
assert r2['manifest_size'] == 32017, r2['manifest_size']
assert {e['path'] for e in r2['entries_misdescribed']} == {
    'fia_brain/cloud_llm.py', 'fia_brain/final_three_brain.py', 'fia_brain/prompts.py'
}
assert r2['correction_reason']
assert r2['superseded_at_utc']
assert len(r2['superseded_by_commit']) == 40
assert all(c in '0123456789abcdef' for c in r2['superseded_by_commit'])
'''
text = text.replace(anchor, anchor + r2_block, 1)
text = text.replace(
    "print('PASS test_release_manifest_v661 (manifest r2, r1 recorded as superseded)')",
    "print('PASS test_release_manifest_v661 (manifest r3; r1+r2 preserved as superseded)')",
    1,
)
release_test.write_text(text, encoding="utf-8")
py_compile.compile(str(release_test), doraise=True)

obj = json.loads(MANIFEST.read_text(encoding="utf-8"))
history = obj["manifest_revision_history"]
assert [h["revision"] for h in history] == [1], history
history.append(
    {
        "revision": 2,
        "status": "SUPERSEDED_STALE_AFTER_RUNTIME_HARDENING",
        "manifest_sha256": pre_manifest_sha,
        "manifest_size": pre_manifest_size,
        "observed_at_commit": os.environ.get("SOURCE_COMMIT"),
        "correction_reason": (
            "Revision 2 became stale after hosted GPT-OSS runtime hardening changed "
            "cloud_llm.py, final_three_brain.py and prompts.py. Revision 3 also records "
            "the bounded L9 regression correction for citation-complete judge grounding. "
            "No Forward-OOS seal, protected scientific artifact, historical outcome or prediction is rewritten."
        ),
        "entries_misdescribed": mismatches,
        "entries_changed_by_this_correction": [
            "tests/test_release_manifest_v661.py",
            "tests/test_l9_validator_evidence_window_v74.py",
        ],
        "superseded_at_utc": datetime.now(timezone.utc).isoformat(),
        "superseded_by_commit": "PENDING_REPAIR_PAYLOAD_COMMIT",
    }
)
obj["manifest_revision"] = 3
obj["manifest_revision_note"] = (
    "Release version unchanged. Revision 3 refreshes engineering release metadata after "
    "hosted-runtime hardening and records the bounded L9 regression correction; r1/r2 remain preserved."
)

file_entries = {x["path"]: x for x in obj["files"]}
update_paths = [
    "fia_brain/cloud_llm.py",
    "fia_brain/final_three_brain.py",
    "fia_brain/prompts.py",
    "tests/test_release_manifest_v661.py",
    "tests/test_l9_validator_evidence_window_v74.py",
]
for rel in update_paths:
    q = BRAIN / rel
    assert q.is_file(), rel
    assert rel in file_entries, rel
    file_entries[rel]["size"] = q.stat().st_size
    file_entries[rel]["sha256"] = sha256(q)
MANIFEST.write_text(json.dumps(obj, indent=1, ensure_ascii=True) + "\n", encoding="utf-8")

# Independent local manifest consistency check.
obj2 = json.loads(MANIFEST.read_text(encoding="utf-8"))
bad_entries = []
for rel, exp in {x["path"]: x for x in obj2["files"]}.items():
    q = BRAIN / rel
    if not q.is_file() or q.stat().st_size != exp["size"] or sha256(q) != exp["sha256"]:
        bad_entries.append(rel)
assert not bad_entries, bad_entries

# Frozen archive identity must remain exact.
frozen = BACKEND / "fia_backtest_frozen/data/polygon_news_minimal_20250901_20260831.jsonl.gz"
fm = json.loads((BACKEND / "fia_backtest_frozen/FROZEN_NEWS_MANIFEST.json").read_text())
assert sha256(frozen) == fm["sha256_gz"] == "bf62059fb75f768f1b15061a1fb1f2110635d0d62ebb8cad38c86dfc4327a295"
assert fm["records"] == fm["source_articles"] == 64851

print("FINAL_REPAIR_V3_PATCH_STAGE=PASS")
print("FROZEN_NEWS_SHA256_GZ=", sha256(frozen))
