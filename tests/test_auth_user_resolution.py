import os
import sys
from pathlib import Path

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_KEY", "dummy-key")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from main import _resolve_app_user_id


def test_resolve_app_user_id_falls_back_to_email_lookup():
    session_data = {"user_email": "farmer@example.com"}

    resolved_id = _resolve_app_user_id(
        session_data,
        lookup_user_id=lambda candidate_id: False,
        lookup_email=lambda email: "users-table-id-123" if email == "farmer@example.com" else None,
    )

    assert resolved_id == "users-table-id-123"
    assert session_data["user_id"] == "users-table-id-123"


def test_resolve_app_user_id_keeps_already_valid_session_id():
    session_data = {"user_id": "users-table-id-456"}

    resolved_id = _resolve_app_user_id(
        session_data,
        lookup_user_id=lambda candidate_id: candidate_id == "users-table-id-456",
    )

    assert resolved_id == "users-table-id-456"
