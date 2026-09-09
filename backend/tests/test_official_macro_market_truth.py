import unittest
from datetime import datetime, timezone

from fia.official_macro_fallback import parse_bea_schedule, parse_bls_ics


class OfficialMacroFallbackTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 9, 9, 17, 0, tzinfo=timezone.utc)

    def test_bls_ics_cpi_and_employment_are_timestamped_in_et(self):
        fixture = """BEGIN:VCALENDAR
BEGIN:VEVENT
DTSTART;TZID=America/New_York:20260911T083000
SUMMARY:Consumer Price Index
END:VEVENT
BEGIN:VEVENT
DTSTART;TZID=America/New_York:20261002T083000
SUMMARY:The Employment Situation
END:VEVENT
BEGIN:VEVENT
DTSTART;TZID=America/New_York:20260912T100000
SUMMARY:Unrelated Release
END:VEVENT
END:VCALENDAR
"""
        events = parse_bls_ics(fixture, now=self.now)
        self.assertEqual([e["type"] for e in events], ["CPI", "EMPLOYMENT_SITUATION"])
        # September is EDT, therefore 08:30 ET == 12:30 UTC.
        self.assertEqual(events[0]["time_utc"], "2026-09-11T12:30:00+00:00")
        self.assertTrue(all(e["directional_score_available"] is False for e in events))
        self.assertTrue(all(e["actual"] is None and e["expected"] is None for e in events))

    def test_bea_schedule_extracts_gdp_and_pce_only(self):
        fixture = """
        <table><tbody>
          <tr><td>September 30 8:30 AM</td><td>News</td><td>GDP (Third Estimate), 2nd Quarter 2026</td><td>View</td></tr>
          <tr><td>September 30 8:30 AM</td><td>News</td><td>Personal Income and Outlays, August 2026</td><td>View</td></tr>
          <tr><td>October 6 10:00 AM</td><td>Data</td><td>Services Supplied Through Affiliates, 2024</td></tr>
        </tbody></table>
        """
        events = parse_bea_schedule(fixture, now=self.now)
        self.assertEqual([e["type"] for e in events], ["GDP", "PCE"])
        self.assertEqual(events[0]["time_utc"], "2026-09-30T12:30:00+00:00")
        self.assertTrue(all(e["directional_score_available"] is False for e in events))

    def test_official_calendar_never_fabricates_consensus_or_direction(self):
        fixture = """BEGIN:VCALENDAR
BEGIN:VEVENT
DTSTART;TZID=America/New_York:20260911T083000
SUMMARY:Consumer Price Index
END:VEVENT
END:VCALENDAR
"""
        event = parse_bls_ics(fixture, now=self.now)[0]
        self.assertIsNone(event["actual"])
        self.assertIsNone(event["expected"])
        self.assertFalse(event["directional_score_available"])


if __name__ == "__main__":
    unittest.main()
