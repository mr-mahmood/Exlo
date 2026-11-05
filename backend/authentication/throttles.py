from rest_framework.throttling import SimpleRateThrottle
from users.validators import validate_phone


class OTPPhoneThrottle(SimpleRateThrottle):
    scope = "otp_phone"

    def get_cache_key(self, request, view):
        phone_number = validate_phone(
            request.data.get("phone_number"),
            skip_duplicate_check=True,
        )
        if phone_number:
            return self.cache_format % {
                "scope": self.scope,
                "ident": phone_number,
            }
        return None


class OTPIPThrottle(SimpleRateThrottle):
    scope = "otp_ip"

    def get_cache_key(self, request, view):
        ip = self.get_ident(request)
        return self.cache_format % {
            "scope": self.scope,
            "ident": ip,
        }
