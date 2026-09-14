"""Fail-closed adapter for the exact verified SRB_V1_1_FINAL artifact.

This module is intentionally outside the CLEAR NASDAQ backend scientific
fingerprint and prediction path. It does not reimplement SRB. It only verifies
that an externally supplied SRB payload is byte-identical to the internally
verified artifact before any shadow/research use is allowed.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Dict

INTEGRATION_ID = "SRB_V1_1_SHADOW_INTEGRATION_V1"
SRB_VERSION = "SRB_V1_1_FINAL"
MODE = "SHADOW_RESEARCH_ONLY"
PRODUCTION_INFLUENCE = False
DEPLOYMENT_AUTHORIZED = False
PREDICTIVE_EDGE_CLAIMED = False
SUPERINTELLIGENCE_CLAIMED = False

EXPECTED_SOURCE_GENERATOR_SHA256 = (
    "e1303368e18c8b408c01866ff361fbecafb2fc83b480b496d949652684f2e61e"
)
EXPECTED_MANIFEST_SHA256 = (
    "d95420913c5a3401c40abf1c5da6e59451baab3f36727735ea5ada4263c00982"
)
EXPECTED_FINAL_ZIP_SHA256 = (
    "08045c3a630f50656d47f42021b27036e4250e77488e2e0df2a4d2129371474d"
)
EXPECTED_INDEPENDENT_HANDOFF_ZIP_SHA256 = (
    "5f3317efc40782959d6c8cf0d38960454c46cbc99c4776ee278de85833d6546f"
)

VENDOR_DIR = Path(__file__).resolve().parent / "vendor"
SOURCE_PATH = VENDOR_DIR / "SRB_V1_1_BUILD_SOURCE.py"
MANIFEST_PATH = VENDOR_DIR / "SRB_V1_1_FINAL_MANIFEST.json"
FINAL_ZIP_PATH = VENDOR_DIR / "SUPER_REASONING_BRAIN_V1_1_FINAL.zip"


class SRBPayloadError(RuntimeError):
    """Raised when the exact verified SRB payload is absent or mismatched."""


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def verify_payload(vendor_dir: Path | None = None) -> Dict[str, Any]:
    """Verify exact SRB V1.1 payload identity; never infer readiness.

    The final ZIP/source are intentionally not reconstructed from reports or
    manifests. Missing bytes are a hard NOT_READY state.
    """
    root = Path(vendor_dir) if vendor_dir is not None else VENDOR_DIR
    source = root / SOURCE_PATH.name
    manifest = root / MANIFEST_PATH.name
    final_zip = root / FINAL_ZIP_PATH.name

    required = {
        "source": (source, EXPECTED_SOURCE_GENERATOR_SHA256),
        "manifest": (manifest, EXPECTED_MANIFEST_SHA256),
        "final_zip": (final_zip, EXPECTED_FINAL_ZIP_SHA256),
    }

    checks: Dict[str, Any] = {}
    ready = True
    for label, (path, expected) in required.items():
        if not path.is_file():
            checks[label] = {
                "present": False,
                "expected_sha256": expected,
                "actual_sha256": None,
                "match": False,
            }
            ready = False
            continue
        actual = _sha256(path)
        match = actual == expected
        checks[label] = {
            "present": True,
            "expected_sha256": expected,
            "actual_sha256": actual,
            "match": match,
        }
        ready = ready and match

    return {
        "integration_id": INTEGRATION_ID,
        "srb_version": SRB_VERSION,
        "mode": MODE,
        "shadow_ready": bool(ready),
        "production_influence": PRODUCTION_INFLUENCE,
        "deployment_authorized": DEPLOYMENT_AUTHORIZED,
        "predictive_edge_claimed": PREDICTIVE_EDGE_CLAIMED,
        "superintelligence_claimed": SUPERINTELLIGENCE_CLAIMED,
        "checks": checks,
    }


def assert_shadow_ready(vendor_dir: Path | None = None) -> Dict[str, Any]:
    status = verify_payload(vendor_dir)
    if not status["shadow_ready"]:
        raise SRBPayloadError(
            "SRB_V1_1_FINAL exact verified payload is missing or hash-mismatched; "
            "shadow execution is blocked."
        )
    return status
