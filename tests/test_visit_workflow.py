import os

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_KEY", "dummy-key")

from main import _coerce_time_to_hhmmss, _do_schedule_time_ranges_overlap, _format_confirmed_schedule_label, _should_archive_visit_discussion, _fetch_visit_workflow_payload


def test_coerce_time_to_hhmmss_supports_ampm_and_24h_inputs():
    assert _coerce_time_to_hhmmss("9:00 AM") == "09:00:00"
    assert _coerce_time_to_hhmmss("13:30") == "13:30:00"


def test_format_confirmed_schedule_label_uses_readable_stamp():
    assert _format_confirmed_schedule_label("2026-07-21", "09:00:00", "11:30:00") == "Confirmed: July 21, 2026, from 9:00 AM to 11:30 AM"


def test_do_schedule_time_ranges_overlap_returns_true_for_overlapping_slots():
    assert _do_schedule_time_ranges_overlap("09:00 AM", "11:00 AM", "08:00 AM", "10:00 AM") is True
    assert _do_schedule_time_ranges_overlap("09:00 AM", "11:00 AM", "11:00 AM", "12:00 PM") is False
    assert _do_schedule_time_ranges_overlap("09:00 AM", "11:00 AM", "08:00 AM", "09:00 AM") is False


def test_archive_logic_reopens_discussion_when_reschedule_is_pending():
    assert _should_archive_visit_discussion("Visit Scheduled", "") is True
    assert _should_archive_visit_discussion("Visit Scheduled", "Bad weather") is False
    assert _should_archive_visit_discussion("Awaiting Confirmed Schedule", "") is False


def test_fetch_visit_workflow_payload_prepends_visit_request_reason(monkeypatch):
    import main
    class DummyResponse:
        def __init__(self, data):
            self.data = data
    class DummyQuery:
        def __init__(self, data):
            self._data = data
        def select(self, *args, **kwargs): return self
        def eq(self, *args, **kwargs): return self
        def order(self, *args, **kwargs): return self
        def execute(self): return DummyResponse(self._data)
    class DummySupabase:
        def table(self, name):
            if name == "reports":
                return DummyQuery([{"id": 999, "status": "Awaiting Confirmed Schedule", "user_id": "u1", "visit_request_reason": "Need checkup on trees"}])
            return DummyQuery([])
    monkeypatch.setattr(main, "supabase", DummySupabase())
    payload = _fetch_visit_workflow_payload(999)
    assert len(payload["messages"]) == 1
    assert payload["messages"][0]["message"] == "Need checkup on trees"
    assert payload["messages"][0]["sender_label"] == "Farmer"

