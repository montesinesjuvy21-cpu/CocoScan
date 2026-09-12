import logging
from functools import wraps
from flask import session, flash, redirect, url_for, jsonify, request
from app import security_service

logger = logging.getLogger(__name__)

def normalize_role(value) -> str:
    raw = str(value or "").strip().lower()
    if raw in ['admin', 'administrator']:
        return 'admin'
    if raw in ['agri_expert', 'agriculturist', 'agriculture_expert', 'expert']:
        return 'agri_expert'
    if raw in ['lgu', 'lgu_officer']:
        return 'lgu'
    if raw in ['farmer']:
        return 'farmer'
    return raw

def get_role_dashboard_url(role: str) -> str:
    """Return direct dashboard endpoint URL for a given normalized role."""
    normalized = normalize_role(role)
    if normalized == 'farmer':
        return url_for('farmer_dashboard')
    elif normalized == 'agri_expert':
        return url_for('agri_dashboard')
    elif normalized == 'lgu':
        return url_for('lgu_dashboard')
    elif normalized == 'admin':
        return url_for('admin_dashboard')
    return url_for('login')

def resolve_user_fullname(first_name_or_dict=None, last_name=None, email=None, default="Farmer") -> str:
    """
    Safely resolve a user's full name from Supabase user records or session data,
    preventing 'None', 'None None', 'null', or empty names from leaking into templates.
    """
    if isinstance(first_name_or_dict, dict):
        fn = first_name_or_dict.get('first_name')
        ln = first_name_or_dict.get('last_name')
        email = email or first_name_or_dict.get('email')
    else:
        fn = first_name_or_dict
        ln = last_name

    fn_str = str(fn or '').strip()
    ln_str = str(ln or '').strip()

    invalid_tokens = {'none', 'null', 'undefined'}
    if fn_str.lower() in invalid_tokens:
        fn_str = ''
    if ln_str.lower() in invalid_tokens:
        ln_str = ''

    full = f"{fn_str} {ln_str}".strip()

    if not full or full.lower() in ['none', 'none none', 'null', 'undefined']:
        if email and '@' in str(email):
            derived = str(email).split('@')[0].replace('.', ' ').replace('_', ' ').replace('-', ' ').title()
            if derived and derived.lower() not in ['none', 'none none', 'null', 'undefined']:
                return derived
        return default
    return full



def require_role(*roles):
    """
    Decorator to require a user to have a specific role or one of multiple roles.
    Expects roles in lower case or standard format (e.g. 'farmer', 'agriculturist', 'lgu', 'admin').
    If the request is an API request (JSON) or starts with '/api', it returns JSON error.
    Otherwise, flashes an error and redirects to login.
    """
    allowed_roles = [normalize_role(r) for r in roles]

    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            user_id = session.get('user_id')
            user_role = normalize_role(session.get('user_role'))
            user_email = session.get('user_email') or request.cookies.get('cocoscan_user_email')
            offline_cookie = request.cookies.get('cocoscan_offline_active')

            # Support offline farmer session fallback ONLY for farmer routes
            if 'farmer' in allowed_roles:
                if not user_id or user_id == 'offline_farmer':
                    if offline_cookie == 'true' or (request.cookies.get('cocoscan_user_role') == 'farmer'):
                        session['user_id'] = 'offline_farmer'
                        session['user_role'] = 'farmer'
                        if user_email and not session.get('user_email'):
                            session['user_email'] = user_email
                        user_id = session.get('user_id')
                        user_role = session.get('user_role')

            if not user_id or user_role not in allowed_roles:
                # If user is authenticated with a different valid role, redirect them to their correct role dashboard
                if user_id and user_role and user_id != 'offline_farmer':
                    logger.info(f"User with role '{user_role}' attempted to access {request.path} (allowed: {allowed_roles}). Redirecting to {user_role} dashboard.")
                    return redirect(get_role_dashboard_url(user_role))

                error_msg = "Unauthorized access path. Please log in."
                
                # Check if API request or POST request
                if request.is_json or request.path.startswith('/api/') or request.method == 'POST':
                    return jsonify({'success': False, 'error': 'Unauthorized access'}), 403
                
                flash(error_msg, "error")
                return redirect(url_for('login'))
                
            return f(*args, **kwargs)
        return decorated_function
    return decorator

# Common Supabase Helpers
def fetch_user_reports(supabase, user_id, limit=6):
    """Fetch recent reports for a user."""
    try:
        response = supabase.table('reports').select('*, visit_chats(count)').eq('user_id', user_id).order('created_at', desc=True).limit(limit).execute()
        return getattr(response, 'data', []) or []
    except Exception as e:
        logger.error(f"Error fetching user reports: {e}")
        return []

