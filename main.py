import os
import traceback
import logging
import json
from datetime import datetime, UTC
from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
import base64
from io import BytesIO
from werkzeug.utils import secure_filename
from werkzeug.exceptions import RequestEntityTooLarge
from dotenv import load_dotenv
from supabase import create_client, Client
from PIL import Image
import re
import requests

# Native Python email modules (Replaces Brevo SDK)
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from app.validators import (
    validate_signup_data, 
    validate_duplicate_email,
    validate_login_credentials,
    validate_login_form,
    ValidationError
)
from app.password_utils import hash_password, verify_password
from app.report_storage import (
    build_report_payload,
    format_report_date,
    format_report_timestamp,
    is_pending_report_status,
    is_resolved_report_status,
    normalize_report_status,
    resolve_farmer_notes,
    resolve_field_notes,
    resolve_report_image_url,
)
from app.dashboard_data import build_dashboard_chart_payload
from app.model_paths import resolve_model_path
from app.map_utils import filter_map_reports, limit_recent_records

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def _normalize_availability_slots(value):
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        cleaned = value.strip()
        if not cleaned:
            return []
        if cleaned.startswith("["):
            try:
                parsed = json.loads(cleaned)
                return _normalize_availability_slots(parsed)
            except Exception:
                return []
        return [item.strip() for item in re.split(r',|;|\n', cleaned) if item.strip()]
    return []


# Load environment configuration variables
load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "fallback_local_secret")
# Upload configuration
# Limit uploads to 25 MB by default
app.config['MAX_CONTENT_LENGTH'] = int(os.getenv('MAX_CONTENT_MB', '25')) * 1024 * 1024
app.config['UPLOAD_FOLDER'] = os.path.join(app.root_path, 'static', 'uploads')
try:
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
except Exception:
    logger.warning(f"Could not create upload folder: {app.config['UPLOAD_FOLDER']}")


@app.errorhandler(RequestEntityTooLarge)
def handle_file_too_large(error):
    max_mb = app.config.get('MAX_CONTENT_LENGTH', 0) // (1024 * 1024)
    return (
        jsonify({
            'success': False,
            'error': 'File too large',
            'message': f'Uploaded file exceeds the allowed size of {max_mb} MB.'
        }),
        413,
    )

# Initialize Supabase Client Connection
url: str = os.getenv("SUPABASE_URL")
key: str = os.getenv("SUPABASE_KEY")
supabase: Client = create_client(url, key)


def normalize_role(value) -> str:
    return str(value or "").strip().lower()


def _resolve_app_user_id(session_data=None, *, lookup_user_id=None, lookup_email=None):
    """Return the public users.id that should be persisted into foreign-keyed columns."""
    active_session = session_data if session_data is not None else session
    if active_session is None:
        return None

    candidate_id = active_session.get("user_id")
    email = str(active_session.get("user_email") or active_session.get("email") or "").strip()

    if candidate_id:
        if lookup_user_id is not None:
            if lookup_user_id(candidate_id):
                return candidate_id
        else:
            try:
                response = supabase.table("users").select("id").eq("id", candidate_id).limit(1).execute()
                rows = getattr(response, "data", None) or []
                if rows:
                    return candidate_id
            except Exception as exc:
                logger.warning(f"Unable to verify session user id {candidate_id}: {exc}")

    if email:
        if lookup_email is not None:
            resolved_id = lookup_email(email)
            if resolved_id:
                if hasattr(active_session, "__setitem__"):
                    active_session["user_id"] = resolved_id
                return resolved_id
        else:
            try:
                response = supabase.table("users").select("id").eq("email", email).limit(1).execute()
                rows = getattr(response, "data", None) or []
                if rows:
                    resolved_id = rows[0].get("id")
                    if resolved_id:
                        if hasattr(active_session, "__setitem__"):
                            active_session["user_id"] = resolved_id
                        return resolved_id
            except Exception as exc:
                logger.warning(f"Unable to resolve session user id from email {email}: {exc}")

    return candidate_id


def _get_current_app_user_id():
    return _resolve_app_user_id(session)


def _append_status_note(existing_notes, note_text):
    cleaned_existing = str(existing_notes or "").strip()
    cleaned_note = str(note_text or "").strip()
    if not cleaned_note:
        return cleaned_existing
    if not cleaned_existing:
        return cleaned_note
    return f"{cleaned_existing}\n\n{cleaned_note}"


def _should_archive_visit_discussion(status, reschedule_reason):
    normalized_status = str(status or "").strip().lower()
    has_pending_reschedule = bool(str(reschedule_reason or "").strip())
    if normalized_status == "visit scheduled" or normalized_status == "visit_scheduled":
        return not has_pending_reschedule
    return False


def _coerce_time_to_hhmmss(value):
    if value is None:
        return ""

    if isinstance(value, datetime):
        return value.strftime("%H:%M:%S")

    cleaned = str(value or "").strip()
    if not cleaned:
        return ""

    for fmt in ("%H:%M:%S", "%H:%M", "%I:%M %p", "%I:%M:%S %p"):
        try:
            return datetime.strptime(cleaned.upper(), fmt).strftime("%H:%M:%S")
        except ValueError:
            continue

    return ""


def _format_time_label(value):
    normalized = _coerce_time_to_hhmmss(value)
    if not normalized:
        return ""

    parsed = datetime.strptime(normalized, "%H:%M:%S")
    suffix = parsed.strftime("%p").upper()
    hour = parsed.hour % 12 or 12
    return f"{hour}:{parsed.minute:02d} {suffix}"


def _format_confirmed_schedule_label(confirmed_date, start_time, end_time):
    try:
        parsed_date = datetime.strptime(str(confirmed_date or ""), "%Y-%m-%d")
    except ValueError:
        return ""

    start_label = _format_time_label(start_time)
    end_label = _format_time_label(end_time)
    if not start_label or not end_label:
        return ""

    return f"Confirmed: {parsed_date.strftime('%B %d, %Y')}, from {start_label} to {end_label}"


def _validate_time_range(start_time, end_time):
    normalized_start = _coerce_time_to_hhmmss(start_time)
    normalized_end = _coerce_time_to_hhmmss(end_time)
    if not normalized_start or not normalized_end:
        raise ValueError("Please provide both start and end times.")

    start_dt = datetime.strptime(normalized_start, "%H:%M:%S")
    end_dt = datetime.strptime(normalized_end, "%H:%M:%S")
    if end_dt <= start_dt:
        raise ValueError("End time must be after start time.")
    
    # Validate 8 AM to 5 PM constraint
    if start_dt.time() < datetime.strptime("08:00:00", "%H:%M:%S").time():
        raise ValueError("Start time cannot be earlier than 8:00 AM.")
    if end_dt.time() > datetime.strptime("17:00:00", "%H:%M:%S").time():
        raise ValueError("End time cannot be later than 5:00 PM.")

    return normalized_start, normalized_end


def _fetch_visit_workflow_payload(report_id):
    report_response = supabase.table("reports").select("id, status, user_id, reviewed_by_id, visit_request_reason, visit_requested_at, visit_summary, visit_completed_at, final_remarks, visit_reschedule_reason, visit_rescheduled_at, visit_rescheduled_by").eq("id", report_id).execute()
    report_row = (getattr(report_response, "data", None) or [{}])[0] if getattr(report_response, "data", None) else {}

    chats_response = supabase.table("visit_chats").select("id, sender_id, message, created_at").eq("report_id", report_id).order("created_at", desc=False).execute()
    chat_rows = getattr(chats_response, "data", None) or []

    schedules_response = supabase.table("visit_schedules").select("id, agriculturist_id, confirmed_date, start_time, end_time, created_at").eq("report_id", report_id).order("created_at", desc=False).execute()
    schedule_rows = getattr(schedules_response, "data", None) or []

    messages = []
    for chat_row in chat_rows:
        sender_id = chat_row.get("sender_id")
        sender_label = "Farmer"
        if sender_id and report_row.get("reviewed_by_id") and str(sender_id) == str(report_row.get("reviewed_by_id")):
            sender_label = "Agriculturist"
        elif sender_id and report_row.get("user_id") and str(sender_id) == str(report_row.get("user_id")):
            sender_label = "Farmer"
        else:
            sender_label = "Agriculturist" if sender_id and report_row.get("reviewed_by_id") else "Farmer"
        messages.append({
            "id": chat_row.get("id"),
            "sender_id": sender_id,
            "sender_label": sender_label,
            "message": chat_row.get("message") or "",
            "created_at": chat_row.get("created_at"),
        })

    latest_schedule = schedule_rows[-1] if schedule_rows else None
    schedule_stamp = ""
    if latest_schedule:
        schedule_stamp = _format_confirmed_schedule_label(latest_schedule.get("confirmed_date"), latest_schedule.get("start_time"), latest_schedule.get("end_time"))

    has_pending_reschedule = bool(str(report_row.get("visit_reschedule_reason") or "").strip())
    
    if has_pending_reschedule and schedule_stamp:
        schedule_stamp = schedule_stamp.replace("Confirmed:", "Previous Schedule:")

    has_pending_reschedule = bool(str(report_row.get("visit_reschedule_reason") or "").strip())
    is_archived = _should_archive_visit_discussion(report_row.get("status"), report_row.get("visit_reschedule_reason"))
    
    if has_pending_reschedule:
        schedule_title = "Reschedule Requested"
    else:
        schedule_title = "New Schedule Confirmed" if len(schedule_rows) > 1 else "Visit Scheduled"

    visit_images_response = supabase.table("visit_images").select("image_url").eq("report_id", report_id).execute()
    visit_images = [row.get("image_url") for row in getattr(visit_images_response, "data", None) or [] if row.get("image_url")]

    return {
        "report": report_row,
        "messages": messages,
        "schedule": latest_schedule,
        "schedule_stamp": schedule_stamp,
        "is_archived": is_archived,
        "schedule_title": schedule_title,
        "visit_images": visit_images,
    }

def _update_report_workflow(report_id, status, *, note=None, extra_updates=None):
    if not report_id:
        raise ValueError("Missing report reference")

    now_iso = datetime.now(UTC).isoformat()
    update_data = {
        "status": normalize_report_status(status, default="Under Review"),
        "updated_at": now_iso,
    }

    if note and (not extra_updates or "farmer_notes" not in extra_updates):
        existing_response = supabase.table("reports").select("farmer_notes").eq("id", report_id).execute()
        existing_rows = getattr(existing_response, "data", None) or []
        existing_report = existing_rows[0] if existing_rows else {}
        existing_notes = existing_report.get("farmer_notes") or ""
        update_data["farmer_notes"] = _append_status_note(existing_notes, note)

    if extra_updates:
        if "farmer_notes" in extra_updates:
            update_data["farmer_notes"] = extra_updates["farmer_notes"]
            extra_updates = {k: v for k, v in extra_updates.items() if k != "farmer_notes"}
        update_data.update(extra_updates)

    update_response = supabase.table("reports").update(update_data).eq("id", report_id).execute()
    return update_response


def _persist_supporting_images(report_id, files, *, uploaded_at=None):
    if not report_id:
        return []

    if not files:
        return []

    uploaded_at = uploaded_at or datetime.now(UTC).isoformat()
    rows = []
    for index, uploaded_file in enumerate(files):
        if not uploaded_file:
            continue
        if not getattr(uploaded_file, "filename", None):
            continue
        safe_name = secure_filename(uploaded_file.filename or f"supporting_{index}.jpg")
        storage_name = f"visit_{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}_{index}_{safe_name}"
        image_bytes = uploaded_file.read()
        image_url = upload_image_to_supabase(image_bytes, storage_name, uploaded_file.mimetype)
        if image_url:
            rows.append({
                "report_id": report_id,
                "image_url": image_url,
                "uploaded_at": uploaded_at,
            })

    if rows:
        supabase.table("report_supporting_images").insert(rows).execute()
    return rows


def _persist_visit_images(report_id, files, user_id, *, uploaded_at=None):
    if not report_id or not files:
        return []

    uploaded_at = uploaded_at or datetime.now(UTC).isoformat()
    rows = []
    for index, uploaded_file in enumerate(files):
        if not uploaded_file or not getattr(uploaded_file, "filename", None):
            continue
        safe_name = secure_filename(uploaded_file.filename or f"visit_{index}.jpg")
        storage_name = f"visit_{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}_{index}_{safe_name}"
        image_bytes = uploaded_file.read()
        image_url = upload_image_to_supabase(image_bytes, storage_name, uploaded_file.mimetype)
        if image_url:
            rows.append({
                "report_id": report_id,
                "image_url": image_url,
                "uploaded_by": user_id,
                "uploaded_at": uploaded_at,
            })

    if rows:
        supabase.table("visit_images").insert(rows).execute()
    return rows

