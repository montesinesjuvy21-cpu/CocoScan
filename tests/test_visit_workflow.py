import os

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_KEY", "dummy-key")

from main import _coerce_time_to_hhmmss, _format_confirmed_schedule_label, _should_archive_visit_discussion


def test_coerce_time_to_hhmmss_supports_ampm_and_24h_inputs():
    assert _coerce_time_to_hhmmss("9:00 AM") == "09:00:00"
    assert _coerce_time_to_hhmmss("13:30") == "13:30:00"


def test_format_confirmed_schedule_label_uses_readable_stamp():
    assert _format_confirmed_schedule_label("2026-07-21", "09:00:00", "11:30:00") == "Confirmed: July 21, 2026, from 9:00 AM to 11:30 AM"


def test_archive_logic_reopens_discussion_when_reschedule_is_pending():
    assert _should_archive_visit_discussion("Visit Scheduled", "") is True
    assert _should_archive_visit_discussion("Visit Scheduled", "Bad weather") is False
    assert _should_archive_visit_discussion("Awaiting Confirmed Schedule", "") is False
