import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_KEY", "dummy-key")

from main import (
    _build_visit_workflow_payload,
    _coerce_time_to_hhmmss,
    _format_confirmed_schedule_label,
)


def test_coerce_time_to_hhmmss_supports_ampm_and_24h_inputs():
    assert _coerce_time_to_hhmmss("9:00 AM") == "09:00:00"
    assert _coerce_time_to_hhmmss("13:30") == "13:30:00"


def test_format_confirmed_schedule_label_uses_readable_stamp():
    assert _format_confirmed_schedule_label("2026-07-21", "09:00:00", "11:30:00") == "Confirmed: July 21, 2026, from 9:00 AM to 11:30 AM"


def test_build_visit_workflow_payload_exposes_visit_chats_and_visit_schedules():
    payload = _build_visit_workflow_payload(
        report_row={"id": 7, "status": "Awaiting Confirmed Schedule", "user_id": 10, "reviewed_by_id": 42},
        chat_rows=[
            {"id": 1, "sender_id": 10, "message": "Need help", "created_at": "2026-07-15T10:00:00+00:00"},
            {"id": 2, "sender_id": 42, "message": "I can assist", "created_at": "2026-07-15T10:05:00+00:00"},
        ],
        schedule_rows=[
            {"id": 1, "confirmed_date": "2026-07-21", "start_time": "09:00:00", "end_time": "11:00:00"},
        ],
    )

    assert payload["messages"][0]["sender_label"] == "Farmer"
    assert payload["visit_chats"][1]["sender_label"] == "Agriculturist"
    assert payload["visit_schedules"][0]["confirmed_date"] == "2026-07-21"
    assert payload["has_messages"] is True
    assert payload["schedule_stamp"] == "Confirmed: July 21, 2026, from 9:00 AM to 11:00 AM"
