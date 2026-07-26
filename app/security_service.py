import sqlite3
import time
import random
import os
import smtplib
import traceback
import logging
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

logger = logging.getLogger(__name__)

DB_PATH = os.path.join(os.path.dirname(__file__), "cocoscan_security.db")
OTP_EXPIRY_SECONDS = 45
OTP_RESEND_COOLDOWN_SECONDS = 45

def _get_db():
    conn = sqlite3.connect(DB_PATH, timeout=15)
    conn.row_factory = sqlite3.Row
    return conn

def init_security_db():
    """Initializes the SQLite schema for security tracking and audit logs."""
    with _get_db() as conn:
        cursor = conn.cursor()
        
        # Table for login attempt lockouts
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS login_attempts (
                email TEXT PRIMARY KEY,
                attempt_count INTEGER DEFAULT 0,
                last_attempt_at REAL,
                locked_until REAL,
                lock_reason TEXT
            )
        """)
        
        # Table for OTP codes (2FA and Forgot Password)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS otp_codes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT,
                code TEXT,
                purpose TEXT,
                created_at REAL,
                expires_at REAL,
                is_used INTEGER DEFAULT 0
            )
        """)
        
        # Table for 2FA 7-day expiration tracking
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS two_factor_auth (
                email TEXT PRIMARY KEY,
                last_verified_at REAL
            )
        """)
        
        # Table for Forgot Password 3-attempt limits
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS forgot_pass_attempts (
                email TEXT PRIMARY KEY,
                attempt_count INTEGER DEFAULT 0,
                last_attempt_at REAL
            )
        """)
        
        # Table for Admin Audit Logs
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS audit_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT,
                user_email TEXT,
                user_role TEXT,
                action TEXT,
                details TEXT,
                ip_address TEXT
            )
        """)
        
        conn.commit()

# Initialize DB on import
init_security_db()

# --- ACCOUNT LOCKOUT METHODS ---

def check_account_lockout(email: str):
    """
    Checks if an email is currently locked out.
    Returns: (is_locked: bool, remaining_seconds: int, lock_reason: str)
    """
    email = (email or "").strip().lower()
    if not email:
        return False, 0, ""
        
    with _get_db() as conn:
        row = conn.execute("SELECT * FROM login_attempts WHERE email = ?", (email,)).fetchone()
        if not row:
            return False, 0, ""
            
        locked_until = row["locked_until"]
        if locked_until and time.time() < locked_until:
            rem = int(locked_until - time.time())
            return True, rem, row["lock_reason"] or "Account temporarily locked."
            
        # If lock expired, clean up locked_until
        if locked_until and time.time() >= locked_until:
            conn.execute("UPDATE login_attempts SET locked_until = NULL, attempt_count = 0 WHERE email = ?", (email,))
            conn.commit()
            
    return False, 0, ""

def record_login_failure(email: str, ip_address: str = ""):
    """
    Records a failed login attempt. Locks account for 15 minutes at 3 attempts, 1 hour at 5 attempts.
    Returns: (new_count: int, locked_until: float|None, lock_reason: str)
    """
    email = (email or "").strip().lower()
    if not email:
        return 0, None, ""
        
    now = time.time()
    with _get_db() as conn:
        row = conn.execute("SELECT * FROM login_attempts WHERE email = ?", (email,)).fetchone()
        current_count = row["attempt_count"] if row else 0
        new_count = current_count + 1
        
        locked_until = None
        lock_reason = ""
        
        if new_count >= 5:
            locked_until = now + 3600  # 1 hour
            lock_reason = "Account locked for 1 hour due to 5 failed login attempts."
        elif new_count >= 3:
            locked_until = now + 900   # 15 minutes
            lock_reason = "Account locked for 15 minutes due to 3 failed login attempts."
            
        if row:
            conn.execute("""
                UPDATE login_attempts 
                SET attempt_count = ?, last_attempt_at = ?, locked_until = ?, lock_reason = ?
                WHERE email = ?
            """, (new_count, now, locked_until, lock_reason, email))
        else:
            conn.execute("""
                INSERT INTO login_attempts (email, attempt_count, last_attempt_at, locked_until, lock_reason)
                VALUES (?, ?, ?, ?, ?)
            """, (email, new_count, now, locked_until, lock_reason))
        conn.commit()
        
    if locked_until:
        log_audit(email, "System", "ACCOUNT_LOCKOUT", lock_reason, ip_address)
    else:
        log_audit(email, "System", "LOGIN_FAILED", f"Failed login attempt ({new_count}/3)", ip_address)
        
    return new_count, locked_until, lock_reason

def reset_login_failures(email: str):
    """Resets failed login attempts upon successful login."""
    email = (email or "").strip().lower()
    if not email:
        return
    with _get_db() as conn:
        conn.execute("DELETE FROM login_attempts WHERE email = ?", (email,))
        conn.commit()

# --- FORGOT PASSWORD LIMITS ---

def can_request_forgot_password(email: str):
    """
    Checks if user can request a forgot password OTP (limit 3 attempts per 24 hours).
    Returns: (can_request: bool, attempts_left: int)
    """
    email = (email or "").strip().lower()
    if not email:
        return False, 0
        
    now = time.time()
    with _get_db() as conn:
        row = conn.execute("SELECT * FROM forgot_pass_attempts WHERE email = ?", (email,)).fetchone()
        if not row:
            return True, 3
            
        # Reset limit if last attempt was over 24 hours ago
        if now - (row["last_attempt_at"] or 0) > 86400:
            conn.execute("DELETE FROM forgot_pass_attempts WHERE email = ?", (email,))
            conn.commit()
            return True, 3
            
        count = row["attempt_count"]
        if count >= 3:
            return False, 0
            
        return True, (3 - count)

def record_forgot_password_attempt(email: str):
    """Increments the forgot password attempt counter."""
    email = (email or "").strip().lower()
    if not email:
        return
    now = time.time()
    with _get_db() as conn:
        row = conn.execute("SELECT * FROM forgot_pass_attempts WHERE email = ?", (email,)).fetchone()
        if row:
            conn.execute("UPDATE forgot_pass_attempts SET attempt_count = attempt_count + 1, last_attempt_at = ? WHERE email = ?", (now, email))
        else:
            conn.execute("INSERT INTO forgot_pass_attempts (email, attempt_count, last_attempt_at) VALUES (?, 1, ?)", (email, now))
        conn.commit()

def reset_forgot_password_attempts(email: str):
    """Clears forgot password attempts after successful reset."""
    email = (email or "").strip().lower()
    if not email:
        return
    with _get_db() as conn:
        conn.execute("DELETE FROM forgot_pass_attempts WHERE email = ?", (email,))
        conn.commit()

# --- OTP GENERATION & VERIFICATION ---

def _send_email_smtp(recipient: str, subject: str, body_html: str) -> bool:
    """Helper to send transactional HTML emails via Gmail SMTP."""
    smtp_server = os.getenv("MAIL_SERVER", "smtp.gmail.com").strip()
    smtp_port = int(os.getenv("MAIL_PORT", 587))
    sender_email = (os.getenv("MAIL_USERNAME") or "").strip()
    sender_password = (os.getenv("MAIL_PASSWORD") or "").strip()
    
    if not sender_email or not sender_password:
        logger.warning(f"[SMTP OFFLINE] Email credentials not set in .env. Would send email to {recipient}: Subject='{subject}'")
        return False
        
    msg = MIMEMultipart()
    msg['From'] = f"CocoScan Security <{sender_email}>"
    msg['To'] = recipient
    msg['Subject'] = subject
    msg.attach(MIMEText(body_html, 'html'))

    try:
        server = smtplib.SMTP(smtp_server, smtp_port, timeout=10)
        server.starttls()
        server.login(sender_email, sender_password)
        server.sendmail(sender_email, recipient, msg.as_string())
        server.quit()
        logger.info(f"Security email dispatched via Gmail to {recipient}.")
        return True
    except Exception as e:
        logger.error(f"Gmail SMTP Error while mailing {recipient}: {e}\n{traceback.format_exc()}")
        return False

def generate_and_send_otp(email: str, purpose: str = "2FA Verification") -> dict:
    """
    Generates a 6-digit OTP code, stores it in SQLite (valid for 45 seconds), and sends it via email.
    Returns: a dict with the code, send status, expires_at, and resend cooldown details.
    """
    email = (email or "").strip().lower()
    code = f"{random.randint(0, 999999):06d}"
    now = time.time()
    expires_at = now + OTP_EXPIRY_SECONDS
    
    with _get_db() as conn:
        # Invalidate any previous unused OTPs for this email & purpose
        conn.execute("UPDATE otp_codes SET is_used = 1 WHERE email = ? AND purpose = ? AND is_used = 0", (email, purpose))
        conn.execute("""
            INSERT INTO otp_codes (email, code, purpose, created_at, expires_at, is_used)
            VALUES (?, ?, ?, ?, ?, 0)
        """, (email, code, purpose, now, expires_at))
        conn.commit()
        
    logger.info(f"[SECURITY OTP] Generated code for {email} ({purpose}): {code}")
    
    # Clean, vibrant SVG logo matching approved account email
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

    # Send email
    subject = f"Your CocoScan {purpose} Code"
    body_html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>{subject}</title>
    </head>
    <body style="margin: 0; padding: 0; background-color: #f8fafc; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; color: #1e293b; -webkit-font-smoothing: antialiased;">
        <table border="0" cellpadding="0" cellspacing="0" width="100%" style="background-color: #f8fafc; padding: 48px 20px;">
            <tr>
                <td align="center">
                    <table border="0" cellpadding="0" cellspacing="0" width="100%" style="max-width: 560px; background-color: #ffffff; border-radius: 20px; overflow: hidden; border: 1px solid #e2e8f0; box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.05), 0 8px 10px -6px rgba(0, 0, 0, 0.01);">
                        <!-- Accent Top Bar -->
                        <tr>
                            <td style="height: 6px; background: linear-gradient(90deg, #0d9488 0%, #10b981 100%);"></td>
                        </tr>
                        <!-- Header Section -->
                        <tr>
                            <td align="center" style="padding: 36px 36px 24px 36px; background-color: #ffffff; border-bottom: 1px solid #f1f5f9;">
                                <table border="0" cellpadding="0" cellspacing="0">
                                    <tr>
                                        <td style="padding-right: 12px; vertical-align: middle;">
                                            {cocoscan_logo_svg}
                                        </td>
                                        <td style="vertical-align: middle; text-align: left;">
                                            <span style="font-size: 22px; font-weight: 800; color: #0f172a; letter-spacing: -0.5px; display: block;">CocoScan</span>
                                            <span style="font-size: 11px; font-weight: 700; color: #0d9488; letter-spacing: 1.5px; text-transform: uppercase;">Security Verification</span>
                                        </td>
                                    </tr>
                                </table>
                            </td>
                        </tr>
                        
                        <!-- Body Section -->
                        <tr>
                            <td style="padding: 40px 36px; background-color: #ffffff;">
                                <h2 style="margin: 0 0 16px 0; font-size: 20px; font-weight: 700; color: #0f172a; letter-spacing: -0.3px;">Authentication Code</h2>
                                <p style="margin: 0 0 24px 0; font-size: 15px; line-height: 1.6; color: #475569;">
                                    Please use the verification code below to complete your sign-in or security request for <strong>{purpose}</strong>.
                                </p>
                                
                                <div style="background-color: #f0fdf4; border: 1px solid #bbf7d0; border-radius: 14px; padding: 28px 20px; text-align: center; margin: 28px 0;">
                                    <span style="font-size: 36px; font-weight: 800; letter-spacing: 10px; color: #065f46; font-family: 'Courier New', Courier, monospace; display: block; margin-left: 10px;">{code}</span>
                                    <div style="margin-top: 12px; font-size: 13px; color: #166534; font-weight: 500;">
                                     Valid for 45 seconds only
                                    </div>
                                </div>
                                
                                <p style="margin: 24px 0 0 0; font-size: 14px; line-height: 1.6; color: #64748b;">
                                    If you didn't request this code, you can safely ignore this email. Someone else might have typed your email address by mistake.
                                </p>
                                
                                <div style="margin-top: 36px; padding-top: 24px; border-top: 1px solid #f1f5f9;">
                                    <p style="margin: 0; font-size: 14px; color: #475569; line-height: 1.5;">
                                        Best regards,<br>
                                        <strong style="color: #0f172a; font-weight: 600;">The CocoScan Security Team</strong>
                                    </p>
                                </div>
                            </td>
                        </tr>
                        
                        <!-- Footer Section -->
                        <tr>
                            <td align="center" style="padding: 24px 36px; background-color: #f8fafc; border-top: 1px solid #f1f5f9; font-size: 12px; color: #94a3b8; line-height: 1.6;">
                                <p style="margin: 0 0 6px 0;">This is an automated security notification from CocoScan.</p>
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
    
    sent = _send_email_smtp(email, subject, body_html)
    return {
        "code": code,
        "sent": sent,
        "expires_at": expires_at,
        "expires_in_seconds": OTP_EXPIRY_SECONDS,
        "resend_cooldown_seconds": OTP_RESEND_COOLDOWN_SECONDS,
    }

def verify_otp(email: str, code: str, purpose: str = "2FA Verification"):
    """
    Verifies a 6-digit OTP code.
    Returns: (success: bool, message: str)
    """
    email = (email or "").strip().lower()
    code = (code or "").strip()
    
    if not email or not code:
        return False, "Please enter the verification code."
        
    now = time.time()
    with _get_db() as conn:
        row = conn.execute("""
            SELECT * FROM otp_codes 
            WHERE email = ? AND purpose = ? AND is_used = 0
            ORDER BY id DESC LIMIT 1
        """, (email, purpose)).fetchone()
        
        if not row:
            return False, "No active verification code found. Please request a new code."
            
        if now > row["expires_at"]:
            conn.execute("UPDATE otp_codes SET is_used = 1 WHERE id = ?", (row["id"],))
            conn.commit()
            return False, "This verification code has expired. Please request a new code."
            
        if row["code"] != code:
            return False, "Incorrect verification code. Please try again."
            
        # Mark as used
        conn.execute("UPDATE otp_codes SET is_used = 1 WHERE id = ?", (row["id"],))
        conn.commit()
        
    return True, "Verification successful."

# --- TWO FACTOR AUTHENTICATION (7 DAYS) ---

def requires_2fa(email: str, days: int = 7) -> bool:
    """
    Checks if a user requires 2FA verification (every 7 days).
    Returns: True if 2FA is needed, False if verified within the last `days`.
    """
    email = (email or "").strip().lower()
    if not email:
        return False
        
    now = time.time()
    with _get_db() as conn:
        row = conn.execute("SELECT * FROM two_factor_auth WHERE email = ?", (email,)).fetchone()
        if not row or not row["last_verified_at"]:
            return True
            
        elapsed = now - row["last_verified_at"]
        if elapsed > (days * 86400):
            return True
            
    return False

def record_2fa_verification(email: str):
    """Records successful 2FA verification timestamp."""
    email = (email or "").strip().lower()
    if not email:
        return
    now = time.time()
    with _get_db() as conn:
        conn.execute("""
            INSERT INTO two_factor_auth (email, last_verified_at)
            VALUES (?, ?)
            ON CONFLICT(email) DO UPDATE SET last_verified_at = ?
        """, (email, now, now))
        conn.commit()

# --- AUDIT LOGS ---

def log_audit(email: str, role: str, action: str, details: str, ip_address: str = ""):
    """Records an audit log entry."""
    email = (email or "System").strip()
    role = (role or "System").strip()
    action = (action or "EVENT").strip().upper()
    details = (details or "").strip()
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    
    try:
        with _get_db() as conn:
            conn.execute("""
                INSERT INTO audit_logs (timestamp, user_email, user_role, action, details, ip_address)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (timestamp, email, role, action, details, ip_address))
            conn.commit()
    except Exception as e:
        logger.error(f"Failed to record audit log: {e}")

