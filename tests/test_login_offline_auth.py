import unittest
from unittest.mock import patch, MagicMock
from main import app, get_role_dashboard_url
from app.route_utils import normalize_role
from app.password_utils import hash_password


class TestLoginOfflineAuth(unittest.TestCase):
    def setUp(self):
        self.app = app
        self.app.config['TESTING'] = True
        self.app.config['WTF_CSRF_ENABLED'] = False
        self.client = self.app.test_client()

    def test_role_normalization_and_dashboard_urls(self):
        self.assertEqual(normalize_role('Farmer'), 'farmer')
        self.assertEqual(normalize_role('admin'), 'admin')
        self.assertEqual(normalize_role('agriculturist'), 'agri_expert')
        self.assertEqual(normalize_role('agri_expert'), 'agri_expert')
        self.assertEqual(normalize_role('lgu'), 'lgu')

        with self.app.test_request_context():
            self.assertEqual(get_role_dashboard_url('farmer'), '/farmer/dashboard')
            self.assertEqual(get_role_dashboard_url('agri_expert'), '/agriculturist/dashboard')
            self.assertEqual(get_role_dashboard_url('admin'), '/admin/dashboard')
            self.assertEqual(get_role_dashboard_url('lgu'), '/lgu/dashboard')

    def test_login_missing_fields_json(self):
        response = self.client.post('/login', json={'email': '', 'password': ''})
        self.assertEqual(response.status_code, 400)
        data = response.get_json()
        self.assertFalse(data['success'])
        self.assertIn('Please enter both email and password', data['error'])

    @patch('main.supabase')
    @patch('main.security_service.check_account_lockout', return_value=(False, 0, ''))
    @patch('main.security_service.record_login_failure', return_value=(1, None, ''))
    def test_login_user_not_found_json(self, mock_rec_fail, mock_lockout, mock_supabase):
        mock_supabase.table().select().eq().execute.return_value = MagicMock(data=[])

        response = self.client.post('/login', json={
            'email': 'nonexistent@example.com',
            'password': 'Password123!'
        })
        self.assertEqual(response.status_code, 401)
        data = response.get_json()
        self.assertFalse(data['success'])
        self.assertIn('Account not found or invalid credentials', data['error'])

    @patch('main.supabase')
    @patch('main.security_service.check_account_lockout', return_value=(False, 0, ''))
    @patch('main.security_service.reset_login_failures')
    @patch('main.security_service.log_audit')
    def test_login_successful_farmer_json(self, mock_audit, mock_reset_fail, mock_lockout, mock_supabase):
        hashed = hash_password('ValidPass123!')
        mock_user = {
            'id': 'farmer-uuid-1234',
            'email': 'farmer@example.com',
            'password_hash': hashed,
            'role': 'farmer',
            'status': 'Approved',
            'first_name': 'Juan',
            'last_name': 'Dela Cruz'
        }
        mock_supabase.table().select().eq().execute.return_value = MagicMock(data=[mock_user])

        response = self.client.post('/login', json={
            'email': 'farmer@example.com',
            'password': 'ValidPass123!'
        })
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertTrue(data['success'])
        self.assertEqual(data['redirect_url'], '/farmer/dashboard')
        self.assertEqual(data['user']['email'], 'farmer@example.com')
        self.assertEqual(data['user']['role'], 'farmer')
        self.assertEqual(data['user']['name'], 'Juan Dela Cruz')
        self.assertEqual(data['user']['id'], 'farmer-uuid-1234')

    @patch('main.supabase')
    @patch('main.security_service.check_account_lockout', return_value=(False, 0, ''))
    @patch('main.security_service.reset_login_failures')
    @patch('main.security_service.log_audit')
    @patch('main.security_service.requires_2fa', return_value=False)
    def test_login_successful_admin_json(self, mock_2fa, mock_audit, mock_reset_fail, mock_lockout, mock_supabase):
        hashed = hash_password('AdminPass123!')
        mock_user = {
            'id': 'admin-uuid-5678',
            'email': 'admin@cocoscan.gov.ph',
            'password_hash': hashed,
            'role': 'admin',
            'status': 'Approved',
            'first_name': 'PCA',
            'last_name': 'Admin'
        }
        mock_supabase.table().select().eq().execute.return_value = MagicMock(data=[mock_user])

        response = self.client.post('/login', json={
            'email': 'admin@cocoscan.gov.ph',
            'password': 'AdminPass123!'
        })
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertTrue(data['success'])
        self.assertEqual(data['redirect_url'], '/admin/dashboard')
        self.assertEqual(data['user']['role'], 'admin')

    def test_resolve_user_fullname_variants(self):
        from app.route_utils import resolve_user_fullname

        # 1. Normal valid names
        self.assertEqual(resolve_user_fullname("Juan", "Dela Cruz"), "Juan Dela Cruz")
        self.assertEqual(resolve_user_fullname({"first_name": "Maria", "last_name": "Santos"}), "Maria Santos")

        # 2. None / empty values
        self.assertEqual(resolve_user_fullname(None, None, default="Farmer"), "Farmer")
        self.assertEqual(resolve_user_fullname("", "", default="Farmer"), "Farmer")
        self.assertEqual(resolve_user_fullname({"first_name": None, "last_name": None}, default="Farmer"), "Farmer")

        # 3. String literals 'None', 'None None', 'null', 'undefined'
        self.assertEqual(resolve_user_fullname("None", "None", default="Farmer"), "Farmer")
        self.assertEqual(resolve_user_fullname({"first_name": "None", "last_name": None}, default="Farmer"), "Farmer")
        self.assertEqual(resolve_user_fullname({"first_name": "null", "last_name": "undefined"}, default="User"), "User")

        # 4. Fallback to derived email
        self.assertEqual(resolve_user_fullname(None, None, email="juan.cruz@cocoscan.local"), "Juan Cruz")
        self.assertEqual(resolve_user_fullname({"first_name": None, "last_name": None, "email": "pedro_santos@cocoscan.local"}), "Pedro Santos")
        self.assertEqual(resolve_user_fullname("None", None, email="clara-reyes@cocoscan.local"), "Clara Reyes")

    def test_offline_portal_page_renders(self):
        response = self.client.get('/offline')
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn('Retry Connection', html)
        self.assertIn('retry-btn', html)
        self.assertIn('countdown-timer-display', html)
        self.assertIn('Auto-logging out in', html)
        self.assertIn("Can't load right now, you're offline", html)
        self.assertIn('This portal and administrative features require an active internet connection.', html)
        self.assertNotIn('Log Out Now', html)
        self.assertNotIn('Go Back', html)

    def test_farmer_reports_offline_banner(self):
        self.client.set_cookie('cocoscan_offline_active', 'true')
        self.client.set_cookie('cocoscan_user_role', 'farmer')
        self.client.set_cookie('cocoscan_user_email', 'farmer@cocoscan.local')
        response = self.client.get('/farmer/reports')
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn('reports-offline-banner', html)
        self.assertIn('Reports were synced and will load once an active internet connection has been established.', html)

    def test_farmer_offline_cookie_access(self):
        self.client.set_cookie('cocoscan_offline_active', 'true')
        self.client.set_cookie('cocoscan_user_role', 'farmer')
        self.client.set_cookie('cocoscan_user_email', 'farmer@cocoscan.local')
        response = self.client.get('/farmer/dashboard')
        self.assertEqual(response.status_code, 200)

    def test_logout_clears_offline_cookies(self):
        self.client.set_cookie('cocoscan_offline_active', 'true')
        self.client.set_cookie('cocoscan_user_role', 'farmer')
        response = self.client.get('/logout')
        self.assertEqual(response.status_code, 302)
        cookies = response.headers.getlist('Set-Cookie')
        cookie_text = " ".join(cookies)
        self.assertIn('cocoscan_offline_active', cookie_text)

    def test_login_page_renders_offline_modal(self):
        response = self.client.get('/login')
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn('offline-login-modal', html)
        self.assertIn('offline-modal-ok-btn', html)
        self.assertIn('closeOfflineNoticePopupAndClearLogin', html)
        self.assertIn('resetLoginForm', html)
        self.assertIn('Okay', html)
        self.assertIn('-webkit-autofill', html)
        self.assertIn('outline: none !important;', html)
        self.assertIn('Offline credentials verified. Administrative tools require network connection.', html)


if __name__ == '__main__':
    unittest.main()

