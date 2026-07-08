import unittest

from app.report_storage import build_report_payload, resolve_field_notes


class ReportStorageTests(unittest.TestCase):
    def test_resolve_field_notes_prefers_field_notes(self):
        form_data = {"field_notes": "Leaf damage observed", "location_notes": "Nearby orchard"}
        self.assertEqual(resolve_field_notes(form_data), "Leaf damage observed")

    def test_build_report_payload_includes_user_id_and_timestamps(self):
        payload = build_report_payload(
            user_id="user-123",
            pest_type="Brontispa",
            damage_severity="Moderate",
            field_notes="Leaf damage observed",
            confidence="92.5",
            latitude="14.1",
            longitude="121.3",
            gps_accuracy="5.0",
            location_source="camera_gps",
            photo_taken_at="2026-07-08T10:00:00+00:00",
            initial_recommendations=["Inspect leaves"],
            farmer_name="Juan Dela Cruz",
            created_at="2026-07-08T10:00:00+00:00",
            submitted_at="2026-07-08T10:00:00+00:00",
        )

        self.assertEqual(payload["user_id"], "user-123")
        self.assertEqual(payload["field_notes"], "Leaf damage observed")
        self.assertEqual(payload["created_at"], "2026-07-08T10:00:00+00:00")
        self.assertEqual(payload["submitted_at"], "2026-07-08T10:00:00+00:00")
        self.assertEqual(payload["status"], "Pending")


if __name__ == "__main__":
    unittest.main()
