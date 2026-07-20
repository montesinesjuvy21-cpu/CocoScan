import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv

load_dotenv()

smtp_server = os.getenv("MAIL_SERVER", "smtp.gmail.com").strip()
smtp_port = int(os.getenv("MAIL_PORT", 587))
sender_email = (os.getenv("MAIL_USERNAME") or "").strip()
sender_password = (os.getenv("MAIL_PASSWORD") or "").strip()

print(f"Connecting to {smtp_server}:{smtp_port} as {sender_email}")
try:
    server = smtplib.SMTP(smtp_server, smtp_port, timeout=10)
    server.starttls()
    server.login(sender_email, sender_password)
    
    msg = MIMEMultipart()
    msg['From'] = sender_email
    msg['To'] = sender_email
    msg['Subject'] = "Test email"
    msg.attach(MIMEText("This is a test email.", 'plain'))
    
    server.sendmail(sender_email, sender_email, msg.as_string())
    server.quit()
    print("Email sent successfully!")
except Exception as e:
    print(f"Failed to send email: {e}")
