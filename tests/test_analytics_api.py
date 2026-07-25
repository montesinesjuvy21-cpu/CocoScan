import unittest

import main


class AnalyticsApiTests(unittest.TestCase):
    def setUp(self):
        main.app.config.update(TESTING=True)
        self.client = main.app.test_client()

    def test_api_analytics_accepts_month_filter_without_supabase_date_filters(self):
        class FakeResponse:
            def __init__(self, data):
                self.data = data

        class FakeQuery:
            def __init__(self, rows):
                self.rows = rows

            def select(self, *args, **kwargs):
                return self

            def gte(self, *args, **kwargs):
                raise AssertionError("analytics route should not rely on Supabase date filters")

            def lte(self, *args, **kwargs):
                raise AssertionError("analytics route should not rely on Supabase date filters")

            def order(self, *args, **kwargs):
                return self

            def execute(self):
                return FakeResponse(self.rows)

        class FakeSupabaseClient:
            def table(self, _table_name):
                return FakeQuery([
                    {
                        "id": "report-1",
                        "created_at": "2026-07-05T10:00:00Z",
                        "pest_type": "Rhinoceros Beetle",
                        "status": "Under Review",
                    },
                    {
                        "id": "report-2",
                        "created_at": "2026-07-10T11:00:00Z",
                        "pest_type": "Brontispa",
                        "status": "Resolved",
                    },
                ])

        original_supabase = main.supabase
        main.supabase = FakeSupabaseClient()
        self.addCleanup(setattr, main, "supabase", original_supabase)

        with self.client.session_transaction() as session:
            session["user_id"] = "user-1"
            session["user_role"] = "lgu"

        response = self.client.get("/api/analytics?month=2026-07")

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["success"])
        self.assertEqual(payload["status_breakdown"]["rhinoceros beetle"]["pending"], 1)
        self.assertEqual(payload["status_breakdown"]["brontispa"]["resolved"], 1)
        self.assertEqual(payload["status_breakdown"]["total"]["pending"], 1)
        self.assertEqual(payload["status_breakdown"]["total"]["resolved"], 1)
        self.assertIn("trend_labels", payload["dashboard_payload"])

    def test_api_analytics_includes_all_pest_types_in_dashboard_payload(self):
        class FakeResponse:
            def __init__(self, data):
                self.data = data

        class FakeQuery:
            def __init__(self, rows):
                self.rows = rows

            def select(self, *args, **kwargs):
                return self

            def gte(self, *args, **kwargs):
                raise AssertionError("analytics route should not rely on Supabase date filters")

            def lte(self, *args, **kwargs):
                raise AssertionError("analytics route should not rely on Supabase date filters")

            def order(self, *args, **kwargs):
                return self

            def execute(self):
                return FakeResponse(self.rows)

        class FakeSupabaseClient:
            def table(self, _table_name):
                return FakeQuery([
                    {
                        "id": "report-1",
                        "created_at": "2026-07-05T10:00:00Z",
                        "pest_type": "Rhinoceros Beetle",
                        "status": "Under Review",
                    },
                    {
                        "id": "report-2",
                        "created_at": "2026-07-10T11:00:00Z",
                        "pest_type": "Brontispa",
                        "status": "Resolved",
                    },
                    {
                        "id": "report-3",
                        "created_at": "2026-07-12T09:00:00Z",
                        "pest_type": "Healthy Coconut Leaf",
                        "status": "Under Review",
                    },
                ])

        original_supabase = main.supabase
        main.supabase = FakeSupabaseClient()
        self.addCleanup(setattr, main, "supabase", original_supabase)

        with self.client.session_transaction() as session:
            session["user_id"] = "user-1"
            session["user_role"] = "lgu"

        response = self.client.get("/api/analytics?month=2026-07")
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["success"])
        self.assertIn("Healthy Coconut Leaf", payload["dashboard_payload"]["distribution_labels"])
        self.assertEqual(payload["status_breakdown"]["total"]["pending"], 2)
        self.assertEqual(payload["status_breakdown"]["total"]["resolved"], 1)
