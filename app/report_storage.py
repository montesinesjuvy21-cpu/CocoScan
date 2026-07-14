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


def normalize_report_status(value: Any, *, default: str = "Under Review") -> str:
    """Normalize report status values to the simple workflow used across the app."""
    if value is None:
        return default

    normalized = str(value).strip()
    if not normalized:
        return default

    key = normalized.lower().replace("_", " ").replace("-", " ")
    status_map = {
        "pending assessment": "Under Review",
        "pending review": "Under Review",
        "under review": "Under Review",
        "reviewed": "Under Review",
        "submitted": "Under Review",
        "assessment issued": "Assessment Issued",
        "assessment": "Assessment Issued",
        "on site visit requested": "Waiting for Agriculturist Confirmation",
        "visit requested": "Waiting for Agriculturist Confirmation",
        "waiting for agriculturist confirmation": "Waiting for Agriculturist Confirmation",
        "waiting for schedule": "Waiting for Agriculturist Confirmation",
        "visit scheduled": "Visit Scheduled",
        "visit completed": "Visit Completed",
        "resolved": "Resolved",
        "complete": "Resolved",
        "completed": "Resolved",
        "closed": "Resolved",
        "final remarks issued": "Resolved",
        "final remarks": "Resolved",
        "recommendation issued": "Resolved",
    }

    return status_map.get(key, normalized)


def is_pending_report_status(value: Any) -> bool:
    return not is_resolved_report_status(value)


def is_active_report_status(value: Any) -> bool:
    return is_pending_report_status(value)


def is_reviewed_report_status(value: Any) -> bool:
    return is_resolved_report_status(value)


def is_resolved_report_status(value: Any) -> bool:
    return normalize_report_status(value, default="Under Review") == "Resolved"


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
    status: str = "Under Review",
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

    status = normalize_report_status(status, default="Under Review")

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
