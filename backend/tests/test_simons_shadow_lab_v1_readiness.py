import tempfile
import unittest
from pathlib import Path

from simons_shadow_lab_v1.integrity import audit_lab_storage, package_manifest
from simons_shadow_lab_v1.reporting import build_snapshot_report, render_html, render_markdown


def sample_row():
    return {
        "forecast_id": "F1",
        "locked_at_utc": "2026-09-10T13:00:00+00:00",
        "base": {
            "direction": "BULLISH", "confidence": 50.0, "regime": "TREND",
            "h4": {"bullish_probability": 60.0, "bearish_probability": 40.0, "direction": "BULLISH", "confidence": 45.0},
            "h8": {"bullish_probability": 62.0, "bearish_probability": 38.0, "direction": "BULLISH", "confidence": 44.0},
        },
        "outcomes": {},
    }


class ShadowLabReadinessTests(unittest.TestCase):
    def test_reporting_hard_displays_not_proven(self):
        report = build_snapshot_report([sample_row()], "S1")
        self.assertFalse(report["predictive_edge_proven"])
        self.assertFalse(report["profitability_proven"])
        self.assertFalse(report["automatic_strategy_selection"])
        self.assertIn("NOT PROVEN", render_markdown(report))
        self.assertIn("EDGE: NOT PROVEN", render_html(report))

    def test_empty_lab_storage_is_integrity_clean_but_not_edge_proven(self):
        with tempfile.TemporaryDirectory() as td:
            result = audit_lab_storage(Path(td) / "lab", Path(td) / "source")
            self.assertTrue(result["ok"])
            self.assertEqual(result["engineering_readiness"], "PASS")
            self.assertFalse(result["predictive_edge_proven"])
            self.assertFalse(result["profitability_proven"])

    def test_package_manifest_is_deterministic(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); (root / "a.py").write_text("x=1\n", encoding="utf-8"); (root / "b.md").write_text("hello\n", encoding="utf-8")
            a = package_manifest(root); b = package_manifest(root)
            self.assertEqual(a["digest"], b["digest"])
            self.assertEqual(a["file_count"], 2)


if __name__ == "__main__":
    unittest.main()
