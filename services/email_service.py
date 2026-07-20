import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional
from core.logger import serinity_logger as logger

def send_otp_email(to_email: str, subject: str, otp_code: str, body_text: Optional[str] = None):
    """
    Sends an OTP email either via Brevo (if CLOUD_MODE=true) or to the terminal (if CLOUD_MODE=false).
    """
    cloud_mode = os.getenv("CLOUD_MODE", "false").lower() == "true"
    
    # Format the body message
    if not body_text:
        body_text = f"Your verification code is: {otp_code}"
    else:
        body_text = body_text.replace("{otp_code}", otp_code)

    if not cloud_mode:
        # Local Mode: Print to terminal
        print(f"\n" + "="*40)
        print(f"[LOCAL EMAIL SIMULATION]")
        print(f"To: {to_email}")
        print(f"Subject: {subject}")
        print(f"Body:\n{body_text}")
        print(f"="*40 + "\n")
        logger.info(f"Local email simulated for {to_email} (Subject: {subject})")
        return True

    # Cloud Mode: Send via Gmail SMTP
    gmail_user = os.getenv("BREVO_SENDER_EMAIL")  # using the same variable name you already have!
    gmail_app_password = os.getenv("GMAIL_APP_PASSWORD")

    if not gmail_user or not gmail_app_password:
        logger.error("BREVO_SENDER_EMAIL or GMAIL_APP_PASSWORD is not set in environment variables.")
        return False

    msg = MIMEMultipart()
    msg['From'] = f"Serinity AI <{gmail_user}>"
    msg['To'] = to_email
    msg['Subject'] = subject

    msg.attach(MIMEText(f"<html><body><p>{body_text}</p></body></html>", 'html'))

    try:
        # Connect to Gmail's SMTP server
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        # Login with App Password
        server.login(gmail_user, gmail_app_password)
        # Send email
        server.send_message(msg)
        server.quit()
        
        logger.info(f"Email sent successfully via Gmail SMTP to {to_email}")
        return True
    except Exception as e:
        logger.error(f"Failed to send email via Gmail SMTP: {str(e)}")
        return False
