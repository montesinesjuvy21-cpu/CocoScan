from datetime import datetime, UTC, timedelta, timezone
import json
from typing import Any, Mapping


SUPABASE_REPORT_IMAGE_BASE_URL = (
    "https://utvltqgxqnpcqrphuojc.supabase.co/storage/v1/object/public/reports/"
)

MANILA_TIMEZONE = timezone(timedelta(hours=8))


def resolve_field_notes(form_data: Mapping[str, Any]) -> str:
    """Return the farmer notes from the submitted form data."""
    for key in ("field_notes", "location_notes", "notes"):
        value = form_data.get(key, "") if hasattr(form_data, "get") else ""
        if isinstance(value, str):
            value = value.strip()
            if value:
                return value
    return ""


def normalize_report_status(value: Any, *, default: str = "Pending Assessment") -> str:
    """Normalize report status values from the UI and database to a canonical workflow state."""
    if value is None:
        return default

    normalized = str(value).strip()
    if not normalized:
        return default

    aliases = {
        "pending": "Pending Assessment",
        "pending assessment": "Pending Assessment",
        "pending review": "Pending Assessment",
        "pending-review": "Pending Assessment",
        "pending_review": "Pending Assessment",
        "submitted": "Pending Assessment",
        "submitted for review": "Pending Assessment",
        "for review": "Pending Assessment",
        "awaiting review": "Pending Assessment",
        "under review": "under_review",
        "under-review": "under_review",
        "under_review": "under_review",
        "reviewed": "Recommendation Issued",
        "reviewed & issued": "Recommendation Issued",
        "recommendation issued": "Recommendation Issued",
        "recommendation-issued": "Recommendation Issued",
        "recommendation_issued": "Recommendation Issued",
        "assessment issued": "assessment_issued",
        "assessment-issued": "assessment_issued",
        "assessment_issued": "assessment_issued",
        "visit requested": "visit_requested",
        "visit-requested": "visit_requested",
        "visit_requested": "visit_requested",
        "waiting agriculturist confirmation": "waiting_agriculturist_confirmation",
        "waiting-agriculturist-confirmation": "waiting_agriculturist_confirmation",
        "waiting_agriculturist_confirmation": "waiting_agriculturist_confirmation",
        "waiting for farmer feedback": "waiting_agriculturist_confirmation",
        "waiting-for-farmer-feedback": "waiting_agriculturist_confirmation",
        "waiting_for_farmer_feedback": "waiting_agriculturist_confirmation",
        "on-site visit requested": "On-site Visit Requested",
        "on site visit requested": "On-site Visit Requested",
        "on-site-visit-requested": "On-site Visit Requested",
        "waiting for schedule": "waiting_agriculturist_confirmation",
        "waiting-for-schedule": "waiting_agriculturist_confirmation",
        "waiting_for_schedule": "waiting_agriculturist_confirmation",
        "visit scheduled": "visit_scheduled",
        "visit-scheduled": "visit_scheduled",
        "visit_scheduled": "visit_scheduled",
        "inspection completed": "visit_completed",
        "inspection-completed": "visit_completed",
        "inspection_completed": "visit_completed",
        "visit completed": "visit_completed",
        "visit-completed": "visit_completed",
        "final remarks issued": "final_remarks_issued",
        "final-remarks-issued": "final_remarks_issued",
        "final_remarks_issued": "final_remarks_issued",
        "closed": "closed",
        "resolved": "Resolved",
        "complete": "Resolved",
        "completed": "Resolved",
    }

    key = normalized.lower().replace("_", " ").replace("-", " ")
    return aliases.get(key, normalized)


def is_pending_report_status(value: Any) -> bool:
    normalized = normalize_report_status(value)
    return normalized in {
        "Pending Assessment",
        "Waiting for Farmer Feedback",
        "On-site Visit Requested",
        "Waiting for Schedule",
        "Visit Scheduled",
        "Inspection Completed",
        "under_review",
        "assessment_issued",
        "visit_requested",
        "waiting_agriculturist_confirmation",
        "visit_scheduled",
        "visit_completed",
    }