# Notifications removed: backend persistence and helper functions have been deleted.
# If notification functionality is required again, reintroduce a lean API and helpers here.


def normalize_submission_error(error_str: str) -> str:
    """Convert technical database errors into user-friendly messages."""
    error_lower = error_str.lower()
    
    if "invalid input syntax for type" in error_lower:
        if "integer" in error_lower or "numeric" in error_lower:
            return "GPS coordinates are invalid. Please ensure location data is properly captured before submitting."
    
    if "not null violation" in error_lower or "null value" in error_lower:
        return "Some required fields are missing. Please fill in all information before submitting."
    
    if "duplicate" in error_lower or "unique" in error_lower:
        return "This report may have already been submitted. Please refresh and try again."
    
    if "connection" in error_lower or "timeout" in error_lower:
        return "Unable to connect to the server. Please check your internet connection and try again."
    
    return "Failed to submit report. Please try again or contact support if the issue persists."


def reverse_geocode_latlng(latitude, longitude):
    try:
        response = requests.get(
            "https://nominatim.openstreetmap.org/reverse",
            params={
                "format": "jsonv2",
                "lat": latitude,
                "lon": longitude,
                "addressdetails": 1,
            },
            headers={"User-Agent": "CocoScan/1.0"},
            timeout=15,
        )
        if not response.ok:
            logger.warning(f"Reverse geocode failed: {response.status_code}")
            return {}

        payload = response.json().get("address", {}) or {}
        return {
            "barangay": payload.get("barangay") or payload.get("suburb") or payload.get("neighbourhood") or payload.get("hamlet") or "",
            "municipality": payload.get("municipality") or payload.get("city") or payload.get("town") or payload.get("county") or "",
            "province": payload.get("province") or payload.get("state") or payload.get("region") or "",
        }
    except Exception as geocode_err:
        logger.warning(f"Reverse geocode exception: {str(geocode_err)}")
        return {}


def upload_image_to_supabase(file_bytes, filename, content_type="application/octet-stream"):
    bucket = (os.getenv('SUPABASE_STORAGE_BUCKET', 'reports') or 'reports').strip() or 'reports'
    storage_path = f"report_media/{filename}"
    try:
        storage = supabase.storage.from_(bucket)
        upload_result = storage.upload(storage_path, file_bytes, {
            "content-type": content_type
        })
        # The storage API may return data with publicUrl or error fields
        if isinstance(upload_result, dict):
            if upload_result.get('error'):
                logger.warning(f"Supabase Storage upload error: {upload_result.get('error')}")
                return ''
        elif hasattr(upload_result, 'error') and upload_result.error:
            logger.warning(f"Supabase Storage upload error: {upload_result.error}")
            return ''

        return storage_path
    except Exception as upload_err:
        logger.warning(f"Supabase Storage helper error: {str(upload_err)}")
    return ''

