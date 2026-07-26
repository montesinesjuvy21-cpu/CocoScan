import os
import requests
from dotenv import load_dotenv

load_dotenv()

brevo_api_key = os.getenv("BREVO_API_KEY", "").strip()
recipient_email = os.getenv("TEST_EMAIL", "noreply@cocoscan.ph").strip()

if not brevo_api_key:
    print("ERROR: BREVO_API_KEY not set in .env")
    exit(1)

print(f"Sending test email via Brevo to {recipient_email}")

try:
    url = "https://api.brevo.com/v3/smtp/email"
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "api-key": brevo_api_key
    }
    payload = {
        "sender": {"name": "CocoScan Test", "email": "noreply@cocoscan.ph"},
        "to": [{"email": recipient_email}],
        "subject": "Test email from CocoScan via Brevo",
        "htmlContent": "<p>This is a test email sent via Brevo API.</p>"
    }
    
    response = requests.post(url, json=payload, headers=headers, timeout=10)
    
    if response.status_code in [200, 201]:
        print("Email sent successfully!")
        print(f"Response: {response.json()}")
    else:
        print(f"Failed to send email. Status: {response.status_code}")
        print(f"Response: {response.text}")
except Exception as e:
    print(f"Failed to send email: {e}")
