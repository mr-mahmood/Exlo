# authentication/tests/test_otp.py
from django.test import TestCase
from django.core.cache import cache
from authentication.otp_service import generate_otp, verify_otp
from core.errors import APIError
from django.conf import settings


class OTPServiceTest(TestCase):
    """Test OTP service"""

    def setUp(self):
        cache.clear()

    def test_generate_otp_success(self):
        """Test generating OTP"""
        result = generate_otp("09123456789")

        self.assertTrue(result)

        # Check cache
        cache_key = f"otp_09123456789"
        self.assertIsNotNone(cache.get(cache_key))

    def test_verify_otp_success(self):
        """Test verifying correct OTP"""
        generate_otp("09123456789")

        result = verify_otp("09123456789", "123456")

        self.assertTrue(result)

        # Check cache cleared
        cache_key = f"otp_09123456789"
        self.assertIsNone(cache.get(cache_key))

    def test_verify_otp_wrong_code(self):
        """Test verifying wrong OTP"""
        generate_otp("09123456789")

        with self.assertRaises(APIError):
            verify_otp("09123456789", "999999")

    def test_verify_otp_expired(self):
        """Test verifying expired OTP"""
        # Don't generate OTP
        with self.assertRaises(APIError):
            verify_otp("09123456789", "123456")

    def test_otp_hash_security(self):
        generate_otp("09123456789")
        cache_key = f"otp_09123456789"
        stored = cache.get(cache_key)

        # Should not be plain text
        self.assertNotEqual(stored, "123456")
        self.assertNotEqual(stored, "")

        # Should be scheme-tagged: "hmac_sha256$<64 hex chars>"
        import re

        self.assertTrue(stored.startswith("hmac_sha256$"))
        hex_part = stored.split("$", 1)[1]
        self.assertEqual(len(hex_part), 64)
        self.assertTrue(re.fullmatch(r"[a-f0-9]{64}", hex_part))
