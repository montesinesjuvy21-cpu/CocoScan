import os
import sys
import time
import uuid
import pytest
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.session_utils import (
    get_remember_me_days,
    get_remember_me_lifetime_seconds,
    RoleBasedSessionInterface,
    ROLE_REMEMBER_ME_DAYS,
    REMEMBER_COOKIE_NAME,
    INACTIVITY_TIMEOUT_SECONDS
)
from app import security_service
import main
from main import app


def test_role_based_expiration_days():
    """Verify role-based Remember Me duration mapping."""
    assert get_remember_me_days('farmer') == 90
    assert get_remember_me_lifetime_seconds('farmer') == 90 * 24 * 60 * 60

    assert get_remember_me_days('lgu') == 14
    assert get_remember_me_lifetime_seconds('lgu') == 14 * 24 * 60 * 60

    assert get_remember_me_days('agri_expert') == 14
    assert get_remember_me_days('agriculturist') == 14
    assert get_remember_me_lifetime_seconds('agri_expert') == 14 * 24 * 60 * 60

    assert get_remember_me_days('admin') == 7
    assert get_remember_me_days('administrator') == 7
    assert get_remember_me_lifetime_seconds('admin') == 7 * 24 * 60 * 60

    # Default fallback
    assert get_remember_me_days('unknown_role') == 7


def test_role_based_session_interface_expiration():
    """Verify custom RoleBasedSessionInterface calculates correct expiration."""
    interface = RoleBasedSessionInterface()

    # Non-permanent session -> None
    session_mock = {'user_role': 'farmer'}
    session_mock_obj = type('MockSession', (dict,), {'permanent': False})(session_mock)
    assert interface.get_expiration_time(app, session_mock_obj) is None

    # Permanent session for farmer -> 90 days from now
    session_mock_obj.permanent = True
    now = datetime.now(timezone.utc)
    exp_farmer = interface.get_expiration_time(app, session_mock_obj)
    assert exp_farmer is not None
    assert 89 <= (exp_farmer - now).days <= 91

    # Permanent session for LGU -> 14 days
    session_mock_obj['user_role'] = 'lgu'
    exp_lgu = interface.get_expiration_time(app, session_mock_obj)
    assert exp_lgu is not None
    assert 13 <= (exp_lgu - now).days <= 15

    # Permanent session for Admin -> 7 days
    session_mock_obj['user_role'] = 'admin'
    exp_admin = interface.get_expiration_time(app, session_mock_obj)
    assert exp_admin is not None
    assert 6 <= (exp_admin - now).days <= 8


def test_remember_token_lifecycle():
    """Verify Remember Me token creation, validation, expiration, and revocation in security_service."""
    email = "test_farmer_persist@example.com"
    user_id = str(uuid.uuid4())
    role = "farmer"
    user_name = "Farmer John"

    # 1. Create token
    raw_token, expires_at = security_service.create_remember_token(user_id, email, role, user_name)
    assert isinstance(raw_token, str)
    assert len(raw_token) > 20
    assert expires_at > time.time() + (89 * 86400)

    # 2. Validate token
    token_data = security_service.validate_remember_token(raw_token)
    assert token_data is not None
    assert token_data['user_id'] == user_id
    assert token_data['email'] == email
    assert token_data['role'] == role
    assert token_data['user_name'] == user_name

    # 3. Invalid token returns None
    assert security_service.validate_remember_token("invalid-token-value") is None
    assert security_service.validate_remember_token("") is None

    # 4. Revoke token
    revoked = security_service.revoke_remember_token(raw_token)
    assert revoked is True
    assert security_service.validate_remember_token(raw_token) is None

    # 5. Revoke all user tokens
    t1, _ = security_service.create_remember_token(user_id, email, role, user_name)
    t2, _ = security_service.create_remember_token(user_id, email, role, user_name)
    count = security_service.revoke_all_user_remember_tokens(email)
    assert count >= 2
    assert security_service.validate_remember_token(t1) is None
    assert security_service.validate_remember_token(t2) is None


def test_login_page_renders_remember_me_checkbox():
    """Verify that the login page UI includes the Remember Me checkbox."""
    app.config.update(TESTING=True)
    with app.test_client() as client:
        response = client.get('/login')
        assert response.status_code == 200
        html = response.get_data(as_text=True)
        assert 'id="remember_me"' in html
        assert 'name="remember_me"' in html
        assert 'Remember Me' in html


def test_hybrid_inactivity_and_remember_me_restoration():
    """Verify hybrid session: standard session times out, while remember token restores session."""
    app.config.update(TESTING=True)
    with app.test_client() as client:
        test_uid = str(uuid.uuid4())
        # Scenario A: Non-remembered session times out after 15m (900s)
        with client.session_transaction() as sess:
            sess['user_id'] = test_uid
            sess['user_email'] = 'timeout@example.com'
            sess['user_role'] = 'farmer'
            sess['user_name'] = 'Farmer Timeout'
            sess['remember_me'] = False
            sess['last_active'] = time.time() - 950  # 950 seconds ago (> 900s)

        response = client.get('/dashboard', follow_redirects=False)
        assert response.status_code == 302
        assert '/login' in response.headers.get('Location', '')
        
        # Verify session was cleared
        with client.session_transaction() as sess:
            assert 'user_id' not in sess

        # Scenario B: Remembered session auto-restores via remember token cookie when session was cleared
        restore_uid = str(uuid.uuid4())
        raw_token, _ = security_service.create_remember_token(
            restore_uid,
            'restored@example.com',
            'farmer',
            'Farmer Restored'
        )
        client.set_cookie(REMEMBER_COOKIE_NAME, raw_token)

        response = client.get('/dashboard', follow_redirects=False)
        assert response.status_code == 302
        assert '/farmer/dashboard' in response.headers.get('Location', '')
        with client.session_transaction() as sess:
            assert sess.get('user_id') == restore_uid
            assert sess.get('user_email') == 'restored@example.com'
            assert sess.get('remember_me') is True


def test_logout_revokes_remember_token_and_cookie():
    """Verify logging out deletes the remember token from DB and removes cookie."""
    app.config.update(TESTING=True)
    with app.test_client() as client:
        test_uid = str(uuid.uuid4())
        raw_token, _ = security_service.create_remember_token(
            test_uid,
            'logout@example.com',
            'admin',
            'Admin User'
        )
        client.set_cookie(REMEMBER_COOKIE_NAME, raw_token)
        with client.session_transaction() as sess:
            sess['user_id'] = test_uid
            sess['user_email'] = 'logout@example.com'
            sess['user_role'] = 'admin'
            sess['remember_me'] = True

        response = client.get('/logout', follow_redirects=False)
        assert response.status_code == 302
        assert '/login' in response.headers.get('Location', '')

        # Token must be revoked in DB
        assert security_service.validate_remember_token(raw_token) is None
        # Cookie must be cleared in response headers
        set_cookie_headers = response.headers.getlist('Set-Cookie')
        assert any(REMEMBER_COOKIE_NAME in h and ('Max-Age=0' in h or 'Expires=' in h or '""' in h) for h in set_cookie_headers)