def is_reviewed_report_status(value: Any) -> bool:
    normalized = normalize_report_status(value)
    return normalized in {"Recommendation Issued", "Resolved", "final_remarks_issued", "resolved", "closed"}


def is_resolved_report_status(value: Any) -> bool:
    normalized = normalize_report_status(value)
    return normalized in {"final_remarks_issued", "resolved", "closed"}


def resolve_report_image_url(image_url: Any) -> str:
    """Return a usable public URL for a report image stored in Supabase Storage."""
    if not image_url:
        return ""

    resolved = str(image_url).strip()
    if not resolved:
        return ""

    if resolved.startswith(("http://", "https://", "data:", "blob:")):
        return resolved

    resolved = resolved.lstrip("/")
    if resolved.startswith("storage/v1/object/public/reports/"):
        resolved = resolved.split("storage/v1/object/public/reports/", 1)[-1]
    elif resolved.startswith("report_media/"):
        resolved = resolved

    return f"{SUPABASE_REPORT_IMAGE_BASE_URL}{resolved}"


def parse_utc_timestamp(value: Any) -> datetime | None:
    if not value:
        return None

    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)

    return parsed.astimezone(MANILA_TIMEZONE)


def format_report_timestamp(value: Any, fmt: str = "%b %d, %Y • %I:%M %p") -> str:
    parsed = parse_utc_timestamp(value)
    return parsed.strftime(fmt) if parsed else "Timestamp unavailable"


def format_report_date(value: Any) -> str:
    parsed = parse_utc_timestamp(value)
    return parsed.strftime("%Y-%m-%d") if parsed else ""


def build_report_payload(
    *,
    user_id: str,
    pest_type: str,
    field_notes: str,
    confidence: Any,
    latitude: str,
    longitude: str,
    gps_accuracy: str,
    location_source: str,
    photo_taken_at: str,
    initial_recommendations: Any,
    farmer_name: str = "Farmer",
    created_at: str | None = None,
    submitted_at: str | None = None,
    status: str = "Pending Assessment",
    image_url: str = "",
    barangay: str = "",
    municipality: str = "",
    province: str = "",
) -> dict[str, Any]:
    """Create a report payload compatible with the Supabase reports table."""
    if created_at is None:
        created_at = datetime.now(UTC).isoformat()
    if submitted_at is None:
        submitted_at = created_at

    if isinstance(initial_recommendations, str):
        try:
            initial_recommendations = json.loads(initial_recommendations)
        except (TypeError, ValueError):
            initial_recommendations = [initial_recommendations]
    if initial_recommendations is None:
        initial_recommendations = []

    # Convert coordinate strings to floats for database compatibility
    try:
        latitude = float(latitude) if latitude else None
    except (ValueError, TypeError):
        latitude = None
    
    try:
        longitude = float(longitude) if longitude else None
    except (ValueError, TypeError):
        longitude = None
    
    # Convert confidence to float
    try:
        confidence = float(confidence) if confidence else 0.0
    except (ValueError, TypeError):
        confidence = 0.0

    status = normalize_report_status(status, default="Pending Assessment")

    return {
        "user_id": user_id,
        "farmer_name": farmer_name,
        "pest_type": pest_type,
        "confidence": confidence,
        "image_url": image_url,
        "field_notes": field_notes,
        "status": status,
        "created_at": created_at,
        "initial_recommendations": initial_recommendations,
        "latitude": latitude,
        "longitude": longitude,
        "gps_accuracy": gps_accuracy,
        "location_source": location_source,
        "photo_taken_at": photo_taken_at,
        "barangay": barangay,
        "municipality": municipality,
        "province": province,
        "submitted_at": submitted_at,
        "updated_at": submitted_at,
    }
