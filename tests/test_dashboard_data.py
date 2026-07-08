import unittest

from app.dashboard_data import build_dashboard_chart_payload


class DashboardDataTests(unittest.TestCase):
    def test_build_dashboard_chart_payload_returns_empty_state_for_no_reports(self):
        payload = build_dashboard_chart_payload([])

        self.assertEqual(payload["trend_labels"], ["No data"])
        self.assertEqual(payload["distribution_labels"], ["No reports yet"])
        self.assertEqual(payload["distribution_data"], [0])

    def test_build_dashboard_chart_payload_uses_real_report_data(self):
        reports = [
            {"created_at": "2026-01-01T10:00:00Z", "pest_type": "Rhinoceros Beetle"},
            {"created_at": "2026-02-01T10:00:00Z", "pest_type": "Rhinoceros Beetle"},
            {"created_at": "2026-02-15T10:00:00Z", "pest_type": "Brontispa"},
        ]

        payload = build_dashboard_chart_payload(reports)

        self.assertEqual(payload["trend_labels"], ["Jan", "Feb"])
        self.assertEqual(payload["distribution_labels"], ["Rhinoceros Beetle", "Brontispa"])
        self.assertEqual(payload["distribution_data"], [2, 1])
        self.assertEqual(payload["trend_datasets"][0]["data"], [1, 1])
