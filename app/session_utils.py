"""
Session utility helpers and custom session interface for CocoScan.
Implements role-based session lifetimes for the hybrid session approach:
- Farmers: 90 days
- LGU / Agriculturists: 14 days
- Admins: 7 days
- Inactivity Timeout: 15 minutes (900 seconds)
"""
from datetime import datetime, timezone, timedelta
from flask.sessions import SecureCookieSessionInterface
from app.route_utils import normalize_role

# Inactivity timeout for standard active sessions (15 minutes)
INACTIVITY_TIMEOUT_SECONDS = 900

# Remember Me persistent duration mapping in days per normalized role
ROLE_REMEMBER_ME_DAYS = {
    'farmer': 90,
    'lgu': 14,
    'agri_expert': 14,
    'admin': 7,
}

REMEMBER_COOKIE_NAME = "cocoscan_remember_token"


def get_remember_me_days(role: str) -> int:
    """Return the Remember Me lifetime in days for the given role."""
    norm = normalize_role(role)
    return ROLE_REMEMBER_ME_DAYS.get(norm, 7)


def get_remember_me_lifetime_seconds(role: str) -> int:
    """Return the Remember Me lifetime in seconds for the given role."""
    return get_remember_me_days(role) * 24 * 60 * 60


class RoleBasedSessionInterface(SecureCookieSessionInterface):
    """
    Custom Flask SecureCookieSessionInterface that sets cookie expiration
    dynamically based on the user's role when session.permanent is True.
    """
    def get_expiration_time(self, app, session):
        if session.permanent:
            role = session.get('user_role', '')
            days = get_remember_me_days(role)
            return datetime.now(timezone.utc) + timedelta(days=days)
        return None
