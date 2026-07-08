import unittest

from app.report_storage import (
    build_report_payload,
    is_pending_report_status,
    is_reviewed_report_status,
    normalize_report_status,
    resolve_field_notes,
    resolve_report_image_url,
)


class ReportStorageTests(unittest.TestCase):
    def test_resolve_field_notes_prefers_field_notes(self):
        form_data = {"field_notes": "Leaf damage observed", "location_notes": "Nearby orchard"}
        self.assertEqual(resolve_field_notes(form_data), "Leaf damage observed")

    def test_build_report_payload_includes_user_id_and_timestamps(self):
        payload = build_report_payload(
            user_id="user-123",
            pest_type="Brontispa",
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
        self.assertNotIn("damage_severity", payload)

    def test_status_helpers_normalize_pending_and_reviewed_states(self):
        self.assertEqual(normalize_report_status("Pending Review"), "Pending")
        self.assertEqual(normalize_report_status("Reviewed"), "Recommendation Issued")
        self.assertEqual(normalize_report_status("Submitted"), "Pending")
        self.assertTrue(is_pending_report_status("pending review"))
        self.assertTrue(is_pending_report_status("Submitted"))
        self.assertTrue(is_reviewed_report_status("reviewed"))
        self.assertFalse(is_pending_report_status("Recommendation Issued"))
        self.assertFalse(is_reviewed_report_status("Pending"))

    def test_resolve_report_image_url_handles_storage_keys_and_public_urls(self):
        base_url = "https://utvltqgxqnpcqrphuojc.supabase.co/storage/v1/object/public/reports/"
        self.assertEqual(resolve_report_image_url("report_media/sample.jpg"), f"{base_url}report_media/sample.jpg")
        self.assertEqual(resolve_report_image_url(f"{base_url}report_media/sample.jpg"), f"{base_url}report_media/sample.jpg")
        self.assertEqual(resolve_report_image_url("https://example.com/image.jpg"), "https://example.com/image.jpg")


if __name__ == "__main__":
    unittest.main()