def send_status_email(user_email, user_name, status):
    """Sends a transactional HTML notification email to the user via Gmail SMTP"""
    smtp_server = os.getenv("MAIL_SERVER", "smtp.gmail.com").strip()
    smtp_port = int(os.getenv("MAIL_PORT", 587))
    sender_email = (os.getenv("MAIL_USERNAME") or "").strip()
    sender_password = (os.getenv("MAIL_PASSWORD") or "").strip()
    
    sender_name = "CocoScan Admin Team"
    subject = f"Account Update: Your CocoScan Application has been {status}"
    
    # Dynamic styling matching the context status
    theme_color = "#40916c" if status == "Approved" else "#e63946"
    
    # Clean, vibrant SVG logo for email
    cocoscan_logo_svg = """
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512" width="64" height="64" style="display: block; margin: 0 auto;">
        <!-- Shield Base -->
        <path fill="#059669" d="M256 0c-11.5 0-22.1 5.5-28.5 14.8C183.3 78.1 105.9 115.4 52 123.8c-12 1.9-20 12.3-20 24.5 0 185.3 125.7 319.4 207.7 359.8 10.1 5 22.4 5 32.5 0 20.3-10 54.3-30.8 89.2-61.9-10.7-18-17.4-38.6-17.4-60.7 0-61.1 46.1-111.4 106-118.6V148.3c0-12.2-8-22.6-20-24.5-53.9-8.4-131.3-45.7-175.5-109C278.1 5.5 267.5 0 256 0z"/>
        <!-- Shield Halved Highlight -->
        <path fill="#047857" d="M256 44.2v396.4c55.3-31.9 133.8-124.9 142.4-245.5v-75C345 113 288.5 81 256 44.2z"/>
        <!-- Inner Leaf/Sprout -->
        <g transform="translate(156, 160) scale(0.4)" fill="#ffffff">
            <path d="M96 96c0-53 43-96 96-96h16c17.7 0 32 14.3 32 32v16c0 53-43 96-96 96H128c-17.7 0-32-14.3-32-32V96zM0 224c0-53 43-96 96-96h16c17.7 0 32 14.3 32 32v16c0 53-43 96-96 96H32c-17.7 0-32-14.3-32-32v-16zm224-32c0-17.7 14.3-32 32-32s32 14.3 32 32v192c0 17.7-14.3 32-32 32s-32-14.3-32-32V192z"/>
        </g>
    </svg>
    """

    if status == "Approved":
        status_title = "APPLICATION APPROVED"
        status_color = "#059669"
        message_body = f"""
        <p style="margin-bottom: 16px;">Great news! Your account application for <strong>CocoScan</strong> has been reviewed and approved by our administration team.</p>
        <p style="margin-bottom: 24px;">You can now log in to access your custom dashboard, review coconut metrics, and utilize our pest scanning system features.</p>
        <div style="margin: 32px 0; text-align: center;">
            <a href="http://127.0.0.1:5000/login" style="background-color: {status_color}; color: #ffffff; padding: 14px 32px; text-decoration: none; font-weight: 600; font-size: 16px; border-radius: 8px; display: inline-block;">Log In To Dashboard</a>
        </div>
        """
    else:
        status_title = "APPLICATION DECLINED"
        status_color = "#dc2626"
        message_body = f"""
        <p style="margin-bottom: 16px;">Thank you for your interest in <strong>CocoScan</strong>.</p>
        <p style="margin-bottom: 24px;">After carefully reviewing your registration details, our administration team has declined your account application at this time.</p>
        <div style="background-color: #fef2f2; border-left: 4px solid {status_color}; padding: 16px; border-radius: 4px; margin-bottom: 24px;">
            <p style="margin: 0; color: #991b1b; font-size: 14px; line-height: 1.5;">
                <strong>Notice:</strong> If you believe this decision was made in error or if you provided incorrect credentials during registration, please reach out to our system support desk for manual verification.
            </p>
        </div>
        """

    body_html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>{subject}</title>
    </head>
    <body style="margin: 0; padding: 0; background-color: #f3f4f6; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; color: #1f2937; -webkit-font-smoothing: antialiased;">
        <table border="0" cellpadding="0" cellspacing="0" width="100%" style="table-layout: fixed; background-color: #f3f4f6; padding: 40px 20px;">
            <tr>
                <td align="center">
                    <table border="0" cellpadding="0" cellspacing="0" width="100%" style="max-width: 600px; background-color: #ffffff; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06);">
                        <!-- Header Section -->
                        <tr>
                            <td align="center" style="padding: 48px 24px 32px 24px; background-color: #ffffff; border-bottom: 1px solid #e5e7eb;">
                                <div style="margin-bottom: 16px;">
                                    {cocoscan_logo_svg}
                                </div>
                                <h1 style="margin: 0 0 8px 0; font-size: 28px; font-weight: 800; color: #111827; letter-spacing: -0.5px;">CocoScan</h1>
                                <div style="display: inline-block; padding: 4px 12px; background-color: {status_color}15; color: {status_color}; font-size: 12px; font-weight: 700; letter-spacing: 1px; border-radius: 9999px;">
                                    {status_title}
                                </div>
                            </td>
                        </tr>
                        
                        <!-- Body Section -->
                        <tr>
                            <td style="padding: 40px 32px; background-color: #ffffff;">
                                <h2 style="margin: 0 0 20px 0; font-size: 20px; font-weight: 600; color: #111827;">Hello {user_name},</h2>
                                <div style="font-size: 16px; line-height: 1.6; color: #4b5563;">
                                    {message_body}
                                </div>
                                
                                <div style="margin-top: 40px; padding-top: 24px; border-top: 1px solid #e5e7eb;">
                                    <p style="margin: 0; font-size: 15px; color: #6b7280; line-height: 1.6;">
                                        Best regards,<br>
                                        <strong style="color: #111827;">The CocoScan Team</strong>
                                    </p>
                                </div>
                            </td>
                        </tr>
                    </table>
                    
                    <!-- Footer Section -->
                    <table border="0" cellpadding="0" cellspacing="0" width="100%" style="max-width: 600px;">
                        <tr>
                            <td align="center" style="padding: 24px; font-size: 12px; color: #9ca3af; line-height: 1.5;">
                                <p style="margin: 0 0 8px 0;">This transmission is encrypted and delivered from the CocoScan system.</p>
                                <p style="margin: 0;">&copy; 2026 CocoScan • Coconut Disease Detection Systems</p>
                            </td>
                        </tr>
                    </table>
                </td>
            </tr>
        </table>
    </body>
    </html>
    """

    msg = MIMEMultipart()
    msg['From'] = f"{sender_name} <{sender_email}>"
    msg['To'] = user_email
    msg['Subject'] = subject
    msg.attach(MIMEText(body_html, 'html'))

    try:
        try:
            server = smtplib.SMTP(smtp_server, smtp_port, timeout=10)
        except Exception as e:
            logger.error(f"Gmail SMTP Connection failed: {str(e)}\n{traceback.format_exc()}")
            return False

        try:
            server.starttls()
        except Exception as e:
            logger.error(f"Gmail SMTP STARTTLS failed: {str(e)}\n{traceback.format_exc()}")
            return False

        try:
            server.login(sender_email, sender_password)
        except Exception as e:
            logger.error(f"Gmail SMTP Login failed: {str(e)}\n{traceback.format_exc()}")
            return False

        try:
            server.sendmail(sender_email, user_email, msg.as_string())
        except Exception as e:
            logger.error(f"Gmail SMTP Sendmail failed: {str(e)}\n{traceback.format_exc()}")
            return False

        server.quit()
        logger.info(f"Notification email dispatched cleanly via Gmail to {user_email}.")
        return True
    except Exception as e:
        logger.error(f"Gmail SMTP Unexpected Exception thrown while mailing {user_email}: {str(e)}\n{traceback.format_exc()}")
        return False
    
@app.route('/favicon.ico')
def favicon():
    return '', 204

@app.route('/')
def splash():
    """Renders the initial welcome splash screen loader entry point"""
    return render_template('splash.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    """Login page route: Authenticates users against Supabase credentials"""
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')

        if not email or not password:
            flash("Please enter both email and password.", "error")
            return render_template('login.html')

        try:
            validated_email, validated_password = validate_login_form(request.form)
            email = validated_email.strip().lower()
            password = validated_password
        except ValidationError as val_err:
            flash(str(val_err), "error")
            return render_template('login.html')
        except (ValueError, TypeError):
            logger.warning("Login form validator did not return a standard 2-item tuple. Falling back to raw form data.")

        try:
            user_query = supabase.table("users").select("*").eq("email", email).execute()
            
            if not user_query.data:
                flash("Account not found. Please verify your email or sign up.", "error")
                return render_template('login.html')
                
            user_data = user_query.data[0]
            
            if not verify_password(password, user_data.get('password_hash', '')):
                flash("Invalid credentials. Please verify your password and try again.", "error")
                return render_template('login.html')
                
            user_status = user_data.get('status', 'Under Review')
            
            if user_status == 'Under Review':
                flash("Your account is pending administrative approval. You will receive an email once activated.", "warning")
                return render_template('login.html')
            elif user_status == 'Rejected':
                flash("Your application for this account has been declined. Please contact support.", "error")
                return render_template('login.html')

            session.clear()
            session['user_id'] = user_data['id']
            session['user_email'] = email
            session['user_role'] = normalize_role(user_data.get('role'))
            session['user_name'] = f"{user_data.get('first_name', '')} {user_data.get('last_name', '')}".strip()
            
            logger.info(f"User {email} successfully logged in with role: {session['user_role']}")
            
            if session['user_role'] == 'admin':
                return redirect(url_for('admin_user_management'))
            else:
                return redirect(url_for('dashboard'))

        except Exception as db_err:
            logger.error(f"Authentication system pipeline breakdown: {str(db_err)}")
            flash("An unexpected error occurred during login. Please try again later.", "error")
            return render_template('login.html')
            
    return render_template('login.html')

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    """Signup page: Processes user registration with full validation and security"""
    if request.method == 'POST':
        try:
            role = request.form.get('role', '').strip()
            if not role:
                flash("Please select an account role", "error")
                return redirect(url_for('signup'))
            
            validated_data = validate_signup_data(request.form, role)
            email = validated_data['email']
            password = validated_data['password']
            
            if validate_duplicate_email(supabase, email):
                flash("This email address is already registered.", "error")
                return redirect(url_for('signup'))
            
            password_hash = hash_password(password)
            
            user_payload = {
                "first_name": validated_data['first_name'],
                "middle_name": validated_data.get('middle_name'),
                "last_name": validated_data['last_name'],
                "extension_name": validated_data.get('extension_name'),
                "age": validated_data['age'],
                "barangay": validated_data['barangay'],
                "municipality": validated_data['municipality'],
                "province": validated_data['province'],
                "email": email,
                "role": role,
                "password_hash": password_hash,
                "status": "Under Review"
            }
            
            user_response = supabase.table("users").insert(user_payload).execute()
            if not user_response.data:
                raise Exception("Failed to insert record into users table")
            
            new_user_id = user_response.data[0]['id']
            profile_payload = {"user_id": new_user_id, "role": role}
            
            if role == 'farmer':
                profile_payload.update({
                    "farmer_barangay": validated_data['farmer_barangay'],
                    "farm_size": validated_data.get('farm_size')
                })
            elif role == 'lgu':
                profile_payload.update({
                    "agency_office": validated_data['lgu_agency'],
                    "position_title": validated_data['lgu_position'],
                    "employee_id": validated_data['lgu_employee_id'],
                    "office_email": validated_data.get('lgu_office_email'),
                    "jurisdiction": validated_data['lgu_jurisdiction']
                })
            elif role == 'agri_expert':
                profile_payload.update({
                    "agency_office": validated_data['agri_office_name'],
                    "position_title": validated_data['agri_position'],
                    "employee_id": validated_data['agri_employee_id'],
                    "office_email": validated_data.get('agri_office_email'),
                    "jurisdiction": validated_data['agri_jurisdiction']
                })
            
            supabase.table("profiles").insert(profile_payload).execute()
            flash(f"Account created successfully! Your account is pending approval.", "success")
            return redirect(url_for('account_notice'))
        
        except ValidationError as e:
            flash(str(e), "error")
            return redirect(url_for('signup'))
        except Exception as e:
            flash("Signup failed. Please check your information and try again.", "error")
            return redirect(url_for('signup'))
    
    return render_template('signup.html')

@app.route('/account-notice')
def account_notice():
    return render_template('notice.html')



@app.route('/dashboard')
def dashboard():
    """Central routing hub to dispatch logged-in sessions to role-specific views"""
    user_id = session.get('user_id')
    user_role = normalize_role(session.get('user_role'))
    
    if not user_id:
        return redirect(url_for('login'))
        
    if user_role == 'farmer':
        return redirect(url_for('farmer_dashboard'))
    elif user_role == 'agri_expert':
        return redirect(url_for('agriculturist_dashboard'))
    elif user_role == 'lgu':
        return redirect(url_for('lgu_dashboard'))
    elif user_role == 'admin':
        return redirect(url_for('admin_user_management'))
        
    return render_template('404.html')

def calculate_environmental_risk(temp, humidity, rainfall):
    """Rule-based engine returning high-contrast solid color spaces for dark container themes"""
    if temp == "--" or humidity == "--":
        return {
            "level": "Unknown", 
            "color": "#475569", 
            "bg": "#f1f5f9", 
            "border": "#cbd5e1", 
            "text": "Risk assessment unavailable offline."
        }
    
    try:
        t = float(temp)
        h = float(humidity)
    except (ValueError, TypeError):
        return {
            "level": "Moderate", 
            "color": "#b45309", 
            "bg": "#fef3c7", 
            "border": "#fde68a", 
            "text": "Standard environmental monitoring active."
        }

    if t >= 32 and h >= 75:
        return {
            "level": "High Risk",
            "color": "#991b1b",
            "bg": "#fee2e2",
            "border": "#fca5a5",
            "text": "<strong>High Risk</strong>: Accelerated breeding climate detected for both Brontispa and Rhinoceros Beetles. Inspect young fronds immediately."
        }
    elif h >= 80:
        return {
            "level": "Moderate Risk",
            "color": "#92400e",
            "bg": "#fef3c7",
            "border": "#fde68a",
            "text": "<strong>Moderate Risk</strong>: High moisture levels favor Rhinoceros Beetle breeding nests and localized larval development."
        }
    elif t >= 31 and h < 65:
        return {
            "level": "Moderate Risk",
            "color": "#92400e",
            "bg": "#fef3c7",
            "border": "#fde68a",
            "text": "<strong>Moderate Risk</strong>: Warm, dry foliage layout accelerates early-stage Brontispa leaf-incubation cycles."
        }
    else:
        return {
            "level": "Low Risk",
            "color": "#065f46",
            "bg": "#d1fae5",
            "border": "#a7f3d0",
            "text": "<strong>Low Risk</strong>: Current climate conditions are within baseline stability parameters for pest development."
        }


def _format_report_confidence(value):
    if value is None:
        return "--"

    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return "--"
        if stripped.endswith("%"):
            return stripped
        try:
            numeric_value = float(stripped)
        except ValueError:
            return stripped
    else:
        try:
            numeric_value = float(value)
        except (TypeError, ValueError):
            return str(value)

    if numeric_value <= 1:
        numeric_value *= 100

    return f"{round(numeric_value)}%"


def _normalize_string_list(value):
    """Normalize recommendations: parse JSON strings, clean list items"""
    if isinstance(value, str):
        # Try to parse as JSON first (stored as string in database)
        try:
            parsed = json.loads(value)
            if isinstance(parsed, list):
                return [str(item).strip() for item in parsed if str(item).strip()]
        except (json.JSONDecodeError, TypeError):
            pass
        # If not JSON, treat as single string
        cleaned = value.strip()
        return [cleaned] if cleaned else []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


def _format_report_location(item):
    latitude = item.get("latitude")
    longitude = item.get("longitude")

    coordinate_label = ""
    try:
        if latitude is not None and longitude is not None:
            coordinate_label = f"{float(latitude):.4f}, {float(longitude):.4f}"
    except (TypeError, ValueError):
        coordinate_label = ""

    full_location = ", ".join(
        filter(
            None,
            [item.get("barangay"), item.get("municipality"), item.get("province")],
        )
    )

    return full_location or coordinate_label or "No location logged"


def _fetch_report_supporting_images(report_ids):
    report_ids = [str(report_id) for report_id in report_ids if report_id is not None]
    if not report_ids:
        return {}

    try:
        response = (
            supabase.table("report_supporting_images")
            .select("report_id, image_url")
            .in_("report_id", report_ids)
            .order("uploaded_at", desc=False)
            .execute()
        )
    except Exception as error:
        logger.warning(f"Unable to load supporting images: {str(error)}")
        return {}

    grouped_images = {}
    for row in getattr(response, "data", None) or []:
        report_id = str(row.get("report_id") or "").strip()
        if not report_id:
            continue
        grouped_images.setdefault(report_id, []).append(resolve_report_image_url(row.get("image_url") or ""))

    return grouped_images


def _fetch_weather_snapshot(latitude, longitude):
    try:
        if latitude is None or longitude is None:
            raise ValueError("Missing coordinates")

        lat_value = float(latitude)
        lng_value = float(longitude)
        weather_url = (
            "https://api.open-meteo.com/v1/forecast"
            f"?latitude={lat_value}&longitude={lng_value}"
            "&current=temperature_2m,relative_humidity_2m,precipitation,wind_speed_10m"
        )
        response = requests.get(weather_url, timeout=10)
        if response.status_code != 200:
            raise RuntimeError(f"Weather service returned {response.status_code}")

        current_data = response.json().get("current", {})
        temperature = current_data.get("temperature_2m")
        humidity = current_data.get("relative_humidity_2m")
        rainfall = current_data.get("precipitation", 0.0)
        wind = current_data.get("wind_speed_10m")

        return {
            "location": f"{lat_value:.4f}, {lng_value:.4f}",
            "temp": round(temperature) if temperature is not None else "--",
            "humidity": round(humidity) if humidity is not None else "--",
            "rainfall": rainfall if rainfall is not None else "--",
            "wind": round(wind) if wind is not None else "--",
            "is_down": False,
        }
    except Exception as error:
        logger.warning(f"Weather snapshot unavailable: {str(error)}")
        return {
            "location": "Weather unavailable",
            "temp": "--",
            "humidity": "--",
            "rainfall": "--",
            "wind": "--",
            "is_down": True,
        }


def _build_report_modal_payload(item, *, supporting_images=None, weather=None, default_status="Under Review"):
    if supporting_images is None:
        supporting_images = []
    if weather is None:
        weather = {
            "location": "Weather unavailable",
            "temp": "--",
            "humidity": "--",
            "rainfall": "--",
            "wind": "--",
            "is_down": True,
        }

    report_id = item.get("id")
    raw_initial_recommendations = item.get("initial_recommendations") or []
    raw_expert_recommendations = item.get("expert_recommendations") or []
    
    visit_chats = item.get("visit_chats") or []
    chat_count = visit_chats[0].get("count", 0) if visit_chats and isinstance(visit_chats, list) and isinstance(visit_chats[0], dict) else 0

    notes = item.get("farmer_notes") or item.get("notes") or ""
    if notes:
        notes = notes.split("\n\nFarmer requested a visit.")[0]
        notes = notes.split("\n\nVisit scheduled.")[0]
        notes = notes.split("\n\nVisit completed.")[0]
        notes = notes.split("\n\nFarmer requested reschedule.")[0]
        notes = notes.split("\n\nVisit canceled.")[0]
        notes = notes.strip()
    if not notes:
        notes = "No notes logged."

    return {
        "id": report_id,
        "chat_count": chat_count,
        "pest": item.get("pest_type") or item.get("pest") or "Unknown Pest",
        "confidence": _format_report_confidence(item.get("confidence")),
        "status": normalize_report_status(item.get("status"), default=default_status),
        "timestamp": format_report_timestamp(item.get("created_at") or item.get("submitted_at") or item.get("photo_taken_at")),
        "date": format_report_date(item.get("created_at") or item.get("submitted_at") or item.get("photo_taken_at")),
        "farmer": item.get("farmer_name") or item.get("farmer") or "Farmer",
        "notes": notes,
        "location_text": _format_report_location(item),
        "gps": {
            "latitude": item.get("latitude"),
            "longitude": item.get("longitude"),
            "accuracy": item.get("gps_accuracy") or "",
            "source": item.get("location_source") or "",
        },
        "primary_image": resolve_report_image_url(item.get("image_url") or item.get("img") or ""),
        "additional_images": [img for img in supporting_images if img],
        "initial_recommendations": _normalize_string_list(raw_initial_recommendations),
        "expert_recommendations": _normalize_string_list(raw_expert_recommendations),
        "weather": weather,
        "weather_status": "down" if weather.get("is_down") else "ready",
    }

# Farmer
@app.route('/farmer/dashboard')
def farmer_dashboard():
    user_id = session.get('user_id')
    user_role = normalize_role(session.get('user_role'))
    
    if not user_id or user_role != 'farmer':
        flash("Unauthorized access path.", "error")
        return redirect(url_for('login'))
        
    try:
        # Fetch the real profile name details from cloud instance
        user_query = supabase.table("users").select("first_name, last_name").eq("id", user_id).execute()
        user_name = f"{user_query.data[0].get('first_name', '')} {user_query.data[0].get('last_name', '')}".strip() if user_query.data else "Farmer"
        
        reports_response = supabase.table('reports').select('*, visit_chats(count)').eq('user_id', user_id).order('created_at', desc=True).execute()
        reports = getattr(reports_response, 'data', []) or []

        total_cases = len(reports)
        pending_cases = sum(1 for report in reports if is_pending_report_status(report.get('status')))
        resolved_cases = sum(1 for report in reports if is_resolved_report_status(report.get('status')))

        metrics = {
            "total_cases": total_cases,
            "pending_cases": pending_cases,
            "resolved_cases": resolved_cases
        }
        chart_data = build_dashboard_chart_payload(reports)
        
        weather = {
            "location": "San Pablo City, Laguna",
            "temp": "--",
            "humidity": "--",
            "rainfall": "--",
            "wind": "--",
            "is_down": False
        }
        
        latitude = 14.0708
        longitude = 121.3256
        weather_url = f"https://api.open-meteo.com/v1/forecast?latitude={latitude}&longitude={longitude}&current=temperature_2m,relative_humidity_2m,precipitation,wind_speed_10m"
        
        try:
            response = requests.get(weather_url, timeout=4)
            if response.status_code == 200:
                data = response.json()
                current_data = data.get("current", {})
                weather["temp"] = round(current_data.get("temperature_2m"))
                weather["humidity"] = current_data.get("relative_humidity_2m")
                weather["rainfall"] = current_data.get("precipitation", 0.0)
                weather["wind"] = round(current_data.get("wind_speed_10m"))
            else:
                weather["is_down"] = True
        except Exception as weather_err:
            weather["is_down"] = True
            logger.error(f"Weather diagnostic error: {str(weather_err)}")

        risk = calculate_environmental_risk(weather["temp"], weather["humidity"], weather["rainfall"])

        return render_template('farmer_dashboard.html', user_name=user_name, metrics=metrics, weather=weather, risk=risk, chart_data=chart_data)
        
    except Exception as e:
        logger.error(f"Dashboard routing exception: {str(e)}")
        return redirect(url_for('logout'))

@app.route('/farmer/scan')
def farmer_scan():
    user_id = session.get('user_id')
    user_role = normalize_role(session.get('user_role'))
    
    if not user_id or user_role != 'farmer':
        flash("Unauthorized access path. Please log in.", "error")
        return redirect(url_for('login'))
        
    try:
        user_query = supabase.table("users").select("first_name, last_name").eq("id", user_id).execute()
        user_name = f"{user_query.data[0].get('first_name', '')} {user_query.data[0].get('last_name', '')}".strip() if user_query.data else "Farmer"

        reports_response = supabase.table('reports').select('*, visit_chats(count)').eq('user_id', user_id).order('created_at', desc=True).execute()
        recent_reports = []
        for item in getattr(reports_response, 'data', []) or []:
            created_raw = item.get('submitted_at') or item.get('created_at') or ''
            created_label = format_report_timestamp(created_raw)

            recent_reports.append({
                'id': item.get('id'),
                'pest': item.get('pest_type') or 'Unknown Pest',
                'confidence': f"{int(float(item.get('confidence', 0)))}%" if item.get('confidence') else '90%',
                'raw_timestamp': created_label,
                'time_string': created_label,
                'timestamp': created_label,
                'status': normalize_report_status(item.get('status'), default='Pending')
            })

        return render_template('farmer_scan.html', user_name=user_name, recent_reports=recent_reports[:6])
    except Exception as e:
        logger.error(f"Scan Pest routing exception: {str(e)}")
        return redirect(url_for('logout'))

@app.route('/farmer/predict', methods=['POST'])
def farmer_predict():
    """Process image prediction using the full inference pipeline"""
    import base64
    from io import BytesIO
    from app.inference_pipeline import run_full_inference_pipeline
    
    user_id = session.get('user_id')
    user_role = normalize_role(session.get('user_role'))
    
    if not user_id or user_role != 'farmer':
        return jsonify({'success': False, 'error': 'Unauthorized'}), 403
    
    try:
        # Debug: log incoming files/form keys
        try:
            logger.info(f"Files: {list(request.files.keys())}")
            logger.info(f"Form fields: {list(request.form.keys())}")
        except Exception:
            logger.warning('Failed to log incoming request file/form keys')

        # Require multipart file upload only for prediction
        image_file = request.files.get('image_file')
        if not image_file:
            return jsonify({"error": "No image file uploaded"}), 400

        try:
            image_bytes = image_file.read()
            image = Image.open(BytesIO(image_bytes)).convert("RGB")
        except Exception as e:
            logger.error(f"Image file decoding error: {str(e)}")
            return jsonify({'success': False, 'error': 'Invalid uploaded image file'}), 400
        
        pest_model_path = resolve_model_path(
            'PEST_MODEL_PATH',
            'pest_classifier_YOLO.tflite'
        )

        if not os.path.exists(pest_model_path):
            logger.error(f"Model not found: {pest_model_path}")
            return jsonify({'success': False, 'error': f'Model not found: {pest_model_path}'}), 500

        result = run_full_inference_pipeline(
            image,
            '',
            pest_model_path,
            None,
            use_lite_size=False
        )

        if not result.get('success', False):
            logger.warning(f"Inference pipeline failed: {result.get('error', 'Unknown error')}")
            return jsonify({
                'success': False,
                'error': result.get('error', 'Failed to process image'),
                'pest': 'Unknown',
                'severity': 'Not available'
            }), 400

        severity_confidence = result.get('severity_confidence')
        if severity_confidence is not None:
            severity_confidence = round(severity_confidence * 100, 1)

        response = {
            'success': True,
            'pest': result['pest'],
            'severity': result.get('severity', 'Not available'),
            'pest_confidence': round(result['pest_confidence'] * 100, 1),
            'severity_confidence': severity_confidence,
            'damage_percentage': result.get('damage_percentage'),
            'recommendations': result['recommendations'],
            'risk_level': result['risk_level'],
            'urgency': result['urgency'],
            'risk_factors': result['risk_factors']
        }
        
        logger.info(f"Prediction successful: {result['pest']} - {result['severity']}")
        return jsonify(response), 200
        
    except Exception as e:
        logger.error(f"Prediction route error: {str(e)}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/farmer/reports')
def farmer_reports():
    user_id = session.get('user_id')
    user_role = normalize_role(session.get('user_role'))
    
    if not user_id or user_role != 'farmer':
        flash("Unauthorized access path. Please log in.", "error")
        return redirect(url_for('login'))

    user_name = "Farmer"
    reports_data = []

    try:
        user_query = supabase.table("users").select("first_name, last_name").eq("id", user_id).execute()
        if getattr(user_query, "data", None):
            user_name = f"{user_query.data[0].get('first_name', '')} {user_query.data[0].get('last_name', '')}".strip() or "Farmer"
    except Exception as e:
        logger.warning(f"Unable to load farmer profile for reports page: {str(e)}")

    try:
        reports_response = supabase.table("reports").select("*, visit_chats(count)").eq("user_id", user_id).order("created_at", desc=True).execute()
        report_rows = getattr(reports_response, "data", []) or []
        logger.info(f"[FARMER_REPORTS] User {user_id}: Query returned {len(report_rows)} reports")
        for idx, r in enumerate(report_rows[:3]):
            logger.info(f"[FARMER_REPORTS]   [{idx}] ID={r.get('id')}, user_id={r.get('user_id')}, pest={r.get('pest_type')}")
        supporting_map = _fetch_report_supporting_images([item.get("id") for item in report_rows])

        for item in report_rows:
            payload = _build_report_modal_payload(
                item,
                supporting_images=supporting_map.get(str(item.get("id")), []),
                weather=_fetch_weather_snapshot(item.get("latitude"), item.get("longitude")),
                default_status="Pending Assessment",
            )

            reports_data.append({
                **payload,
                "img": payload["primary_image"],
                "full_location": payload["location_text"],
                "timestamp": payload["timestamp"],
                "date": payload["date"],
            })
    except Exception as e:
        logger.warning(f"Unable to load reports data for reports page: {str(e)}")

    try:
        return render_template('farmer_reports.html', user_name=user_name, reports_data=reports_data)
    except Exception as e:
        logger.exception("Failed to render farmer reports page")
        return render_template('farmer_reports.html', user_name=user_name, reports_data=[])

@app.route('/farmer/drafts')
def farmer_drafts():
    user_id = session.get('user_id')
    user_role = normalize_role(session.get('user_role'))
    if not user_id or user_role != 'farmer':
        flash("Unauthorized access path. Please log in.", "error")
        return redirect(url_for('login'))

    user_name = "Farmer"
    try:
        user_query = supabase.table("users").select("first_name, last_name").eq("id", user_id).execute()
        if getattr(user_query, 'data', None):
            user_name = f"{user_query.data[0].get('first_name', '')} {user_query.data[0].get('last_name', '')}".strip() or "Farmer"
    except Exception as e:
        logger.warning(f"Unable to load farmer profile for drafts page: {str(e)}")

    return render_template('farmer_drafts.html', user_name=user_name)

# Agriculturist
@app.route('/agriculturist/dashboard')
def agriculturist_dashboard():
    user_id = session.get('user_id')
    user_role = normalize_role(session.get('user_role'))
    
    if not user_id or user_role != 'agri_expert':
        flash("Unauthorized access path.", "error")
        return redirect(url_for('login'))
        
    try:
        # Fetch the real profile name details
        user_query = supabase.table("users").select("first_name, last_name").eq("id", user_id).execute()
        user_name = f"{user_query.data[0].get('first_name', '')} {user_query.data[0].get('last_name', '')}".strip() if user_query.data else "Agriculturist"
        
        reports_response = supabase.table('reports').select('*, visit_chats(count)').order('created_at', desc=True).execute()
        reports = getattr(reports_response, 'data', []) or []

        total_cases = len(reports)
        pending_cases = sum(1 for report in reports if is_pending_report_status(report.get('status')))
        resolved_cases = sum(1 for report in reports if is_resolved_report_status(report.get('status')))
        affected_areas = len({str(report.get('barangay') or '').strip() for report in reports if str(report.get('barangay') or '').strip()})

        metrics = {
            "total_cases": total_cases,
            "pending_cases": pending_cases,
            "resolved_cases": resolved_cases,
            "affected_areas": affected_areas
        }
        chart_data = build_dashboard_chart_payload(reports)
        
        weather = {
            "location": "San Pablo City, Laguna",
            "temp": "--",
            "humidity": "--",
            "rainfall": "--",
            "wind": "--",
            "is_down": False
        }
        
        latitude = 14.0708
        longitude = 121.3256
        weather_url = f"https://api.open-meteo.com/v1/forecast?latitude={latitude}&longitude={longitude}&current=temperature_2m,relative_humidity_2m,precipitation,wind_speed_10m"
        
        try:
            response = requests.get(weather_url, timeout=4)
            if response.status_code == 200:
                data = response.json()
                current_data = data.get("current", {})
                weather["temp"] = round(current_data.get("temperature_2m"))
                weather["humidity"] = current_data.get("relative_humidity_2m")
                weather["rainfall"] = current_data.get("precipitation", 0.0)
                weather["wind"] = round(current_data.get("wind_speed_10m"))
            else:
                weather["is_down"] = True
        except Exception as weather_err:
            weather["is_down"] = True
            logger.error(f"Weather diagnostic error: {str(weather_err)}")

        risk = calculate_environmental_risk(weather["temp"], weather["humidity"], weather["rainfall"])

        return render_template('agriculturist_dashboard.html', user_name=user_name, metrics=metrics, weather=weather, risk=risk, chart_data=chart_data)
        
    except Exception as e:
        logger.error(f"Agriculturist dashboard routing exception: {str(e)}")
        return redirect(url_for('logout'))

@app.route('/lgu/dashboard')
def lgu_dashboard():
    user_id = session.get('user_id')
    user_role = normalize_role(session.get('user_role'))
    
    if not user_id or user_role != 'lgu':
        flash("Unauthorized access path.", "error")
        return redirect(url_for('login'))
        
    try:
        user_query = supabase.table("users").select("first_name, last_name").eq("id", user_id).execute()
        user_name = f"{user_query.data[0].get('first_name', '')} {user_query.data[0].get('last_name', '')}".strip() if user_query.data else "LGU Officer"
        
        reports_response = supabase.table('reports').select('*, visit_chats(count)').order('created_at', desc=True).execute()
        reports = getattr(reports_response, 'data', []) or []

        total_cases = len(reports)
        pending_cases = sum(1 for report in reports if is_pending_report_status(report.get('status')))
        resolved_cases = sum(1 for report in reports if is_resolved_report_status(report.get('status')))
        affected_areas = len({str(report.get('barangay') or '').strip() for report in reports if str(report.get('barangay') or '').strip()})

        metrics = {
            "total_cases": total_cases,
            "pending_cases": pending_cases,
            "resolved_cases": resolved_cases,
            "affected_areas": affected_areas
        }
        chart_data = build_dashboard_chart_payload(reports)
        
        weather = {
            "location": "San Pablo City, Laguna",
            "temp": "--",
            "humidity": "--",
            "rainfall": "--",
            "wind": "--",
            "is_down": False
        }
        
        latitude = 14.0708
        longitude = 121.3256
        weather_url = f"https://api.open-meteo.com/v1/forecast?latitude={latitude}&longitude={longitude}&current=temperature_2m,relative_humidity_2m,precipitation,wind_speed_10m"
        
        try:
            response = requests.get(weather_url, timeout=4)
            if response.status_code == 200:
                data = response.json()
                current_data = data.get("current", {})
                weather["temp"] = round(current_data.get("temperature_2m"))
                weather["humidity"] = current_data.get("relative_humidity_2m")
                weather["rainfall"] = current_data.get("precipitation", 0.0)
                weather["wind"] = round(current_data.get("wind_speed_10m"))
            else:
                weather["is_down"] = True
        except Exception as weather_err:
            weather["is_down"] = True
            logger.error(f"Weather diagnostic error: {str(weather_err)}")

        risk = calculate_environmental_risk(weather["temp"], weather["humidity"], weather["rainfall"])

        return render_template('lgu_dashboard.html', user_name=user_name, metrics=metrics, weather=weather, risk=risk, chart_data=chart_data)
        
    except Exception as e:
        logger.error(f"LGU dashboard routing exception: {str(e)}")
        return redirect(url_for('logout'))

@app.route('/lgu/analytics')
def lgu_analytics():
    user_id = session.get('user_id')
    user_role = normalize_role(session.get('user_role'))
    
    if not user_id or user_role != 'lgu':
        flash("Unauthorized access path.", "error")
        return redirect(url_for('login'))

    try:
        user_query = supabase.table("users").select("first_name, last_name").eq("id", user_id).execute()
        user_name = f"{user_query.data[0].get('first_name', '')} {user_query.data[0].get('last_name', '')}".strip() if user_query.data else "LGU Officer"

        reports_response = supabase.table('reports').select('*, visit_chats(count)').order('created_at', desc=True).execute()
        reports = getattr(reports_response, 'data', []) or []

        total_cases = len(reports)
        pending_cases = sum(1 for report in reports if is_pending_report_status(report.get('status')))
        resolved_cases = sum(1 for report in reports if is_resolved_report_status(report.get('status')))
        affected_areas = len({str(report.get('barangay') or '').strip() for report in reports if str(report.get('barangay') or '').strip()})

        metrics = {
            "total_cases": total_cases,
            "pending_cases": pending_cases,
            "resolved_cases": resolved_cases,
            "affected_areas": affected_areas
        }
        chart_data = build_dashboard_chart_payload(reports)

        weather = {
            "location": "San Pablo City, Laguna",
            "temp": "--",
            "humidity": "--",
            "rainfall": "--",
            "wind": "--",
            "is_down": False
        }
        
        latitude = 14.0708
        longitude = 121.3256
        weather_url = f"https://api.open-meteo.com/v1/forecast?latitude={latitude}&longitude={longitude}&current=temperature_2m,relative_humidity_2m,precipitation,wind_speed_10m"
        
        try:
            response = requests.get(weather_url, timeout=4)
            if response.status_code == 200:
                data = response.json()
                current_data = data.get("current", {})
                weather["temp"] = round(current_data.get("temperature_2m"))
                weather["humidity"] = current_data.get("relative_humidity_2m")
                weather["rainfall"] = current_data.get("precipitation", 0.0)
                weather["wind"] = round(current_data.get("wind_speed_10m"))
            else:
                weather["is_down"] = True
        except Exception as weather_err:
            weather["is_down"] = True
            logger.error(f"Weather diagnostic error: {str(weather_err)}")

        risk = calculate_environmental_risk(weather["temp"], weather["humidity"], weather["rainfall"])

        return render_template('lgu_analytics.html', user_name=user_name, metrics=metrics, weather=weather, risk=risk, chart_data=chart_data)

    except Exception as e:
        logger.error(f"LGU analytics routing exception: {str(e)}")
        return redirect(url_for('logout'))

@app.route('/debug/reports')
def debug_reports():
    """Debug endpoint to see all reports in database"""
    try:
        reports_response = supabase.table("reports").select("*").order("created_at", desc=True).limit(20).execute()
        reports = reports_response.data or []
        return jsonify({
            "total": len(reports),
            "reports": [{"id": r.get("id"), "pest_type": r.get("pest_type"), "status": r.get("status"), "created_at": r.get("created_at")} for r in reports]
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/agriculturist/pending')
def agriculturist_pending():
    """Fetches active workflow reports from Supabase and renders the active reports queue."""
    user_id = session.get('user_id')
    user_role = normalize_role(session.get('user_role'))
    
    if not user_id or user_role != 'agri_expert':
        flash("Unauthorized access path.", "error")
        return redirect(url_for('login'))
        
    try:
        # Load user profile for layout presentation layer
        user_query = supabase.table("users").select("first_name, last_name").eq("id", user_id).execute()
        user_name = f"{user_query.data[0].get('first_name', '')} {user_query.data[0].get('last_name', '')}".strip() if user_query.data else "Agriculturist"
        
        # Pull reports in active workflow statuses from database
        reports_response = supabase.table("reports")\
            .select("*, visit_chats(count)")\
            .order("created_at", desc=True)\
            .execute()
            
        raw_reports = reports_response.data or []
        logger.info(f"[ACTIVE] Fetched {len(raw_reports)} total reports from database")
        for r in raw_reports[:3]:  # Log first 3 reports
            logger.info(f"[ACTIVE] Report: id={r.get('id')}, status={r.get('status')}, pest={r.get('pest_type')}")
        
        supporting_map = _fetch_report_supporting_images([item.get("id") for item in raw_reports])
        active_reports_list = []
        
        for item in raw_reports:
            status = item.get("status")
            if is_resolved_report_status(status):
                logger.debug(f"[ACTIVE] Skipping report {item.get('id')}: status={status} (resolved)")
                continue
            payload = _build_report_modal_payload(
                item,
                supporting_images=supporting_map.get(str(item.get("id")), []),
                weather=_fetch_weather_snapshot(item.get("latitude"), item.get("longitude")),
                default_status="Pending Assessment",
            )

            active_reports_list.append({
                **payload,
                "location": payload["location_text"],
                "full_location": payload["location_text"],
                "farmer_notes": payload["notes"],
                "img": payload["primary_image"],
            })
        
        logger.info(f"[ACTIVE] Returning {len(active_reports_list)} active reports to template")
            
        return render_template(
            'agriculturist_pending_reports.html', 
            user_name=user_name, 
            pending_reports=active_reports_list
        )
        
    except Exception as e:
        logger.error(f"Error serving agriculturist pending list module: {str(e)}")
        flash("An alignment error occurred reading data snapshots.", "error")
        return redirect(url_for('agriculturist_dashboard'))

@app.route('/agriculturist/reviewed')
def agriculturist_reviewed():
    """Fetches reports with 'Recommendation Issued' status from Supabase and renders the archive."""
    user_id = session.get('user_id')
    user_role = normalize_role(session.get('user_role'))
    
    if not user_id or user_role != 'agri_expert':
        flash("Unauthorized access path.", "error")
        return redirect(url_for('login'))
        
    try:
        # Load user profile for layout presentation layer
        user_query = supabase.table("users").select("first_name, last_name").eq("id", user_id).execute()
        user_name = f"{user_query.data[0].get('first_name', '')} {user_query.data[0].get('last_name', '')}".strip() if user_query.data else "Agriculturist"
        
        # Pull reports that have already been reviewed by an expert from the database
        reports_response = supabase.table("reports")\
            .select("*")\
            .order("updated_at", desc=True)\
            .execute()
            
        raw_reports = reports_response.data or []
        supporting_map = _fetch_report_supporting_images([item.get("id") for item in raw_reports])
        reviewed_reports_list = []
        
        for item in raw_reports:
            if not is_resolved_report_status(item.get("status")):
                continue
            payload = _build_report_modal_payload(
                item,
                supporting_images=supporting_map.get(str(item.get("id")), []),
                weather=_fetch_weather_snapshot(item.get("latitude"), item.get("longitude")),
                default_status="Resolved",
            )

            reviewed_reports_list.append({
                **payload,
                "location": payload["location_text"],
                "full_location": payload["location_text"],
                "farmer_notes": payload["notes"],
                "img": payload["primary_image"],
                "expert_recommendation": payload["expert_recommendations"] or ["No technical recommendations filed."],
            })
            
        return render_template(
            'agriculturist_reviewed_reports.html', 
            user_name=user_name, 
            reviewed_reports=reviewed_reports_list
        )
        
    except Exception as e:
        logger.error(f"Error serving agriculturist reviewed list module: {str(e)}")
        flash("An alignment error occurred reading data snapshots.", "error")
        return redirect(url_for('agriculturist_dashboard'))

@app.route('/agriculturist/map')
def agriculturist_map():
    """Fetches incident coordinates and location data aggregates to render the geospatial map."""
    user_id = session.get('user_id')
    user_role = normalize_role(session.get('user_role'))
    
    if not user_id or user_role != 'agri_expert':
        flash("Unauthorized access path.", "error")
        return redirect(url_for('login'))
        
    try:
        search_query = request.args.get("search", "").strip()
        pest_filter = (request.args.get("pest", "all") or "all").strip() or "all"

        # Load user profile for layout presentation layer
        user_query = supabase.table("users").select("first_name, last_name").eq("id", user_id).execute()
        user_name = f"{user_query.data[0].get('first_name', '')} {user_query.data[0].get('last_name', '')}".strip() if user_query.data else "Agriculturist"
        
        # Retrieve all spatial records containing geographical metrics
        reports_response = supabase.table("reports")\
            .select("id, barangay, municipality, province, latitude, longitude, pest_type, status")\
            .order("created_at", desc=True)\
            .execute()
            
        raw_reports = reports_response.data or []
        map_reports_list = []
        
        # Aggregate tracking data parameters
        for item in raw_reports:
            try:
                lat = float(item.get("latitude"))
                lng = float(item.get("longitude"))
            except (ValueError, TypeError):
                continue  # Skip records missing physical coordinates
                
            map_reports_list.append({
                "id": item.get("id"),
                "barangay": item.get("barangay") or "Unknown Sector",
                "municipality": item.get("municipality") or "San Pablo City",
                "province": item.get("province") or "Laguna",
                "latitude": lat,
                "longitude": lng,
                "pest_type": item.get("pest_type") or "Unknown Pest",
                "status": normalize_report_status(item.get("status"), default="Under Review"),
                "cases_count": 1 # Serves as baseline cluster weight variable
            })

        filtered_map_reports = filter_map_reports(map_reports_list, search_query=search_query, pest_filter=pest_filter)
        recent_map_reports = limit_recent_records(filtered_map_reports, 5)
            
        return render_template(
            'map_view.html', 
            user_name=user_name, 
            map_reports=filtered_map_reports,
            recent_map_reports=recent_map_reports,
            search_query=search_query,
            pest_filter=pest_filter
        )
        
    except Exception as e:
        logger.error(f"Error serving geospatial map canvas metrics: {str(e)}")
        flash("An alignment error occurred reading spatial coordinates.", "error")
        return redirect(url_for('agriculturist_dashboard'))

@app.route('/farmer/follow-up-report', methods=['POST'])
def farmer_follow_up_report():
    """Reopen a previously reviewed report when the farmer submits a new update."""
    user_id = _get_current_app_user_id()
    user_role = normalize_role(session.get('user_role'))

    if not user_id or user_role != 'farmer':
        return jsonify({'success': False, 'message': 'Unauthorized user session'}), 403

    try:
        data = request.get_json(silent=True) or {}
        report_id = data.get('report_id') or request.form.get('report_id')
        follow_up_notes = (data.get('notes') or request.form.get('notes') or '').strip()

        if not report_id:
            return jsonify({'success': False, 'message': 'Missing report reference'}), 400

        existing_response = supabase.table('reports').select('*').eq('id', report_id).execute()
        existing_rows = getattr(existing_response, 'data', None) or []
        existing_report = existing_rows[0] if existing_rows else {}
        if not existing_report:
            return jsonify({'success': False, 'message': 'Report not found'}), 404

        existing_notes = str(existing_report.get('farmer_notes') or '').strip()
        if follow_up_notes:
            combined_notes = "\n\n".join(filter(None, [existing_notes, f"Follow-up update: {follow_up_notes}"]))
        else:
            combined_notes = existing_notes

        update_response = _update_report_workflow(
            report_id,
            'Under Review',
            note=f"Follow-up update: {follow_up_notes}",
            extra_updates={
                'farmer_notes': combined_notes,
                'expert_recommendations': [],
                'reviewed_by_id': None,
            },
        )

        if getattr(update_response, 'error', None):
            logger.error(f"Follow-up report update failed: {update_response.error}")
            return jsonify({'success': False, 'message': 'The report could not be reopened for review.'}), 500

        logger.info(f"Report ID #{report_id} reopened for follow-up review by farmer #{user_id}.")
        return jsonify({
            'success': True,
            'message': 'Your update has been submitted and the report has been sent back for review.',
        })

    except Exception as e:
        logger.error(f"Error reopening report for follow-up: {str(e)}")
        return jsonify({'success': False, 'message': 'The follow-up could not be saved.'}), 500
    
@app.route('/agriculturist/submit-assessment', methods=['POST'])
def agriculturist_submit_assessment():
    """Save the agriculturist assessment notes and advance the report to assessment issued."""
    user_id = _get_current_app_user_id()
    user_role = normalize_role(session.get('user_role'))

    if not user_id or user_role != 'agri_expert':
        return jsonify({'success': False, 'message': 'Unauthorized user session'}), 403

    try:
        payload = request.get_json(silent=True) or {}
        report_id = payload.get('report_id') or request.form.get('report_id')
        assessment_notes = (
            payload.get('assessment_notes')
            or payload.get('recommendation')
            or request.form.get('assessment_notes')
            or request.form.get('recommendation', '')
        ).strip()

        if not report_id or not assessment_notes:
            return jsonify({'success': False, 'message': 'Assessment notes are required.'}), 400

        update_response = _update_report_workflow(
            report_id,
            'assessment_issued',
            extra_updates={
                'expert_recommendations': [assessment_notes],
                'reviewed_by_id': user_id,
            },
        )

        if getattr(update_response, 'error', None):
            logger.error(f"Assessment update failed: {update_response.error}")
            return jsonify({'success': False, 'message': 'The assessment could not be saved.'}), 500

        logger.info(f"Report ID #{report_id} assessment logged by expert #{user_id}.")
        return jsonify({'success': True, 'message': 'Assessment notes saved successfully.'})
    except Exception as e:
        logger.error(f"Error saving assessment: {str(e)}")
        return jsonify({'success': False, 'message': 'The assessment could not be saved.'}), 500


@app.route('/farmer/submit-assessment-feedback', methods=['POST'])
def farmer_submit_assessment_feedback():
    """Let the farmer confirm whether the assessment resolved the issue or request a visit."""
    user_id = _get_current_app_user_id()
    user_role = normalize_role(session.get('user_role'))

    if not user_id or user_role != 'farmer':
        return jsonify({'success': False, 'message': 'Unauthorized user session'}), 403

    try:
        payload = request.get_json(silent=True) or {}
        report_id = payload.get('report_id') or request.form.get('report_id')
        confirmation = str(payload.get('confirmation') or request.form.get('confirmation') or '').strip().lower()
        reason = (payload.get('reason') or request.form.get('reason') or '').strip()

        if not report_id:
            return jsonify({'success': False, 'message': 'Missing report reference'}), 400

        if confirmation == 'resolved' or confirmation == 'yes':
            note = "Farmer confirmed the assessment resolved the issue."
            update_response = _update_report_workflow(report_id, 'resolved', note=note)
        else:
            if not reason:
                return jsonify({'success': False, 'message': 'Please provide a reason for requesting the visit.'}), 400

            update_response = _update_report_workflow(
                report_id,
                'Awaiting Confirmed Schedule',
                note=None,
                extra_updates={
                    'visit_request_reason': reason,
                    'visit_requested_at': datetime.now(UTC).isoformat(),
                },
            )
            if getattr(update_response, 'error', None):
                logger.error(f"Assessment feedback update failed: {update_response.error}")
                return jsonify({'success': False, 'message': 'The feedback could not be saved.'}), 500

            chat_insert_response = supabase.table('visit_chats').insert({
                'report_id': report_id,
                'sender_id': user_id,
                'message': reason,
            }).execute()
            if getattr(chat_insert_response, 'error', None):
                logger.warning(f"Visit chat insert failed: {chat_insert_response.error}")

        if getattr(update_response, 'error', None):
            logger.error(f"Assessment feedback update failed: {update_response.error}")
            return jsonify({'success': False, 'message': 'The feedback could not be saved.'}), 500

        return jsonify({'success': True, 'message': 'Your feedback has been saved.'})
    except Exception as e:
        logger.error(f"Error saving assessment feedback: {str(e)}")
        return jsonify({'success': False, 'message': 'The feedback could not be saved.'}), 500


@app.route('/reports/<int:report_id>/visit-discussion', methods=['GET'])
def get_visit_discussion(report_id):
    user_id = _get_current_app_user_id()
    user_role = normalize_role(session.get('user_role'))
    if not user_id or user_role not in {'farmer', 'agri_expert'}:
        return jsonify({'success': False, 'message': 'Unauthorized user session'}), 403

    payload = _fetch_visit_workflow_payload(report_id)
    report_row = payload.get('report') or {}
    is_archived = payload.get('is_archived', False)
    return jsonify({
        'success': True,
        'messages': payload.get('messages', []),
        'schedule': payload.get('schedule'),
        'schedule_stamp': payload.get('schedule_stamp', ''),
        'status': report_row.get('status') or '',
        'is_archived': is_archived,
        'visit_reschedule_reason': report_row.get('visit_reschedule_reason') or '',
        'visit_rescheduled_at': report_row.get('visit_rescheduled_at') or '',
        'visit_rescheduled_by': report_row.get('visit_rescheduled_by') or '',
        'schedule_title': payload.get('schedule_title', 'Visit Scheduled'),
    })


@app.route('/reports/<int:report_id>/visit-chat', methods=['POST'])
def save_visit_chat(report_id):
    user_id = _get_current_app_user_id()
    user_role = normalize_role(session.get('user_role'))
    if not user_id or user_role not in {'farmer', 'agri_expert'}:
        return jsonify({'success': False, 'message': 'Unauthorized user session'}), 403

    try:
        payload = request.get_json(silent=True) or {}
        message = str(payload.get('message') or request.form.get('message') or '').strip()
        if not message:
            return jsonify({'success': False, 'message': 'A message is required.'}), 400

        report_payload = _fetch_visit_workflow_payload(report_id)
        report_row = report_payload.get('report') or {}
        current_status = str(report_row.get('status') or '').strip()
        if _should_archive_visit_discussion(current_status, report_row.get('visit_reschedule_reason')):
            return jsonify({'success': False, 'message': 'The visit discussion is archived.'}), 400

        insert_response = supabase.table('visit_chats').insert({
            'report_id': report_id,
            'sender_id': user_id,
            'message': message,
        }).execute()
        if getattr(insert_response, 'error', None):
            logger.error(f"Visit chat insert failed: {insert_response.error}")
            return jsonify({'success': False, 'message': 'The message could not be saved.'}), 500

        _update_report_workflow(report_id, 'Awaiting Confirmed Schedule')
        return jsonify({'success': True, 'message': 'Message sent.'})
    except Exception as e:
        logger.error(f"Error saving visit chat: {str(e)}")
        return jsonify({'success': False, 'message': 'The message could not be saved.'}), 500


@app.route('/reports/<int:report_id>/request-reschedule', methods=['POST'])
def request_visit_reschedule(report_id):
    user_id = _get_current_app_user_id()
    user_role = normalize_role(session.get('user_role'))

    if not user_id or user_role not in {'farmer', 'agri_expert'}:
        return jsonify({'success': False, 'message': 'Unauthorized user session'}), 403

    try:
        payload = request.get_json(silent=True) or {}
        reason = str(payload.get('reason') or request.form.get('reason') or '').strip()
        if not reason:
            return jsonify({'success': False, 'message': 'Please select a reschedule reason.'}), 400

        update_response = _update_report_workflow(
            report_id,
            'Awaiting Confirmed Schedule',
            note=None,
            extra_updates={
                'visit_reschedule_reason': reason,
                'visit_rescheduled_at': datetime.now(UTC).isoformat(),
            },
        )
        if getattr(update_response, 'error', None):
            logger.error(f"Reschedule request update failed: {update_response.error}")
            return jsonify({'success': False, 'message': 'The reschedule request could not be saved.'}), 500

        message = f"Reschedule requested: {reason}"
        chat_insert_response = supabase.table('visit_chats').insert({
            'report_id': report_id,
            'sender_id': user_id,
            'message': message,
        }).execute()
        if getattr(chat_insert_response, 'error', None):
            logger.warning(f"Reschedule chat insert failed: {chat_insert_response.error}")

        return jsonify({'success': True, 'message': 'Reschedule request submitted.'})
    except Exception as e:
        logger.error(f"Error requesting visit reschedule: {str(e)}")
        return jsonify({'success': False, 'message': 'The reschedule request could not be submitted.'}), 500


@app.route('/agriculturist/finalize-visit-schedule', methods=['POST'])
def agriculturist_finalize_visit_schedule():
    user_id = _get_current_app_user_id()
    user_role = normalize_role(session.get('user_role'))

    if not user_id or user_role != 'agri_expert':
        return jsonify({'success': False, 'message': 'Unauthorized user session'}), 403

    try:
        payload = request.get_json(silent=True) or {}
        report_id = payload.get('request_id') or payload.get('report_id') or request.form.get('request_id') or request.form.get('report_id')
        confirmed_date = str(payload.get('confirmed_date') or request.form.get('confirmed_date') or '').strip()
        start_time = str(payload.get('start_time') or request.form.get('start_time') or '').strip()
        end_time = str(payload.get('end_time') or request.form.get('end_time') or '').strip()
        requested_status = str(payload.get('status') or request.form.get('status') or 'Visit Scheduled').strip() or 'Visit Scheduled'

        if not report_id:
            return jsonify({'success': False, 'message': 'Missing report reference'}), 400
        if not confirmed_date:
            return jsonify({'success': False, 'message': 'Please select a confirmed date.'}), 400
            
        try:
            confirmed_dt = datetime.strptime(confirmed_date, "%Y-%m-%d").date()
            if confirmed_dt < datetime.now().date():
                return jsonify({'success': False, 'message': 'You cannot schedule a visit in the past.'}), 400
        except ValueError:
            return jsonify({'success': False, 'message': 'Invalid date format.'}), 400

        existing_report_response = supabase.table('reports').select('visit_reschedule_reason').eq('id', report_id).execute()
        existing_report_row = (getattr(existing_report_response, 'data', None) or [{}])[0] if getattr(existing_report_response, 'data', None) else {}
        has_pending_reschedule = bool(str(existing_report_row.get('visit_reschedule_reason') or '').strip())

        try:
            normalized_start, normalized_end = _validate_time_range(start_time, end_time)
        except ValueError as e:
            return jsonify({'success': False, 'message': str(e)}), 400

        if confirmed_dt == datetime.now().date():
            if datetime.strptime(normalized_start, "%H:%M:%S").time() < datetime.now().time():
                return jsonify({'success': False, 'message': 'You cannot schedule a visit for a time that has already passed today.'}), 400

        conflict_query = supabase.table('visit_schedules').select('start_time, end_time').eq('agriculturist_id', user_id).eq('confirmed_date', confirmed_date).execute()
        conflict_rows = getattr(conflict_query, 'data', None) or []
        for row in conflict_rows:
            existing_start = _coerce_time_to_hhmmss(row.get('start_time'))
            existing_end = _coerce_time_to_hhmmss(row.get('end_time'))
            if existing_start and existing_end:
                if (normalized_start < existing_end) and (normalized_end > existing_start):
                    return jsonify({'success': False, 'message': 'You already have an overlapping schedule on this date and time.'}), 400
        schedule_label = _format_confirmed_schedule_label(confirmed_date, normalized_start, normalized_end)
        schedule_message = f"{'New schedule confirmed' if has_pending_reschedule else 'Visit confirmed'}: {schedule_label.replace('Confirmed: ', '')}"

        schedule_insert_response = supabase.table('visit_schedules').insert({
            'report_id': report_id,
            'agriculturist_id': user_id,
            'confirmed_date': confirmed_date,
            'start_time': normalized_start,
            'end_time': normalized_end,
        }).execute()
        if getattr(schedule_insert_response, 'error', None):
            logger.error(f"Visit schedule insert failed: {schedule_insert_response.error}")
            return jsonify({'success': False, 'message': 'The visit schedule could not be saved.'}), 500

        chat_insert_response = supabase.table('visit_chats').insert({
            'report_id': report_id,
            'sender_id': user_id,
            'message': schedule_message,
        }).execute()
        if getattr(chat_insert_response, 'error', None):
            logger.warning(f"Visit schedule chat insert failed: {chat_insert_response.error}")

        update_response = _update_report_workflow(
            report_id,
            requested_status,
            note=f"Visit scheduled. {schedule_label}",
            extra_updates={
                'visit_summary': schedule_label,
                'visit_completed_at': datetime.now(UTC).isoformat(),
                'visit_reschedule_reason': None,
                'visit_rescheduled_at': None,
                'visit_rescheduled_by': None,
            },
        )
        if getattr(update_response, 'error', None):
            logger.error(f"Schedule update failed: {update_response.error}")
            return jsonify({'success': False, 'message': 'The visit schedule could not be finalized.'}), 500

        return jsonify({
            'success': True,
            'message': 'The visit schedule has been finalized.',
            'schedule_stamp': schedule_label,
            'schedule_title': 'New Schedule Confirmed' if has_pending_reschedule else 'Visit Scheduled',
        })
    except ValueError as e:
        return jsonify({'success': False, 'message': str(e)}), 400
    except Exception as e:
        logger.error(f"Error saving visit schedule: {str(e)}")
        return jsonify({'success': False, 'message': 'The visit schedule could not be saved.'}), 500


@app.route('/agriculturist/review-visit-request', methods=['POST'])
def agriculturist_review_visit_request():
    """Accept or reject a farmer visit request."""
    user_id = session.get('user_id')
    user_role = normalize_role(session.get('user_role'))

    if not user_id or user_role != 'agri_expert':
        return jsonify({'success': False, 'message': 'Unauthorized user session'}), 403

    try:
        payload = request.get_json(silent=True) or {}
        report_id = payload.get('report_id') or request.form.get('report_id')
        decision = str(payload.get('decision') or request.form.get('decision') or '').strip().lower()
        reason = (payload.get('reason') or request.form.get('reason') or '').strip()
        preferred_date = (payload.get('preferred_date') or request.form.get('preferred_date') or '').strip()
        preferred_time = (payload.get('preferred_time') or request.form.get('preferred_time') or '').strip()

        if not report_id:
            return jsonify({'success': False, 'message': 'Missing report reference'}), 400

        if decision == 'accept':
            if not preferred_date or not preferred_time:
                return jsonify({'success': False, 'message': 'Please confirm the visit date and time.'}), 400
            note = f"Visit schedule confirmed for {preferred_date} at {preferred_time}."
            status = 'visit_scheduled'
        else:
            if not reason:
                return jsonify({'success': False, 'message': 'A rejection reason is required.'}), 400
            note = f"Visit request rejected. Reason: {reason}"
            status = 'assessment_issued'

        update_response = _update_report_workflow(report_id, status, note=note)
        if getattr(update_response, 'error', None):
            logger.error(f"Visit request review failed: {update_response.error}")
            return jsonify({'success': False, 'message': 'The visit review could not be saved.'}), 500

        return jsonify({'success': True, 'message': 'Visit request updated.'})
    except Exception as e:
        logger.error(f"Error reviewing visit request: {str(e)}")
        return jsonify({'success': False, 'message': 'The visit review could not be saved.'}), 500


@app.route('/agriculturist/request-visit', methods=['POST'])
def agriculturist_request_visit():
    """Advance a case into the on-site visit workflow."""
    user_id = session.get('user_id')
    user_role = normalize_role(session.get('user_role'))

    if not user_id or user_role != 'agri_expert':
        return jsonify({'success': False, 'message': 'Unauthorized user session'}), 403

    try:
        data = request.get_json(silent=True) or {}
        report_id = data.get('report_id') or request.form.get('report_id')
        reason = (data.get('reason') or request.form.get('reason') or '').strip()

        if not report_id:
            return jsonify({'success': False, 'message': 'Missing report reference'}), 400

        note = f"On-site visit requested: {reason or 'No reason provided.'}"
        update_response = _update_report_workflow(report_id, 'Waiting for Agriculturist Confirmation', note=note)
        if getattr(update_response, 'error', None):
            logger.error(f"Visit request update failed: {update_response.error}")
            return jsonify({'success': False, 'message': 'The visit request could not be saved.'}), 500

        return jsonify({
            'success': True,
            'message': 'On-site visit requested successfully.',
        })
    except Exception as e:
        logger.error(f"Error requesting on-site visit: {str(e)}")
        return jsonify({'success': False, 'message': 'The visit request could not be saved.'}), 500


@app.route('/farmer/provide-availability', methods=['POST'])
def farmer_provide_availability():
    """Let the farmer share time slots for the requested visit."""
    user_id = session.get('user_id')
    user_role = normalize_role(session.get('user_role'))

    if not user_id or user_role != 'farmer':
        return jsonify({'success': False, 'message': 'Unauthorized user session'}), 403

    try:
        data = request.get_json(silent=True) or {}
        report_id = data.get('report_id') or request.form.get('report_id')
        availability = (data.get('availability') or request.form.get('availability') or '').strip()

        if not report_id:
            return jsonify({'success': False, 'message': 'Missing report reference'}), 400

        note = f"Farmer availability: {availability or 'No slots provided.'}"
        update_response = _update_report_workflow(report_id, 'Waiting for Agriculturist Confirmation', note=note)
        if getattr(update_response, 'error', None):
            logger.error(f"Availability update failed: {update_response.error}")
            return jsonify({'success': False, 'message': 'The availability could not be submitted.'}), 500

        return jsonify({'success': True, 'message': 'Your availability has been shared with the agriculturist.'})
    except Exception as e:
        logger.error(f"Error saving farmer availability: {str(e)}")
        return jsonify({'success': False, 'message': 'The availability could not be submitted.'}), 500


@app.route('/agriculturist/select-visit-schedule', methods=['POST'])
def agriculturist_select_visit_schedule():
    """Select the farmer availability slot for the visit."""
    user_id = session.get('user_id')
    user_role = normalize_role(session.get('user_role'))

    if not user_id or user_role != 'agri_expert':
        return jsonify({'success': False, 'message': 'Unauthorized user session'}), 403

    try:
        data = request.get_json(silent=True) or {}
        report_id = data.get('report_id') or request.form.get('report_id')
        schedule = (data.get('schedule') or request.form.get('schedule') or '').strip()

        if not report_id:
            return jsonify({'success': False, 'message': 'Missing report reference'}), 400

        note = f"Visit scheduled: {schedule or 'No schedule selected.'}"
        update_response = _update_report_workflow(report_id, 'Visit Scheduled', note=note)
        if getattr(update_response, 'error', None):
            logger.error(f"Schedule update failed: {update_response.error}")
            return jsonify({'success': False, 'message': 'The visit schedule could not be saved.'}), 500

        return jsonify({'success': True, 'message': 'The visit schedule has been shared with the farmer.'})
    except Exception as e:
        logger.error(f"Error saving visit schedule: {str(e)}")
        return jsonify({'success': False, 'message': 'The visit schedule could not be saved.'}), 500


@app.route('/agriculturist/complete-visit', methods=['POST'])
def agriculturist_complete_visit():
    """Record that the on-site visit was completed."""
    user_id = session.get('user_id')
    user_role = normalize_role(session.get('user_role'))

    if not user_id or user_role != 'agri_expert':
        return jsonify({'success': False, 'message': 'Unauthorized user session'}), 403

    try:
        payload = request.get_json(silent=True) or {}
        report_id = payload.get('report_id') or request.form.get('report_id')
        visit_summary = (payload.get('visit_summary') or request.form.get('visit_summary') or payload.get('details') or request.form.get('details') or '').strip()
        visit_files = request.files.getlist('visit_images')

        if not report_id:
            return jsonify({'success': False, 'message': 'Missing report reference'}), 400
        if not visit_summary:
            return jsonify({'success': False, 'message': 'Visit summary is required.'}), 400
        if not visit_files:
            return jsonify({'success': False, 'message': 'Please upload at least one visit image.'}), 400

        note = f"Visit completed: {visit_summary}"
        update_response = _update_report_workflow(report_id, 'resolved', note=note)
        if getattr(update_response, 'error', None):
            logger.error(f"Visit completion update failed: {update_response.error}")
            return jsonify({'success': False, 'message': 'The visit completion note could not be saved.'}), 500

        _persist_visit_images(report_id, visit_files, user_id, uploaded_at=datetime.now(UTC).isoformat())
        return jsonify({'success': True, 'message': 'Visit summary and images saved successfully.'})
    except Exception as e:
        logger.error(f"Error saving inspection completion: {str(e)}")
        return jsonify({'success': False, 'message': 'The visit completion note could not be saved.'}), 500


@app.route('/agriculturist/submit-final-remarks', methods=['POST'])
def agriculturist_submit_final_remarks():
    """Save final remarks and move the report into the final remarks stage."""
    user_id = session.get('user_id')
    user_role = normalize_role(session.get('user_role'))

    if not user_id or user_role != 'agri_expert':
        return jsonify({'success': False, 'message': 'Unauthorized user session'}), 403

    try:
        payload = request.get_json(silent=True) or {}
        report_id = payload.get('report_id') or request.form.get('report_id')
        final_remarks = (payload.get('final_remarks') or request.form.get('final_remarks') or '').strip()
        feedback = (payload.get('feedback') or payload.get('additional_notes') or request.form.get('feedback') or request.form.get('additional_notes') or '').strip()

        if not report_id or not final_remarks:
            return jsonify({'success': False, 'message': 'Final remarks are required.'}), 400

        note_parts = [f"Final remarks: {final_remarks}"]
        if feedback:
            note_parts.append(f"Feedback: {feedback}")
        note = "\n".join(note_parts)

        extra = {}
        if feedback:
            extra['feedback'] = feedback

        update_response = _update_report_workflow(report_id, 'final_remarks_issued', note=note, extra_updates=extra if extra else None)
        if getattr(update_response, 'error', None):
            logger.error(f"Final remarks update failed: {update_response.error}")
            return jsonify({'success': False, 'message': 'The final remarks could not be saved.'}), 500

        return jsonify({'success': True, 'message': 'Final remarks saved successfully.'})
    except Exception as e:
        logger.error(f"Error saving final remarks: {str(e)}")
        return jsonify({'success': False, 'message': 'The final remarks could not be saved.'}), 500


@app.route('/agriculturist/mark-resolved', methods=['POST'])
def agriculturist_mark_resolved():
    """Allow the agriculturist to finalise the case as resolved."""
    user_id = session.get('user_id')
    user_role = normalize_role(session.get('user_role'))

    if not user_id or user_role != 'agri_expert':
        return jsonify({'success': False, 'message': 'Unauthorized user session'}), 403

    try:
        data = request.get_json(silent=True) or {}
        report_id = data.get('report_id') or request.form.get('report_id')
        resolution_note = (data.get('resolution_note') or request.form.get('resolution_note') or '').strip()

        if not report_id:
            return jsonify({'success': False, 'message': 'Missing report reference'}), 400

        note = f"Agriculturist marked resolved: {resolution_note or 'Case closed.'}"
        update_response = _update_report_workflow(report_id, 'resolved', note=note)
        if getattr(update_response, 'error', None):
            logger.error(f"Resolution update failed: {update_response.error}")
            return jsonify({'success': False, 'message': 'The resolution could not be saved.'}), 500

        return jsonify({'success': True, 'message': 'The report has been marked as resolved.'})
    except Exception as e:
        logger.error(f"Error marking report resolved: {str(e)}")
        return jsonify({'success': False, 'message': 'The resolution could not be saved.'}), 500
    
@app.route('/farmer/submit-report', methods=['POST'])
def farmer_submit_report():
    """Processes pest scan data from the frontend and inserts it into the Supabase 'reports' table"""
    user_id = session.get('user_id')
    user_role = normalize_role(session.get('user_role'))
    
    if not user_id or user_role != 'farmer':
        return jsonify({'success': False, 'message': 'Unauthorized user session'}), 403

    try:
        # 1. Extract data sent by your scanning interface/form
        pest_type = request.form.get('pest_type', 'Unknown Pest').strip()
        farmer_notes = resolve_farmer_notes(request.form)
        confidence = request.form.get('confidence', '0').strip()
        latitude = request.form.get('gps_latitude', '').strip()
        longitude = request.form.get('gps_longitude', '').strip()
        gps_accuracy = request.form.get('gps_accuracy', '').strip()
        location_source = request.form.get('location_source', 'camera_gps').strip()
        photo_taken_at = request.form.get('photo_taken_at', '').strip() or datetime.now(UTC).isoformat()

        # Recommendations payload
        recommendations_json = request.form.get('recommendations', '[]').strip()
        try:
            import json
            initial_recommendations = json.loads(recommendations_json) if recommendations_json else []
        except Exception:
            initial_recommendations = []

        image_file = request.files.get('image_file')
        image_field = request.form.get('image_url', '').strip()
        supporting_files = request.files.getlist('supporting_images')
        saved_image_url = ''
        now_value = datetime.now(UTC)
        now_iso = now_value.isoformat()

        reverse_geo = {}
        if latitude and longitude:
            reverse_geo = reverse_geocode_latlng(latitude, longitude)

        barangay = reverse_geo.get('barangay', '')
        municipality = reverse_geo.get('municipality', '')
        province = reverse_geo.get('province', '')

        farmer_name = 'Farmer'
        try:
            user_query = supabase.table('users').select('first_name, last_name').eq('id', user_id).execute()
            if getattr(user_query, 'data', None):
                user_data = user_query.data[0] if user_query.data else {}
                farmer_name = f"{user_data.get('first_name', '')} {user_data.get('last_name', '')}".strip() or 'Farmer'
        except Exception as user_lookup_error:
            logger.warning(f"Unable to load farmer name for report insert: {str(user_lookup_error)}")

        report_payload = build_report_payload(
            user_id=user_id,
            pest_type=pest_type,
            farmer_notes=farmer_notes,
            confidence=confidence,
            latitude=latitude,
            longitude=longitude,
            gps_accuracy=gps_accuracy,
            location_source=location_source,
            photo_taken_at=photo_taken_at,
            initial_recommendations=initial_recommendations,
            farmer_name=farmer_name,
            created_at=now_iso,
            submitted_at=now_iso,
            status='under_review',
            image_url='',
            barangay=barangay,
            municipality=municipality,
            province=province,
        )

        report_insert = supabase.table('reports').insert(report_payload).execute()
        if getattr(report_insert, 'error', None):
            logger.error(f"Supabase report insert failed: {report_insert.error}")
            return jsonify({'success': False, 'message': 'The report could not be saved. Please try again.'}), 500
        if not getattr(report_insert, 'data', None):
            logger.error('Supabase accepted the connection but failed to write rows.')
            return jsonify({'success': False, 'message': 'The report could not be saved. Please try again.'}), 500

        report_id = report_insert.data[0].get('id') if report_insert.data and len(report_insert.data) else None

        try:
            if image_file:
                filename = secure_filename(image_file.filename or f'image_{now_value.timestamp()}.jpg')
                timestamp = now_value.strftime('%Y%m%d%H%M%S')
                storage_name = f"primary_{timestamp}_{filename}"
                image_bytes = image_file.read()
                saved_image_url = upload_image_to_supabase(image_bytes, storage_name, image_file.mimetype)
            elif image_field:
                if image_field.startswith('data:'):
                    header, encoded = image_field.split(',', 1)
                    m = re.match(r'data:(image/\w+);base64', header)
                    ext = 'png'
                    if m:
                        mime = m.group(1)
                        ext = mime.split('/')[-1]
                    decoded = base64.b64decode(encoded)
                    timestamp = now_value.strftime('%Y%m%d%H%M%S')
                    filename = f"{timestamp}_capture.{ext}"
                    saved_image_url = upload_image_to_supabase(decoded, secure_filename(filename), f"image/{ext}")
                else:
                    saved_image_url = image_field
        except Exception as image_error:
            logger.warning(f"Failed to save uploaded image: {str(image_error)}")

        if report_id and saved_image_url:
            try:
                supabase.table('reports').update({'image_url': saved_image_url, 'updated_at': now_iso}).eq('id', report_id).execute()
            except Exception as update_error:
                logger.warning(f"Unable to update report image URL: {str(update_error)}")

        if report_id and supporting_files:
            supporting_rows = []
            support_timestamp = now_value.strftime('%Y%m%d%H%M%S')
            for index, support_file in enumerate(supporting_files):
                if not support_file:
                    continue
                support_name = secure_filename(support_file.filename or f'supporting_{index}.jpg')
                support_path_name = f"support_{support_timestamp}_{support_name}"
                support_bytes = support_file.read()
                support_url = upload_image_to_supabase(support_bytes, support_path_name, support_file.mimetype)
                supporting_rows.append({
                    'report_id': report_id,
                    'image_url': support_url,
                    'uploaded_at': now_iso
                })
            if supporting_rows:
                supabase.table('report_supporting_images').insert(supporting_rows).execute()

        logger.info(f"Pest report logged successfully for user {user_id}. Report ID: {report_id}")
        return jsonify({
            'success': True,
            'message': 'Report submitted and synchronized cleanly!',
        })

    except Exception as e:
        error_str = str(e)
        logger.error(f"Report submission failed: {error_str}")
        # Return a user-friendly error message
        friendly_message = normalize_submission_error(error_str)
        return jsonify({'success': False, 'message': friendly_message}), 500

# Admin
@app.route('/admin/user-management')
def admin_user_management():
    current_role = str(session.get('user_role', '')).strip().lower()
    if current_role != 'admin':
        return redirect(url_for('login'))

    status_filter = request.args.get('status', 'All').strip()
    search_query = request.args.get('search', '').strip()
    
    try:
        current_page = max(1, int(request.args.get('page', 1)))
    except ValueError:
        current_page = 1
    PER_PAGE = 10

    try:
        response = supabase.table("users").select("*, profiles(*)").order("created_at", desc=True).execute()
        raw_users = response.data or []

        processed_users = []
        for u in raw_users:
            if str(u.get('role', '')).strip().lower() == 'admin':
                continue
            
            user_status = u.get('status', 'Under Review')
            if status_filter != 'All' and user_status != status_filter:
                continue

            first = u.get('first_name') or ''
            last = u.get('last_name') or ''
            email = u.get('email') or ''
            
            u['highlighted_first'] = first
            u['highlighted_last'] = last
            u['highlighted_email'] = email

            if search_query:
                sq = search_query.lower()
                full_compiled = f"{first} {last}".lower()
                
                location_text = " ".join(
                    filter(None, [u.get('barangay'), u.get('municipality'), u.get('province')])
                ).lower()

                if sq in full_compiled or sq in email.lower() or sq in location_text:
                    pattern = re.compile(re.escape(search_query), re.IGNORECASE)
                    u['highlighted_first'] = pattern.sub(lambda m: f'<mark class="ux-highlight">{m.group(0)}</mark>', first)
                    u['highlighted_last'] = pattern.sub(lambda m: f'<mark class="ux-highlight">{m.group(0)}</mark>', last)
                    u['highlighted_email'] = pattern.sub(lambda m: f'<mark class="ux-highlight">{m.group(0)}</mark>', email)
                else:
                    continue

            processed_users.append(u)

        total_records = len(processed_users)
        total_pages = max(1, (total_records + PER_PAGE - 1) // PER_PAGE)
        current_page = min(current_page, total_pages)
        
        start_idx = (current_page - 1) * PER_PAGE
        end_idx = start_idx + PER_PAGE
        paginated_users = processed_users[start_idx:end_idx]

    except Exception as e:
        flash(f"Database alignment execution error: {str(e)}", "error")
        paginated_users, total_pages, current_page = [], 1, 1

    return render_template(
        'admin_user_management.html', 
        users=paginated_users, 
        current_status=status_filter, 
        search=search_query,
        current_page=current_page,
        total_pages=total_pages
    )

@app.route('/admin/update-user-status', methods=['POST'])
def update_user_status():
    """Asynchronous API endpoint that saves status, runs email notice, and records logs"""
    if normalize_role(session.get('user_role')) != 'admin':
        return jsonify({'success': False, 'message': 'Unauthorized access'}), 403
        
    data = request.get_json() or {}
    user_id = data.get('user_id')
    action = data.get('action')
    
    if not user_id or action not in ['approve', 'reject']:
        return jsonify({'success': False, 'message': 'Invalid parameters provided'}), 400
        
    target_status = 'Approved' if action == 'approve' else 'Rejected'
    admin_name = session.get('user_name', 'PCA Admin')
    
    try:
        user_query = supabase.table("users").select("email, first_name, last_name").eq("id", user_id).execute()
        if not user_query.data:
            return jsonify({'success': False, 'message': 'Target profile record not found'}), 404
            
        target_user = user_query.data[0]
        target_email = target_user.get('email')
        target_fullname = f"{target_user.get('first_name', '')} {target_user.get('last_name', '')}".strip()
        
        email_sent = send_status_email(target_email, target_fullname, target_status)
        db_email_status = "Sent Successfully" if email_sent else "Delivery Failed"

        supabase.table("users").update({
            "status": target_status,
            "approved_by": admin_name,
            "email_status": db_email_status
        }).eq("id", user_id).execute()
        
        return jsonify({
            'success': True, 
            'target_status': target_status, 
            'admin_name': admin_name,
            'email_notified': email_sent
        })
    except Exception as e:
        logger.error(f"Status update route processing failure: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/admin/resend-email', methods=['POST'])
def resend_user_email():
    """Endpoint to resend status notification email for a specific user"""
    if normalize_role(session.get('user_role')) != 'admin':
        return jsonify({'success': False, 'message': 'Unauthorized access'}), 403
        
    data = request.get_json() or {}
    user_id = data.get('user_id')
    
    if not user_id:
        return jsonify({'success': False, 'message': 'User ID missing'}), 400
        
    try:
        user_query = supabase.table("users").select("email, first_name, last_name, status").eq("id", user_id).execute()
        if not user_query.data:
            return jsonify({'success': False, 'message': 'Target user not found'}), 404
            
        target_user = user_query.data[0]
        target_email = target_user.get('email')
        target_fullname = f"{target_user.get('first_name', '')} {target_user.get('last_name', '')}".strip()
        target_status = target_user.get('status')
        
        if not target_status or target_status == 'Under Review':
            return jsonify({'success': False, 'message': 'User status is pending. Approve or reject before sending email.'}), 400

        email_sent = send_status_email(target_email, target_fullname, target_status)
        db_email_status = "Sent Successfully" if email_sent else "Delivery Failed"

        supabase.table("users").update({
            "email_status": db_email_status
        }).eq("id", user_id).execute()
        
        return jsonify({
            'success': True, 
            'email_notified': email_sent
        })
    except Exception as e:
        logger.error(f"Resend email route processing failure: {str(e)}\n{traceback.format_exc()}")
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404

@app.errorhandler(500)
def internal_error(e):
    return render_template('500.html'), 500

# if __name__ == '__main__':
#     app.run(debug=True, threaded=True)

if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 5000))
    )