def get_audit_logs(page: int = 1, per_page: int = 10, search: str = "", action_filter: str = ""):
    """
    Fetches paginated audit logs with search and action filtering.
    Returns: dict with logs, total, page, per_page, total_pages.
    """
    page = max(1, int(page))
    per_page = max(1, int(per_page))
    offset = (page - 1) * per_page
    
    where_clauses = []
    params = []
    
    if search and search.strip():
        s = f"%{search.strip()}%"
        where_clauses.append("(user_email LIKE ? OR details LIKE ? OR action LIKE ?)")
        params.extend([s, s, s])
        
    if action_filter and action_filter.strip():
        where_clauses.append("action = ?")
        params.append(action_filter.strip().upper())
        
    where_sql = " WHERE " + " AND ".join(where_clauses) if where_clauses else ""
    
    with _get_db() as conn:
        total_row = conn.execute(f"SELECT COUNT(*) as cnt FROM audit_logs{where_sql}", params).fetchone()
        total = total_row["cnt"] if total_row else 0
        
        total_pages = (total + per_page - 1) // per_page if total > 0 else 1
        
        rows = conn.execute(f"""
            SELECT * FROM audit_logs{where_sql}
            ORDER BY id DESC
            LIMIT ? OFFSET ?
        """, (*params, per_page, offset)).fetchall()
        
        logs = [dict(r) for r in rows]
        
    return {
        "logs": logs,
        "total": total,
        "page": page,
        "per_page": per_page,
        "total_pages": total_pages
    }
