import requests
from django.conf import settings


# for more info https://help.zibal.ir/ipg
class ZibalIPG:
    BASE_URL = "https://gateway.zibal.ir"
    REQUEST_URL = f"{BASE_URL}/v1/request/"
    VERIFY_URL = f"{BASE_URL}/v1/verify/"
    START_PAGE = f"{BASE_URL}/start"

    def __init__(self):
        self.merchant = "zibal" if settings.DEBUG else settings.ZIBAL_MERCHANT
        self.fee = settings.ZIBAL_IPG_FEE_MAX

    def request_payment(self, *, amount, callback_url, order_id, mobile, description):
        payload = {
            "amount": amount,
            "callbackUrl": callback_url,
            "merchant": self.merchant,
            "description": description,
            "feeMode": 0,
            "mobile": mobile,
            "orderId": order_id,  # its the UUID of payment table, row
        }
        try:
            response = requests.post(
                self.REQUEST_URL,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=5,
            )
            return response.json()
        except Exception:
            return None

    def verify_payment(self, *, track_id):
        payload = {
            "merchant": self.merchant,
            "trackId": track_id,
        }
        try:
            response = requests.post(
                self.VERIFY_URL,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=5,
            )
            return response.json()
        except Exception:
            return None

    def start_url(self, track_id):
        return f"{self.START_PAGE}/{track_id}"


class ZibalEBank:
    BASE_URL = "https://api.zibal.ir"
    REFUND_URL = f"{BASE_URL}/v1/account/refund/"

    def __init__(self):
        self.fee = settings.ZIBAL_EBANK_FEE_MAX
        self.headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {settings.ZIBAL_API_TOKEN}",
        }

    def refund(self, *, track_id, amount, description):
        payload = {
            "trackId": int(track_id),
            "accountId": settings.ZIBAL_ACCOUNT_ID,
            "amount": amount,
            "description": description,
        }

        try:
            response = requests.post(
                self.REFUND_URL,
                json=payload,
                headers=self.headers,
                timeout=5,
            )
            return response.json()
        except Exception:
            return None
