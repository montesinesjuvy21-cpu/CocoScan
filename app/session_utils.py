"""
Session utility helpers and custom session interface for CocoScan.
Implements Farmer-exclusive Remember Me persistence:
- Farmers: 90 days maximum duration, with 30-day sliding inactivity expiration
- Non-Farmer Roles (Admin, LGU, Agriculturist): Standard sessions (no persistent remember tokens)
- Standard Active Session Inactivity Timeout: 15 minutes (900 seconds)
"""
from datetime import datetime, timezone, timedelta
from flask.sessions import SecureCookieSessionInterface
from app.route_utils import normalize_role

# Inactivity timeout for standard active sessions (15 minutes)
INACTIVITY_TIMEOUT_SECONDS = 900

# Farmer-exclusive Remember Me duration settings
FARMER_REMEMBER_MAX_DAYS = 90
FARMER_REMEMBER_MAX_SECONDS = FARMER_REMEMBER_MAX_DAYS * 24 * 60 * 60

FARMER_REMEMBER_INACTIVITY_DAYS = 30
FARMER_REMEMBER_INACTIVITY_SECONDS = FARMER_REMEMBER_INACTIVITY_DAYS * 24 * 60 * 60

# Remember Me persistent duration mapping (Farmer only)
ROLE_REMEMBER_ME_DAYS = {
    'farmer': 90,
}

REMEMBER_COOKIE_NAME = "cocoscan_remember_token"


def is_farmer_role(role: str) -> bool:
    """Check if the given role is eligible for Remember Me (Farmer only)."""
    return normalize_role(role) in ['farmer', 'offline_farmer']


def get_remember_me_days(role: str) -> int:
    """Return the Remember Me lifetime in days (90 for farmers, 0 for other roles)."""
    norm = normalize_role(role)
    return ROLE_REMEMBER_ME_DAYS.get(norm, 0)


def get_remember_me_lifetime_seconds(role: str) -> int:
    """Return the Remember Me lifetime in seconds for the given role."""
    return get_remember_me_days(role) * 24 * 60 * 60


class RoleBasedSessionInterface(SecureCookieSessionInterface):
    """
    Custom Flask SecureCookieSessionInterface that sets cookie expiration
    dynamically for Farmers when session.permanent is True.
    """
    def get_expiration_time(self, app, session):
        if session.permanent:
            role = session.get('user_role', '')
            days = get_remember_me_days(role)
            if days > 0:
                return datetime.now(timezone.utc) + timedelta(days=days)
        return None

