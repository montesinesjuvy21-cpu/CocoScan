from datetime import datetime, UTC
import json
from typing import Any, Mapping


SUPABASE_REPORT_IMAGE_BASE_URL = (
    "https://utvltqgxqnpcqrphuojc.supabase.co/storage/v1/object/public/reports/"
)


def resolve_field_notes(form_data: Mapping[str, Any]) -> str:
    """Return the farmer notes from the submitted form data."""
    for key in ("field_notes", "location_notes", "notes"):
        value = form_data.get(key, "") if hasattr(form_data, "get") else ""
        if isinstance(value, str):
            value = value.strip()
            if value:
                return value
    return ""


def normalize_report_status(value: Any, *, default: str = "Pending") -> str:
    """Normalize report status values from the UI and database to a canonical workflow state."""
    if value is None:
        return default

    normalized = str(value).strip()
    if not normalized:
        return default

    aliases = {
        "pending": "Pending",
        "pending review": "Pending",
        "pending-review": "Pending",
        "pending_review": "Pending",
        "submitted": "Pending",
        "submitted for review": "Pending",
        "for review": "Pending",
        "awaiting review": "Pending",
        "under review": "Pending",
        "reviewed": "Recommendation Issued",
        "reviewed & issued": "Recommendation Issued",
        "recommendation issued": "Recommendation Issued",
        "recommendation-issued": "Recommendation Issued",
        "recommendation_issued": "Recommendation Issued",
        "resolved": "Recommendation Issued",
        "completed": "Recommendation Issued",
    }

    key = normalized.lower().replace("_", " ").replace("-", " ")
    return aliases.get(key, normalized)


def is_pending_report_status(value: Any) -> bool:
    return not is_reviewed_report_status(value)


def is_reviewed_report_status(value: Any) -> bool:
    return normalize_report_status(value) == "Recommendation Issued"


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
    status: str = "Pending",
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

    status = normalize_report_status(status, default="Pending")

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
