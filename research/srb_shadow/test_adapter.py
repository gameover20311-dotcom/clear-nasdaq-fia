import tempfile
import unittest
from pathlib import Path

from research.srb_shadow.adapter import (
    DEPLOYMENT_AUTHORIZED,
    PREDICTIVE_EDGE_CLAIMED,
    PRODUCTION_INFLUENCE,
    SUPERINTELLIGENCE_CLAIMED,
    SRBPayloadError,
    assert_shadow_ready,
    verify_payload,
)


class SRBShadowBoundaryTests(unittest.TestCase):
    def test_production_influence_is_false(self):
        self.assertFalse(PRODUCTION_INFLUENCE)
        self.assertFalse(DEPLOYMENT_AUTHORIZED)
        self.assertFalse(PREDICTIVE_EDGE_CLAIMED)
        self.assertFalse(SUPERINTELLIGENCE_CLAIMED)

    def test_missing_payload_fails_closed(self):
        with tempfile.TemporaryDirectory() as td:
            status = verify_payload(Path(td))
            self.assertFalse(status["shadow_ready"])
            self.assertTrue(all(not x["match"] for x in status["checks"].values()))
            with self.assertRaises(SRBPayloadError):
                assert_shadow_ready(Path(td))

    def test_wrong_payload_fails_closed(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "SRB_V1_1_BUILD_SOURCE.py").write_text("wrong", encoding="utf-8")
            (root / "SRB_V1_1_FINAL_MANIFEST.json").write_text("{}", encoding="utf-8")
            (root / "SUPER_REASONING_BRAIN_V1_1_FINAL.zip").write_bytes(b"wrong")
            status = verify_payload(root)
            self.assertFalse(status["shadow_ready"])
            self.assertTrue(all(x["present"] for x in status["checks"].values()))
            self.assertTrue(all(not x["match"] for x in status["checks"].values()))

    def test_no_report_only_reconstruction(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "SRB_V1_1_FINAL_FORENSIC_REPORT.md").write_text(
                "SRB_V1_1_IMPLEMENTATION = PASS", encoding="utf-8"
            )
            self.assertFalse(verify_payload(root)["shadow_ready"])


if __name__ == "__main__":
    unittest.main()
