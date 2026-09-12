import os
import sys
import pytest
from flask import session

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from main import app

@pytest.fixture
def client():
    app.config['TESTING'] = True
    app.config['SECRET_KEY'] = 'test-secret-key-for-pwa-tests'
    with app.test_client() as client:
        yield client

def test_security_cache_headers_on_sensitive_routes(client):
    """Ensure sensitive route requests receive no-store cache headers to protect back navigation."""
    routes_to_test = [
        '/api/auth/session-check',
        '/admin/dashboard',
        '/lgu/dashboard',
        '/agriculturist/dashboard',
        '/farmer/dashboard'
    ]
    for route in routes_to_test:
        resp = client.get(route)
        cache_control = resp.headers.get('Cache-Control', '')
        assert 'no-store' in cache_control, f"Route {route} missing no-store in Cache-Control"
        assert 'no-cache' in cache_control, f"Route {route} missing no-cache in Cache-Control"
        assert 'must-revalidate' in cache_control, f"Route {route} missing must-revalidate in Cache-Control"
        assert resp.headers.get('Pragma') == 'no-cache'

def test_session_check_unauthenticated(client):
    """Session check endpoint must return 401 unauthenticated when no session or cookie exists."""
    resp = client.get('/api/auth/session-check')
    assert resp.status_code == 401
    data = resp.get_json()
    assert data['authenticated'] is False
    assert data['role'] is None

def test_session_check_authenticated(client):
    """Session check endpoint must return 200 and user metadata when session is valid."""
    with client.session_transaction() as sess:
        sess['user_id'] = 'admin-user-uuid-123'
        sess['user_role'] = 'admin'
        sess['user_email'] = 'admin@cocoscan.org'
        sess['user_name'] = 'System Administrator'

    resp = client.get('/api/auth/session-check')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['authenticated'] is True
    assert data['role'] == 'admin'
    assert data['user_id'] == 'admin-user-uuid-123'
    assert data['email'] == 'admin@cocoscan.org'

def test_login_page_renders_pwa_install_banner(client):
    """Login page must include the dedicated bottom PWA install prompt banner with close button."""
    resp = client.get('/login')
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert 'pwa-install-banner' in html
    assert 'pwa-trigger-btn' in html
    assert 'pwa-dismiss-btn' in html

def test_header_back_button_and_pwa_scripts_presence(client):
    """Dashboard views must render the in-app back navigation button and pwa_scripts component."""
    with client.session_transaction() as sess:
        sess['user_id'] = 'farmer-test-123'
        sess['user_role'] = 'farmer'
        sess['user_name'] = 'Farmer Juan'

    resp = client.get('/farmer/dashboard')
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert 'btn-inapp-back' in html
    assert 'handleInAppBackNavigation()' in html
    assert 'fa-chevron-left' in html
    assert 'pwa-install-banner' in html

def test_farmer_scan_hybrid_upload_elements(client):
    """Farmer scan page must render hybrid camera and upload triggers, location modal, and offline modal."""
    with client.session_transaction() as sess:
        sess['user_id'] = 'farmer-test-123'
        sess['user_role'] = 'farmer'
        sess['user_name'] = 'Farmer Juan'

    resp = client.get('/farmer/scan')
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    # Hybrid action triggers
    assert 'hidden-camera-input' in html
    assert 'hidden-upload-input' in html
    assert 'triggerNativeCamera()' in html
    assert 'triggerPhotoUpload()' in html
    assert 'Use Camera' in html
    assert 'Upload Photo' in html

    # Location Selection Modal for uploaded photos
    assert 'upload-location-modal' in html
    assert 'upload-location-map' in html
    assert 'manual-location-text' in html
    assert 'confirmUploadLocationAndScan()' in html
    assert 'cancelUploadLocationModal()' in html
    assert 'fetchDeviceLocationForMap()' in html

    # Offline saved modal
    assert 'offline-saved-modal' in html
    assert 'dismissOfflineSavedModal()' in html
    assert 'leaflet' in html.lower()

from unittest.mock import MagicMock
from app.report_storage import build_report_payload

def test_build_report_payload_with_manual_location():
    """Verify build_report_payload stores custom geocoded barangay, municipality, province, and source."""
    payload = build_report_payload(
        user_id="a0000000-0000-0000-0000-000000000001",
        pest_type="Coconut Leaf Beetle",
        farmer_notes="Found near western field boundary",
        confidence="92.5",
        latitude="13.9314",
        longitude="121.6172",
        gps_accuracy="10",
        location_source="map_pin",
        photo_taken_at="2026-09-12T14:00:00Z",
        initial_recommendations=["Prune infested fronds"],
        farmer_name="Juan Farmer",
        barangay="San Isidro",
        municipality="Lucena City",
        province="Quezon",
    )
    assert payload["latitude"] == 13.9314
    assert payload["longitude"] == 121.6172
    assert payload["location_source"] == "map_pin"
    assert payload["barangay"] == "San Isidro"
    assert payload["municipality"] == "Lucena City"
    assert payload["province"] == "Quezon"

def test_farmer_submit_report_with_manual_location(client, monkeypatch):
    """Farmer submit-report endpoint should accept and process manual/pin location coordinates & metadata."""
    with client.session_transaction() as sess:
        sess['user_id'] = 'a0000000-0000-0000-0000-000000000001'
        sess['user_role'] = 'farmer'
        sess['user_name'] = 'Farmer Juan'

    # Mock supabase client calls in main.py
    mock_table = MagicMock()
    mock_insert = MagicMock()
    mock_insert.execute.return_value = MagicMock(data=[{'id': 'report-uuid-999'}], error=None)
    mock_select = MagicMock()
    mock_select.eq.return_value.execute.return_value = MagicMock(data=[{'first_name': 'Juan', 'last_name': 'Farmer'}])
    mock_update = MagicMock()
    mock_update.eq.return_value.execute.return_value = MagicMock(data=[{'id': 'report-uuid-999'}])

    mock_table.insert.return_value = mock_insert
    mock_table.select.return_value = mock_select
    mock_table.update.return_value = mock_update

    mock_supabase = MagicMock()
    mock_supabase.table.return_value = mock_table

    import main
    monkeypatch.setattr(main, 'supabase', mock_supabase)
    monkeypatch.setattr(main, 'upload_image_to_supabase', lambda *args, **kwargs: 'https://storage/test.jpg')

    # Send a dummy report submission with manual location data
    report_data = {
        'pest_type': 'Coconut Leaf Beetle',
        'farmer_notes': 'Observed symptoms near western boundary',
        'location_notes': 'Barangay San Isidro, Lucena City',
        'confidence': '92',
        'gps_latitude': '13.9314',
        'gps_longitude': '121.6172',
        'gps_accuracy': '10',
        'location_source': 'map_pin',
        'barangay': 'San Isidro',
        'municipality': 'Lucena City',
        'province': 'Quezon',
        'photo_taken_at': '2026-09-12T14:00:00Z',
        'image_url': 'data:image/jpeg;base64,/9j/4AAQSkZJRgABAQEASABIAAD/2wBDAP//////////////////////////////////////////////////////////////////////////////////////wgALCAABAAEBAREA/8QAFBABAAAAAAAAAAAAAAAAAAAAAP/aAAgBAQABPxA='
    }

    resp = client.post('/farmer/submit-report', data=report_data)
    assert resp.status_code == 200
    res_json = resp.get_json()
    assert res_json.get('success') is True


