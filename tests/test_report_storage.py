import unittest

from app.report_storage import (
    build_report_payload,
    format_report_date,
    format_report_timestamp,
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
        self.assertEqual(payload["status"], "Pending Assessment")
        self.assertNotIn("damage_severity", payload)

    def test_status_helpers_normalize_pending_and_reviewed_states(self):
        self.assertEqual(normalize_report_status("Pending Review"), "Pending Assessment")
        self.assertEqual(normalize_report_status("Reviewed"), "Recommendation Issued")
        self.assertEqual(normalize_report_status("Submitted"), "Pending Assessment")
        self.assertEqual(normalize_report_status("On-site Visit Requested"), "On-site Visit Requested")
        self.assertEqual(normalize_report_status("Resolved"), "Resolved")
        self.assertTrue(is_pending_report_status("pending review"))
        self.assertTrue(is_pending_report_status("Submitted"))
        self.assertTrue(is_reviewed_report_status("reviewed"))
        self.assertTrue(is_reviewed_report_status("Resolved"))
        self.assertFalse(is_pending_report_status("Recommendation Issued"))
        self.assertFalse(is_reviewed_report_status("Pending Assessment"))

    def test_resolve_report_image_url_handles_storage_keys_and_public_urls(self):
        base_url = "https://utvltqgxqnpcqrphuojc.supabase.co/storage/v1/object/public/reports/"
        self.assertEqual(resolve_report_image_url("report_media/sample.jpg"), f"{base_url}report_media/sample.jpg")
        self.assertEqual(resolve_report_image_url(f"{base_url}report_media/sample.jpg"), f"{base_url}report_media/sample.jpg")
        self.assertEqual(resolve_report_image_url("https://example.com/image.jpg"), "https://example.com/image.jpg")

    def test_format_report_timestamp_converts_utc_to_manila_time(self):
        utc_value = "2026-07-08T00:30:00+00:00"
        self.assertEqual(format_report_timestamp(utc_value), "Jul 08, 2026 • 08:30 AM")
        self.assertEqual(format_report_date(utc_value), "2026-07-08")


if __name__ == "__main__":
    unittest.main()
