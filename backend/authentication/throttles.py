from rest_framework.throttling import SimpleRateThrottle


class OTPPhoneThrottle(SimpleRateThrottle):
    scope = "otp_phone"

    def get_cache_key(self, request, view):
        phone_number = request.data.get("phone_number")
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
