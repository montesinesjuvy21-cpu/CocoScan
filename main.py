import os
import logging
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

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

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

        public_url_response = storage.get_public_url(storage_path)
        if isinstance(public_url_response, dict):
            return public_url_response.get('publicUrl') or public_url_response.get('data', {}).get('publicUrl', '')
        if hasattr(public_url_response, 'data') and public_url_response.data:
            return public_url_response.data.get('publicUrl', '')
    except Exception as upload_err:
        logger.warning(f"Supabase Storage helper error: {str(upload_err)}")
    return ''


def send_status_email(user_email, user_name, status):
    """Sends a transactional HTML notification email to the user via Gmail SMTP"""
    smtp_server = os.getenv("MAIL_SERVER", "smtp.gmail.com")
    smtp_port = int(os.getenv("MAIL_PORT", 587))
    sender_email = os.getenv("MAIL_USERNAME")    
    sender_password = os.getenv("MAIL_PASSWORD")  
    
    sender_name = "CocoScan Platform"
    subject = f"Account Update: Your CocoScan Application has been {status}"
    
    # Dynamic styling matching the context status
    theme_color = "#40916c" if status == "Approved" else "#e63946"
    
    # EXACT FONT-AWESOME 'fa-tree-city' SVG VECTOR DATA PATH
    tree_city_svg = """
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 640 512" width="44" height="44" style="fill: #ffffff; display: block;">
        <path d="M0 480c0 17.7 14.3 32 32 32h384V336c0-13.3-10.7-24-24-24H248c-13.3 0-24 10.7-24 24v176H32c-17.7 0-32-14.3-32-32V254.4c0-11.8 4.9-23 13.5-31l112-104c12.5-11.6 32.5-11.6 45 0l40.1 37.2c-5.7 14-8.8 29.3-8.8 45.4c0 66.3 53.7 120 120 120c24.6 0 47.5-7.4 66.5-20.1L303.4 320H400c44.2 0 80 35.8 80 80v112h128c17.7 0 32-14.3 32-32V224c0-17.7-14.3-32-32-32H480V24c0-13.3-10.7-24-24-24H344c-13.3 0-24 10.7-24 24v123.4L230.2 61.3c-23.4-21.7-59.1-21.7-82.5 0L5.3 191.4C1.9 194.5 0 198.9 0 203.6V480zm352-278a40 40 0 1 1 80 0 40 40 0 1 1 -80 0zm40 134a40 40 0 1 1 0-80 40 40 0 1 1 0 80zM520 256a40 40 0 1 1 80 0 40 40 0 1 1 -80 0zm40 134a40 40 0 1 1 0-80 40 40 0 1 1 0 80z"/>
    </svg>
    """

    if status == "Approved":
        status_title = "Application Approved"
        message_body = f"""
        <p>Great news! Your account application for <strong>CocoScan</strong> has been reviewed and approved by our administration team.</p>
        <p>You can now log in to access your custom dashboard, review coconut metrics, and utilize our pest scanning system features.</p>
        <div style="margin: 30px 0; text-align: center;">
            <a href="http://127.0.0.1:5000/login" style="background-color: {theme_color}; color: #ffffff; padding: 14px 32px; text-decoration: none; font-weight: bold; border-radius: 8px; display: inline-block; box-shadow: 0 4px 6px rgba(0,0,0,0.1);">Log In To Dashboard</a>
        </div>
        """
    else:
        status_title = "Application Declined"
        message_body = f"""
        <p>Thank you for your interest in <strong>CocoScan</strong>.</p>
        <p>After carefully reviewing your registration details, our administration team has declined your account application at this time.</p>
        <p style="background-color: #f8f9fa; border-left: 4px solid {theme_color}; padding: 14px; color: #6c757d; font-size: 14px; border-radius: 4px;">
            <strong>Notice:</strong> If you believe this decision was made in error or if you provided incorrect credentials during registration, please reach out to our system support desk for manual verification.
        </p>
        """

    body_html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>{subject}</title>
    </head>
    <body style="margin: 0; padding: 0; background-color: #0b1315; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; color: #e2e8f0;-webkit-font-smoothing: antialiased;">
        <table border="0" cellpadding="0" cellspacing="0" width="100%" style="table-layout: fixed; background-color: #0b1315; padding: 40px 0;">
            <tr>
                <td align="center">
                    <table border="0" cellpadding="0" cellspacing="0" width="100%" style="max-width: 550px; background-color: #121f22; border: 1px solid rgba(255,255,255,0.05); border-radius: 16px; overflow: hidden; box-shadow: 0 10px 30px rgba(0,0,0,0.5);">
                        <tr>
                            <td align="center" style="position: relative; padding: 50px 20px; background: linear-gradient(135deg, #162a2d 0%, #0b1315 100%); border-bottom: 2px solid {theme_color};">
                                <div style="position: relative; width: 100px; height: 100px; margin-bottom: 20px; text-align: center;">
                                    <div style="position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%); width: 90px; height: 90px; background-color: {theme_color}; border-radius: 50%; opacity: 0.15; filter: blur(10px);"></div>
                                    <div style="position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%); width: 80px; height: 80px; border: 2px solid {theme_color}; border-radius: 50%; opacity: 0.3;"></div>
                                    <div style="position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%); width: 55px; height: 55px; border: 1px dashed {theme_color}; border-radius: 50%; opacity: 0.5;"></div>
                                    <div style="position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%); line-height: 1; z-index: 5;">
                                        {tree_city_svg}
                                    </div>
                                </div>
                                <div style="font-weight: 800; font-size: 32px; color: #ffffff; letter-spacing: 1px; margin-bottom: 4px;">CocoScan</div>
                                <div style="font-size: 13px; color: #789c8a; letter-spacing: 2px; text-transform: uppercase; font-weight: 500;">{status_title}</div>
                            </td>
                        </tr>
                        <tr>
                            <td style="padding: 40px 35px; background-color: #121f22;">
                                <h3 style="margin-top: 0; color: #ffffff; font-size: 18px; font-weight: 600;">Hello {user_name},</h3>
                                <div style="font-size: 15px; line-height: 1.7; color: #cbd5e1;">
                                    {message_body}
                                </div>
                                <hr style="border: 0; border-top: 1px solid rgba(255,255,255,0.06); margin: 35px 0;">
                                <p style="margin: 0; font-size: 14px; color: #64748b; line-height: 1.5;">
                                    Best regards,<br>
                                    <span style="color: #ffffff; font-weight: 600;">The CocoScan Development Node</span>
                                </p>
                            </td>
                        </tr>
                        <tr>
                            <td align="center" style="background-color: #0b1315; padding: 25px; font-size: 11px; color: #475569; letter-spacing: 0.5px;">
                                <p style="margin: 0 0 4px 0;">This transmission is encrypted and delivered from the administrative terminal cloud hub.</p>
                                <p style="margin: 0;">&copy; 2026 CocoScan Security Framework • Coconut Disease Detection Systems</p>
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
        server = smtplib.SMTP(smtp_server, smtp_port, timeout=10)
        server.starttls()
        server.login(sender_email, sender_password)
        server.sendmail(sender_email, user_email, msg.as_string())
        server.quit()
        
        logger.info(f"Notification email dispatched cleanly via Gmail to {user_email}.")
        return True
    except Exception as e:
        logger.error(f"Gmail SMTP Exception thrown while mailing {user_email}: {str(e)}")
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
                "address": validated_data['address'],
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
        
        # -------------------------------------------------------------
        # PRODUCTION REPLACEMENT: LIVE REAL-TIME DATA METRICS DOCKING
        # -------------------------------------------------------------
        # Total report count query
        { 'count': 'exact', 'head': True }
        total_res = supabase.table('reports').select('*', count='exact', head=True).execute()
        total_cases = total_res.count if hasattr(total_res, 'count') else 0

        # Unresolved cases query
        pending_res = supabase.table('reports').select('*', count='exact', head=True).eq('status', 'Pending').execute()
        pending_cases = pending_res.count if hasattr(pending_res, 'count') else 0

        # Resolved cases query
        resolved_res = supabase.table('reports').select('*', count='exact', head=True).eq('status', 'Recommendation Issued').execute()
        resolved_cases = resolved_res.count if hasattr(resolved_res, 'count') else 0

        metrics = {
            "total_cases": total_cases, 
            "pending_cases": pending_cases, 
            "resolved_cases": resolved_cases
        }
        # -------------------------------------------------------------
        
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

        return render_template('farmer_dashboard.html', user_name=user_name, metrics=metrics, weather=weather, risk=risk)
        
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
        
        return render_template('farmer_scan.html', user_name=user_name)
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
        
        # Get model paths from environment or use defaults (YOLO removed)
        pest_model_path = os.getenv('PEST_MODEL_PATH',
            os.path.join(os.path.dirname(__file__), '..', 'cocoscan-model', 'models', 'pest_classifier.tflite'))
        severity_model_path = os.getenv('SEVERITY_MODEL_PATH',
            os.path.join(os.path.dirname(__file__), '..', 'cocoscan-model', 'models', 'severity_classifier.tflite'))

        # Verify classification model paths exist
        for model_path in [pest_model_path, severity_model_path]:
            if not os.path.exists(model_path):
                logger.error(f"Model not found: {model_path}")
                return jsonify({'success': False, 'error': f'Model not found: {model_path}'}), 500
        
        # Run inference pipeline (YOLO removed; pass empty string in the yolo slot)
        result = run_full_inference_pipeline(
            image,
            '',
            pest_model_path,
            severity_model_path,
            use_lite_size=False
        )
        
        if not result.get('success', False):
            logger.warning(f"Inference pipeline failed: {result.get('error', 'Unknown error')}")
            return jsonify({
                'success': False,
                'error': result.get('error', 'Failed to process image'),
                'pest': 'Unknown',
                'severity': 'Unknown'
            }), 400
        
        # Format response
        response = {
            'success': True,
            'pest': result['pest'],
            'severity': result['severity'],
            'pest_confidence': round(result['pest_confidence'] * 100, 1),
            'severity_confidence': round(result['severity_confidence'] * 100, 1),
            'damage_percentage': result['damage_percentage'],
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
        reports_response = supabase.table("reports").select("*").eq("user_id", user_id).order("created_at", desc=True).execute()
        for item in getattr(reports_response, "data", []) or []:
            created_raw = item.get("created_at") or ""
            try:
                created_dt = datetime.fromisoformat(created_raw.replace("Z", "+00:00")) if created_raw else None
                created_label = created_dt.strftime("%b %d, %Y") if created_dt else "No date"
                created_value = created_dt.strftime("%Y-%m-%d") if created_dt else ""
            except Exception:
                created_label = created_raw.split("T")[0] if created_raw else "No date"
                created_value = created_label

            # Get recommendations from database or use defaults
            initial_recommendations = item.get("initial_recommendations") or []
            if not isinstance(initial_recommendations, list):
                initial_recommendations = []
            
            if not initial_recommendations:
                # Fallback to default recommendations based on pest type
                pest_type = item.get("pest_type") or "Unknown Pest"
                severity = item.get("damage_severity") or "Moderate"
                from app.recommendations import recommend_actions
                rec_data = recommend_actions(pest_type, severity)
                initial_recommendations = rec_data.get("recommendation", [])

            reports_data.append({
                "id": item.get("id"),
                "pest": item.get("pest_type") or "Unknown Pest",
                "timestamp": created_label,
                "date": created_value,
                "status": item.get("status") or "Under Review",
                "confidence": item.get("confidence") or "90%",
                "damage": item.get("damage_severity") or "Moderate",
                "notes": item.get("field_notes") or "No notes logged.",
                "img": item.get("image_url") or "",
                "initial_recommendations": initial_recommendations,
                "expert_recommendations": []
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
        
        # Fetch metrics (reusing farmer dashboard logic)
        total_res = supabase.table('reports').select('*', count='exact', head=True).execute()
        total_cases = total_res.count if hasattr(total_res, 'count') else 0

        pending_res = supabase.table('reports').select('*', count='exact', head=True).eq('status', 'Pending').execute()
        pending_cases = pending_res.count if hasattr(pending_res, 'count') else 0

        resolved_res = supabase.table('reports').select('*', count='exact', head=True).eq('status', 'Recommendation Issued').execute()
        resolved_cases = resolved_res.count if hasattr(resolved_res, 'count') else 0

        metrics = {
            "total_cases": total_cases, 
            "pending_cases": pending_cases, 
            "resolved_cases": resolved_cases,
            "affected_areas": 3  # Sample: number of affected areas
        }
        
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

        return render_template('agriculturist_dashboard.html', user_name=user_name, metrics=metrics, weather=weather, risk=risk)
        
    except Exception as e:
        logger.error(f"Agriculturist dashboard routing exception: {str(e)}")
        return redirect(url_for('logout'))

@app.route('/agriculturist/pending')
def agriculturist_pending():
    """Fetches reports with 'Pending' status from Supabase and renders the queue."""
    user_id = session.get('user_id')
    user_role = normalize_role(session.get('user_role'))
    
    if not user_id or user_role != 'agri_expert':
        flash("Unauthorized access path.", "error")
        return redirect(url_for('login'))
        
    try:
        # Load user profile for layout presentation layer
        user_query = supabase.table("users").select("first_name, last_name").eq("id", user_id).execute()
        user_name = f"{user_query.data[0].get('first_name', '')} {user_query.data[0].get('last_name', '')}".strip() if user_query.data else "Agriculturist"
        
        # Pull reports awaiting expert review from database
        reports_response = supabase.table("reports")\
            .select("*")\
            .eq("status", "Pending")\
            .order("created_at", desc=True)\
            .execute()
            
        raw_reports = reports_response.data or []
        pending_reports_list = []
        
        for item in raw_reports:
            created_raw = item.get("created_at") or ""
            try:
                created_dt = datetime.fromisoformat(created_raw.replace("Z", "+00:00")) if created_raw else None
                created_label = created_dt.strftime("%b %d, %Y • %I:%M %p") if created_dt else "No date"
                created_date_only = created_dt.strftime("%Y-%m-%d") if created_dt else ""
            except Exception:
                created_date_only = created_raw.split("T")[0] if created_raw else ""
                created_label = created_date_only

            # Process geographic tracking constraints
            loc_summary = item.get("barangay") or "Unknown Location"
            full_loc = ", ".join(filter(None, [item.get("barangay"), item.get("municipality"), item.get("province")]))
            
            pending_reports_list.append({
                "id": item.get("id"),
                "date": created_date_only,
                "timestamp": created_label,
                "location": loc_summary,
                "full_location": full_loc or "No location logged",
                "farmer": item.get("farmer_name") or "Unknown Farmer",
                "pest": item.get("pest_type") or "Unknown Pest",
                "severity": item.get("damage_severity") or "Moderate",
                "status": item.get("status") or "Pending",
                "confidence": f"{int(float(item.get('confidence', 0)))}%" if item.get('confidence') else "90%",
                "farmer_notes": item.get("field_notes") or "No extra notes logged by the farmer.",
                "img": item.get("image_url") or "",
                "initial_recommendations": item.get("initial_recommendations") or []
            })
            
        return render_template(
            'agriculturist_pending_reports.html', 
            user_name=user_name, 
            pending_reports=pending_reports_list
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
            .eq("status", "Recommendation Issued")\
            .order("updated_at", desc=True)\
            .execute()
            
        raw_reports = reports_response.data or []
        reviewed_reports_list = []
        
        for item in raw_reports:
            created_raw = item.get("created_at") or ""
            try:
                created_dt = datetime.fromisoformat(created_raw.replace("Z", "+00:00")) if created_raw else None
                created_label = created_dt.strftime("%b %d, %Y • %I:%M %p") if created_dt else "No date"
                created_date_only = created_dt.strftime("%Y-%m-%d") if created_dt else ""
            except Exception:
                created_date_only = created_raw.split("T")[0] if created_raw else ""
                created_label = created_date_only

            # Process geographic tracking constraints
            loc_summary = item.get("barangay") or "Unknown Location"
            full_loc = ", ".join(filter(None, [item.get("barangay"), item.get("municipality"), item.get("province")]))
            
            # Extract the expert recommendation note (assuming single string inside array matrix or raw fallback)
            expert_recs = item.get("expert_recommendations") or []
            expert_note = expert_recs[0] if isinstance(expert_recs, list) and len(expert_recs) > 0 else "No technical recommendations filed."
            
            reviewed_reports_list.append({
                "id": item.get("id"),
                "date": created_date_only,
                "timestamp": created_label,
                "location": loc_summary,
                "full_location": full_loc or "No location logged",
                "farmer": item.get("farmer_name") or "Unknown Farmer",
                "pest": item.get("pest_type") or "Unknown Pest",
                "severity": item.get("damage_severity") or "Moderate",
                "status": "Reviewed",
                "confidence": f"{int(float(item.get('confidence', 0)))}%" if item.get('confidence') else "90%",
                "farmer_notes": item.get("field_notes") or "No extra notes logged by the farmer.",
                "img": item.get("image_url") or "",
                "initial_recommendations": item.get("initial_recommendations") or [],
                "expert_recommendation": expert_note
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
        # Load user profile for layout presentation layer
        user_query = supabase.table("users").select("first_name, last_name").eq("id", user_id).execute()
        user_name = f"{user_query.data[0].get('first_name', '')} {user_query.data[0].get('last_name', '')}".strip() if user_query.data else "Agriculturist"
        
        # Retrieve all spatial records containing geographical metrics
        reports_response = supabase.table("reports")\
            .select("id, barangay, municipality, province, latitude, longitude, pest_type, damage_severity")\
            .not_.is_("latitude", "null")\
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
                "damage_severity": item.get("damage_severity") or "Moderate",
                "cases_count": 1 # Serves as baseline cluster weight variable
            })
            
        return render_template(
            'map_view.html', 
            user_name=user_name, 
            map_reports=map_reports_list
        )
        
    except Exception as e:
        logger.error(f"Error serving geospatial map canvas metrics: {str(e)}")
        flash("An alignment error occurred reading spatial coordinates.", "error")
        return redirect(url_for('agriculturist_dashboard'))
    
@app.route('/agriculturist/approve-report', methods=['POST'])
def agriculturist_approve_report():
    """Asynchronous pipeline to append specialist recommendations and update status."""
    user_id = session.get('user_id')
    user_role = normalize_role(session.get('user_role'))
    
    if not user_id or user_role != 'agri_expert':
        return jsonify({'success': False, 'message': 'Unauthorized user session'}), 403
        
    try:
        data = request.get_json() or {}
        report_id = data.get('report_id')
        expert_advice = data.get('recommendation', '').strip()
        
        if not report_id or not expert_advice:
            return jsonify({'success': False, 'message': 'Missing validation parameters'}), 400
            
        now_iso = datetime.now(UTC).isoformat()
        
        # Format specialist notes to array wrapper matching expected view parameters
        expert_recs_array = [expert_advice]
        
        # Update row matrix inside Supabase reports data schema
        update_response = supabase.table("reports").update({
            "status": "Recommendation Issued",
            "expert_recommendations": expert_recs_array,
            "reviewed_by_id": user_id,
            "updated_at": now_iso
        }).eq("id", report_id).execute()
        
        if not update_response.data:
            return jsonify({'success': False, 'message': 'Target record failed to save update rows'}), 500
            
        logger.info(f"Report ID #{report_id} successfully processed and signed off by expert #{user_id}.")
        return jsonify({
            'success': True, 
            'message': 'Expert diagnostic treatment recommendation logged successfully.'
        }), 200
        
    except Exception as e:
        logger.error(f"Error running expert approval execution route: {str(e)}")
        return jsonify({'success': False, 'message': f"Internal validation error: {str(e)}"}), 500
    
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
        damage_severity = request.form.get('damage_severity', 'Low').strip()
        field_notes = request.form.get('field_notes', '').strip()
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

        report_payload = {
            'farmer_name': farmer_name,
            'pest_type': pest_type,
            'confidence': confidence,
            'damage_severity': damage_severity,
            'image_url': '',
            'field_notes': field_notes,
            'status': 'Pending',
            'created_at': now_iso,
            'initial_recommendations': initial_recommendations,
            'latitude': latitude,
            'longitude': longitude,
            'gps_accuracy': gps_accuracy,
            'location_source': location_source,
            'photo_taken_at': photo_taken_at,
            'barangay': barangay,
            'municipality': municipality,
            'province': province,
            'submitted_at': now_iso,
            'updated_at': now_iso,
        }

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
                if not saved_image_url:
                    save_path = os.path.join(app.config['UPLOAD_FOLDER'], storage_name)
                    with open(save_path, 'wb') as f:
                        f.write(image_bytes)
                    saved_image_url = url_for('static', filename=f'uploads/{os.path.basename(save_path)}')
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
                    save_path = os.path.join(app.config['UPLOAD_FOLDER'], secure_filename(filename))
                    with open(save_path, 'wb') as f:
                        f.write(decoded)
                    saved_image_url = url_for('static', filename=f'uploads/{os.path.basename(save_path)}')
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
                if not support_url:
                    support_save_path = os.path.join(app.config['UPLOAD_FOLDER'], support_path_name)
                    with open(support_save_path, 'wb') as f:
                        f.write(support_bytes)
                    support_url = url_for('static', filename=f'uploads/{os.path.basename(support_save_path)}')
                supporting_rows.append({
                    'report_id': report_id,
                    'image_url': support_url,
                    'uploaded_at': now_iso
                })
            if supporting_rows:
                supabase.table('report_supporting_images').insert(supporting_rows).execute()

        logger.info(f"Pest report logged successfully for user {user_id}. Report ID: {report_id}")
        return jsonify({'success': True, 'message': 'Report submitted and synchronized cleanly!'})

    except Exception as e:
        logger.error(f"Cloud instance synchronization failed: {str(e)}")
        return jsonify({'success': False, 'message': f"Cloud instance synchronization failed: {str(e)}"}), 500

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
                
                if sq in full_compiled or sq in email.lower() or sq in (u.get('address') or '').lower():
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