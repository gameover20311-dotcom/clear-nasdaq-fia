from __future__ import annotations

import hashlib
import importlib.util
import json
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module


suite = load("fia_suite_contract", "fia_suite.py")
gate = load("fia_gate_contract", "fia_gate.py")


def base_dataset(path, size, digest):
    return {
        "schema": "FIA_EXTERNAL_DATA_REGISTRY_V1",
        "datasets": [{
            "dataset_id": "TEST_DATA",
            "canonical_repo_path": path,
            "expected_size": size,
            "expected_sha256": digest,
            "scope": "HISTORICAL_RESEARCH_ONLY",
            "repository_policy": "INTENTIONALLY_NOT_COMMITTED_LARGE_EXTERNAL_FIXTURE",
            "absence_status": "MISSING_EXTERNAL_DATA",
            "scientific_credit_when_absent": "NONE",
            "predictive_validity_credit_when_absent": False,
            "forward_oos_credit_when_absent": False,
            "required_by": [{
                "entry": "research/check.py",
                "baseline_failure_status": "MISSING_FIXTURE_OR_DATA",
                "required_output_fragment": "canonical data missing"
            }]
        }]
    }


def with_registry(payload, fn):
    old_root = suite.REPO_ROOT
    old_reg = suite.EXTERNAL_DATA_REGISTRY
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        reg = root / ".github" / "registry.json"
        reg.parent.mkdir(parents=True)
        reg.write_text(json.dumps(payload), encoding="utf-8")
        suite.REPO_ROOT = root
        suite.EXTERNAL_DATA_REGISTRY = reg
        try:
            return fn(root)
        finally:
            suite.REPO_ROOT = old_root
            suite.EXTERNAL_DATA_REGISTRY = old_reg


# 1. Exact declared absent dataset can only become NOT_TESTED from exact failure.
def case_missing_exact(root):
    reg = suite.load_external_data_registry()
    assert reg["valid"], reg["errors"]
    status, ev = suite.apply_external_data_contract(
        "research/check.py", "MISSING_FIXTURE_OR_DATA",
        {"reason": "missing"}, "canonical data missing", reg)
    assert status == "MISSING_EXTERNAL_DATA"
    assert ev["scientific_credit"] == "NONE"
    assert ev["predictive_validity_credit"] is False
    assert ev["forward_oos_credit"] is False
    return reg, status, ev

payload = base_dataset("backend/data/canonical.json", 3, hashlib.sha256(b"abc").hexdigest())
reg, status, ev = with_registry(payload, case_missing_exact)

# 2. Arbitrary unregistered missing input is never excused.
status2, _ = suite.apply_external_data_contract(
    "other/check.py", "MISSING_FIXTURE_OR_DATA", {}, "some file missing", reg)
assert status2 == "MISSING_FIXTURE_OR_DATA"

# 3. Wrong failure signature is not reclassified.
status3, _ = suite.apply_external_data_contract(
    "research/check.py", "FAIL", {}, "canonical data missing", reg)
assert status3 == "FAIL"

# 4. A declared required dataset absent while the check reports PASS is fail-open.
status4, ev4 = suite.apply_external_data_contract(
    "research/check.py", "PASS", {}, "", reg)
assert status4 == "FAIL"
assert "passed even though" in ev4["reason"]

# 5. Present wrong bytes are a hard registry/integrity failure.
def case_wrong_bytes(root):
    p = root / "backend/data/canonical.json"
    p.parent.mkdir(parents=True)
    p.write_bytes(b"wrong")
    r = suite.load_external_data_registry()
    assert not r["valid"]
    assert r["datasets"]["TEST_DATA"]["state"] == "PRESENT_IDENTITY_MISMATCH"
    st, _ = suite.apply_external_data_contract(
        "research/check.py", "PASS", {}, "", r)
    assert st == "FAIL"

with_registry(payload, case_wrong_bytes)

# 6. Present exact bytes are verified and no missing-data exemption applies.
def case_exact_bytes(root):
    p = root / "backend/data/canonical.json"
    p.parent.mkdir(parents=True)
    p.write_bytes(b"abc")
    r = suite.load_external_data_registry()
    assert r["valid"], r["errors"]
    assert r["datasets"]["TEST_DATA"]["state"] == "PRESENT_VERIFIED"
    st, _ = suite.apply_external_data_contract(
        "research/check.py", "PASS", {}, "", r)
    assert st == "PASS"

with_registry(payload, case_exact_bytes)

# 7. Gate independently refuses undeclared or credited NOT_TESTED states.
good_suite = {
    "external_data_registry": reg,
    "results": {
        "research/check.py": {"status": "MISSING_EXTERNAL_DATA", "evidence": ev}
    },
}
ok, errors, entries = gate.validate_external_not_tested(good_suite)
assert ok, errors
assert entries == ["research/check.py"]

bad_credit = json.loads(json.dumps(good_suite))
bad_credit["results"]["research/check.py"]["evidence"]["predictive_validity_credit"] = True
ok, errors, _ = gate.validate_external_not_tested(bad_credit)
assert not ok and errors

undeclared = json.loads(json.dumps(good_suite))
undeclared["results"]["other/check.py"] = {
    "status": "MISSING_EXTERNAL_DATA",
    "evidence": {"scientific_credit": "NONE", "predictive_validity_credit": False,
                 "forward_oos_credit": False},
}
ok, errors, _ = gate.validate_external_not_tested(undeclared)
assert not ok and errors

# 8. MISSING_EXTERNAL_DATA is explicitly NOT_TESTED and never a PASS/failing alias.
assert "MISSING_EXTERNAL_DATA" in suite.NOT_TESTED_STATUSES
assert "MISSING_EXTERNAL_DATA" not in suite.FAILING_STATUSES
assert "MISSING_EXTERNAL_DATA" in gate.NOT_TESTED_STATUSES
assert "MISSING_EXTERNAL_DATA" not in gate.FAILING_STATUSES

print("PASS external historical data contract hostile tests")
