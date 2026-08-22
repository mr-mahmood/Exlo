import json
import logging
import http.client
from celery import shared_task
from django.conf import settings

logger = logging.getLogger(__name__)


@shared_task
def send_sms_verification_task(phone_number: str, otp_code: str):
    """Send OTP verification code via SMS.ir template"""
    try:
        conn = http.client.HTTPSConnection("api.sms.ir")

        payload = json.dumps(
            {
                "mobile": phone_number,
                "templateId": 1111111,
                "parameters": [{"name": "OTP", "value": otp_code}],
            }
        )

        headers = {
            "Content-Type": "application/json",
            "x-api-key": settings.SMSIR_API_KEY,
        }

        conn.request("POST", "/v1/send/verify", payload, headers)
        res = conn.getresponse()

        if res.status == 200:
            return True

        logger.error(f"SMS failed: {res.status}")

    except Exception as e:
        logger.error(f"Error: {e}")
    finally:
        conn.close()
