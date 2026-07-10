import unittest

from app.map_utils import filter_map_reports, limit_recent_records


class MapUtilsTests(unittest.TestCase):
    def test_filter_map_reports_matches_location_and_pest(self):
        reports = [
            {"barangay": "San Rafael", "municipality": "San Pablo", "province": "Laguna", "pest_type": "Rhinoceros Beetle"},
            {"barangay": "Bautista", "municipality": "Calauan", "province": "Laguna", "pest_type": "Brontispa"},
            {"barangay": "Lumbangan", "municipality": "San Pablo", "province": "Laguna", "pest_type": "Unknown Pest"},
        ]

        filtered = filter_map_reports(reports, search_query="san pablo")

        self.assertEqual(len(filtered), 2)
        self.assertEqual(filtered[0]["barangay"], "San Rafael")
        self.assertEqual(filtered[1]["barangay"], "Lumbangan")

    def test_limit_recent_records_returns_only_five_entries(self):
        reports = [{"id": i} for i in range(1, 8)]

        limited = limit_recent_records(reports, 5)

        self.assertEqual(len(limited), 5)
        self.assertEqual([item["id"] for item in limited], [1, 2, 3, 4, 5])
