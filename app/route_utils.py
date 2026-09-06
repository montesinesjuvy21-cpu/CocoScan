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

def require_role(*roles):
    """
    Decorator to require a user to have a specific role or one of multiple roles.
    Expects roles in lower case (e.g. 'farmer', 'agriculturist', 'lgu', 'admin').
    If the request is an API request (JSON) or starts with '/api', it returns JSON error.
    Otherwise, flashes an error and redirects to login.
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            user_id = session.get('user_id')
            user_role = normalize_role(session.get('user_role'))
            
            if not user_id or user_role not in [r.lower() for r in roles]:
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
