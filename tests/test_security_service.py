import unittest
import os
import sys
import sqlite3
import time
import gc
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from app import security_service

class TestSecurityService(unittest.TestCase):
    def setUp(self):
        # Create a clean temporary test database in scratch/tmp location
        self.test_db = os.path.join(os.path.dirname(__file__), f"test_security_{time.time_ns()}.db")
        security_service.DB_PATH = self.test_db
        security_service.init_security_db()

    def tearDown(self):
        gc.collect()
        if os.path.exists(self.test_db):
            try:
                os.remove(self.test_db)
            except Exception:
                pass

    def test_account_lockout(self):
        email = "test@example.com"
        # Attempt 1
        cnt, locked, msg = security_service.record_login_failure(email, "127.0.0.1")
        self.assertEqual(cnt, 1)
        self.assertIsNone(locked)

        # Attempt 2
        cnt, locked, msg = security_service.record_login_failure(email, "127.0.0.1")
        self.assertEqual(cnt, 2)

        # Attempt 3 - should lock for 15 minutes
        cnt, locked, msg = security_service.record_login_failure(email, "127.0.0.1")
        self.assertEqual(cnt, 3)
        self.assertIsNotNone(locked)
        self.assertIn("15 minutes", msg)

        # Check lockout
        is_locked, rem, reason = security_service.check_account_lockout(email)
        self.assertTrue(is_locked)
        self.assertGreater(rem, 800)

        # Reset failures
        security_service.reset_login_failures(email)
        is_locked, rem, reason = security_service.check_account_lockout(email)
        self.assertFalse(is_locked)

    def test_2fa_requirement(self):
        email = "admin@example.com"
        # Should require 2fa initially
        self.assertTrue(security_service.requires_2fa(email, days=7))
        
        # Record verification
        security_service.record_2fa_verification(email)
        self.assertFalse(security_service.requires_2fa(email, days=7))

    def test_audit_logs(self):
        security_service.log_audit("admin@example.com", "admin", "LOGIN", "Test audit log", "127.0.0.1")
        logs_data = security_service.get_audit_logs(page=1, per_page=10)
        self.assertGreaterEqual(logs_data['total'], 1)
        self.assertEqual(logs_data['logs'][0]['action'], "LOGIN")

if __name__ == '__main__':
    unittest.main()
