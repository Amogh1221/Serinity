import os
import requests
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

    # Cloud Mode: Send via Brevo
    brevo_api_key = os.getenv("BREVO_API_KEY")
    if not brevo_api_key:
        logger.error("BREVO_API_KEY is not set in environment variables.")
        return False

    url = "https://api.brevo.com/v3/smtp/email"
    headers = {
        "accept": "application/json",
        "api-key": brevo_api_key,
        "content-type": "application/json"
    }
    
    payload = {
        "sender": {
            "name": "Serinity AI",
            "email": "noreply@serinity.ai"
        },
        "to": [
            {
                "email": to_email
            }
        ],
        "subject": subject,
        "htmlContent": f"<html><body><p>{body_text}</p></body></html>"
    }

    try:
        response = requests.post(url, json=payload, headers=headers, timeout=10)
        response.raise_for_status()
        logger.info(f"Email sent successfully via Brevo to {to_email}")
        return True
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to send email via Brevo: {str(e)}")
        if hasattr(e, 'response') and e.response is not None:
            logger.error(f"Brevo API Response: {e.response.text}")
        return False
