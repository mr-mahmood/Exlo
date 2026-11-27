# authentication/tests/test_otp.py
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from time import monotonic, sleep
from unittest.mock import patch
from uuid import uuid4

from django.test import SimpleTestCase, override_settings
from django.core.cache import cache
from kombu.exceptions import EncodeError, OperationalError
from redis.client import Pipeline
from redis.exceptions import ConnectionError

from authentication.otp_service import OTPPurpose, delete_if_unchanged, generate_otp, verify_otp
from core.errors import APIError, OTPError


class OTPServiceTest(SimpleTestCase):
    """Test OTP service"""

    def setUp(self):
        cache.clear()

    def test_generate_otp_success(self):
        """Test generating OTP"""
        result = generate_otp(phone_number="09123456789", purpose=OTPPurpose.LOGIN)

        self.assertIsNone(result)

        # Check cache
        cache_key = "otp:login:-:09123456789"
        self.assertIsNotNone(cache.get(cache_key))

    def test_verify_otp_success(self):
        """Test verifying correct OTP"""
        generate_otp(phone_number="09123456789", purpose=OTPPurpose.LOGIN)

        result = verify_otp(phone_number="09123456789", otp_code="123456", purpose=OTPPurpose.LOGIN)

        self.assertIsNone(result)

        with self.assertRaises(APIError) as replay:
            verify_otp(phone_number="09123456789", otp_code="123456", purpose=OTPPurpose.LOGIN)
        self.assertEqual(replay.exception.error_code, "OTP-002")
        with self.assertRaises(APIError) as duplicate:
            generate_otp(phone_number="09123456789", purpose=OTPPurpose.LOGIN)
        self.assertEqual(duplicate.exception.error_code, "OTP-009")

    def test_verify_otp_wrong_code(self):
        """Test verifying wrong OTP"""
        generate_otp(phone_number="09123456789", purpose=OTPPurpose.LOGIN)

        with self.assertRaises(APIError):
            verify_otp(phone_number="09123456789", otp_code="999999", purpose=OTPPurpose.LOGIN)

    def test_verify_otp_expired(self):
        """Test verifying expired OTP"""
        # Don't generate OTP
        with self.assertRaises(APIError):
            verify_otp(phone_number="09123456789", otp_code="123456", purpose=OTPPurpose.LOGIN)

    def test_otp_hash_security(self):
        generate_otp(phone_number="09123456789", purpose=OTPPurpose.LOGIN)
        cache_key = "otp:login:-:09123456789"
        _, stored, failed_attempts = cache.get(cache_key)
        self.assertEqual(failed_attempts, 0)

        # Should not be plain text
        self.assertNotEqual(stored, "123456")
        self.assertNotEqual(stored, "")

        # Should be scheme-tagged: "hmac_sha256$<64 hex chars>"
        import re

        self.assertTrue(stored.startswith("hmac_sha256$"))
        hex_part = stored.split("$", 1)[1]
        self.assertEqual(len(hex_part), 64)
        self.assertTrue(re.fullmatch(r"[a-f0-9]{64}", hex_part))

    def test_redis_connection_failure_returns_service_unavailable(self):
        key = "otp:login:-:09123456789"
        scope = {"phone_number": "09123456789", "purpose": OTPPurpose.LOGIN}
        with patch.object(cache.client, "get_client_with_index", side_effect=ConnectionError):
            with self.assertRaises(APIError) as issuance:
                generate_otp(**scope)
        with patch.object(cache.client, "get_client", side_effect=ConnectionError):
            with self.assertRaises(APIError) as verification:
                verify_otp(otp_code="123456", **scope)
            self.assertFalse(delete_if_unchanged(key, ("id", "hash", 0)))
        for unavailable in (issuance, verification):
            self.assertEqual(unavailable.exception.status_code, 503)
            self.assertEqual(unavailable.exception.error_code, "OTP-011")
        self.assertIsNone(cache.get(key))

    def test_duplicate_preserves_expiry_code_and_attempts(self):
        phone = "09123456789"
        key = f"otp:login:-:{phone}"
        generate_otp(phone_number=phone, purpose=OTPPurpose.LOGIN)
        cache.touch(key, 20)
        with self.assertRaises(APIError) as wrong:
            verify_otp(phone_number=phone, otp_code="999999", purpose=OTPPurpose.LOGIN)
        self.assertEqual(wrong.exception.error_code, OTPError.OTP_INVALID[0])
        original_challenge = cache.get(key)

        with self.assertRaises(APIError) as duplicate:
            generate_otp(phone_number=phone, purpose=OTPPurpose.LOGIN)
        self.assertEqual(duplicate.exception.error_code, OTPError.OTP_ALREADY_ACTIVE[0])
        self.assertIn(duplicate.exception.retry_after, range(1, 21))
        self.assertLessEqual(cache.ttl(key), 20)
        self.assertEqual(cache.get(key), original_challenge)
        self.assertEqual(original_challenge[2], 1)

        for _ in range(3):
            with self.assertRaises(APIError) as wrong:
                verify_otp(phone_number=phone, otp_code="999999", purpose=OTPPurpose.LOGIN)
            self.assertEqual(wrong.exception.error_code, OTPError.OTP_INVALID[0])
        self.assertIsNone(verify_otp(phone_number=phone, otp_code="123456", purpose=OTPPurpose.LOGIN))

    @override_settings(OTP_EXPIRY_SECONDS=1, OTP_MAX_ATTEMPTS=1)
    def test_locked_challenge_expires_and_can_be_reissued(self):
        phone = "09123456789"
        key = f"otp:login:-:{phone}"
        generate_otp(phone_number=phone, purpose=OTPPurpose.LOGIN)
        with self.assertRaises(APIError) as locked:
            verify_otp(phone_number=phone, otp_code="999999", purpose=OTPPurpose.LOGIN)
        self.assertEqual(locked.exception.error_code, OTPError.OTP_ATTEMPTS_EXHAUSTED[0])
        self.assertEqual(locked.exception.retry_after, 1)

        deadline = monotonic() + 3
        while cache.get(key) is not None and monotonic() < deadline:
            sleep(0.025)
        with self.assertRaises(APIError) as expired:
            verify_otp(phone_number=phone, otp_code="123456", purpose=OTPPurpose.LOGIN)
        self.assertEqual(expired.exception.error_code, OTPError.OTP_NOT_FOUND[0])
        generate_otp(phone_number=phone, purpose=OTPPurpose.LOGIN)
        self.assertIsNone(verify_otp(phone_number=phone, otp_code="123456", purpose=OTPPurpose.LOGIN))

    def test_purpose_and_user_scope(self):
        phone = "09123456789"
        owner, other = uuid4(), uuid4()
        scopes = [
            {"purpose": OTPPurpose.LOGIN},
            {"purpose": OTPPurpose.OLD_PHONE, "user_id": owner},
            {"purpose": OTPPurpose.NEW_PHONE, "user_id": owner},
            {"purpose": OTPPurpose.NEW_PHONE, "user_id": other},
        ]
        for scope in scopes:
            with self.assertRaises(APIError) as missing:
                verify_otp(phone_number=phone, otp_code="123456", **scope)
            self.assertEqual(missing.exception.error_code, OTPError.OTP_NOT_FOUND[0])
            self.assertIsNone(generate_otp(phone_number=phone, **scope))

        for scope in scopes:
            self.assertIsNone(verify_otp(phone_number=phone, otp_code="123456", **scope))

    def concurrent_results(self, count, operation):
        start = Barrier(count, timeout=5)

        def run():
            start.wait()
            try:
                return operation()
            except APIError as exc:
                return exc.error_code, exc.retry_after

        with ThreadPoolExecutor(max_workers=count) as executor:
            return list(executor.map(lambda _: run(), range(count)))

    def test_only_one_concurrent_request_issues_challenge(self):
        results = self.concurrent_results(4, lambda: generate_otp(phone_number="09123456789", purpose=OTPPurpose.LOGIN))
        self.assertEqual(results.count(None), 1)
        for code, retry_after in (result for result in results if result is not None):
            self.assertEqual(code, OTPError.OTP_ALREADY_ACTIVE[0])
            self.assertIn(retry_after, range(1, 121))

    def test_only_one_concurrent_verification_succeeds(self):
        phone = "09123456789"
        generate_otp(phone_number=phone, purpose=OTPPurpose.LOGIN)
        results = self.concurrent_results(
            4, lambda: verify_otp(phone_number=phone, otp_code="123456", purpose=OTPPurpose.LOGIN)
        )
        self.assertCountEqual(results, [None] + [(OTPError.OTP_NOT_FOUND[0], None)] * 3)

    def test_concurrent_wrong_entries_count_toward_lockout(self):
        phone = "09123456789"
        generate_otp(phone_number=phone, purpose=OTPPurpose.LOGIN)
        results = self.concurrent_results(
            6, lambda: verify_otp(phone_number=phone, otp_code="999999", purpose=OTPPurpose.LOGIN)
        )
        self.assertEqual(results.count((OTPError.OTP_INVALID[0], None)), 4)
        for code, retry_after in (result for result in results if result != (OTPError.OTP_INVALID[0], None)):
            self.assertEqual(code, OTPError.OTP_ATTEMPTS_EXHAUSTED[0])
            self.assertIn(retry_after, range(1, 121))
        with self.assertRaises(APIError) as locked:
            verify_otp(phone_number=phone, otp_code="123456", purpose=OTPPurpose.LOGIN)
        self.assertEqual(locked.exception.error_code, OTPError.OTP_ATTEMPTS_EXHAUSTED[0])
        self.assertIn(locked.exception.retry_after, range(1, 121))

    def test_conflict_leaves_replacement_challenge_untouched(self):
        scope = {"phone_number": "09123456789", "purpose": OTPPurpose.LOGIN}
        key = "otp:login:-:09123456789"
        generate_otp(**scope)
        original_exec = Pipeline._execute_transaction

        def replace_before_exec(pipe, *args, **kwargs):
            cache.delete(key)
            generate_otp(**scope)
            return original_exec(pipe, *args, **kwargs)

        with patch.object(Pipeline, "_execute_transaction", autospec=True, side_effect=replace_before_exec) as execute:
            with self.assertRaises(APIError) as stale:
                verify_otp(otp_code="123456", **scope)
            execute.assert_called_once()
        self.assertEqual(stale.exception.error_code, "OTP-002")
        self.assertIsNone(verify_otp(otp_code="123456", **scope))

    def test_lost_exec_reply_does_not_retry_committed_write(self):
        scope = {"phone_number": "09123456789", "purpose": OTPPurpose.LOGIN}
        generate_otp(**scope)
        original_parse = Pipeline.parse_response
        lost_replies = 0

        def lose_exec_reply(pipe, *args, **kwargs):
            nonlocal lost_replies
            response = original_parse(pipe, *args, **kwargs)
            if isinstance(response, list):
                lost_replies += 1
                raise ConnectionError("private transport details")
            return response

        with patch.object(Pipeline, "parse_response", lose_exec_reply):
            with self.assertRaises(APIError) as unavailable:
                verify_otp(otp_code="999999", **scope)
        self.assertEqual(unavailable.exception.error_code, "OTP-011")
        self.assertEqual(lost_replies, 1)
        self.assertEqual(cache.get("otp:login:-:09123456789")[2], 1)

    @override_settings(IS_PRODUCTION=True)
    def test_sms_publication_failure_preserves_only_uncertain_delivery(self):
        scope = {"phone_number": "09123456789", "purpose": OTPPurpose.LOGIN}
        key = "otp:login:-:09123456789"
        for failure, should_keep in ((EncodeError, False), (OperationalError, True)):
            with self.subTest(failure=failure):
                with patch("core.sms_task.send_sms_verification_task.delay", side_effect=failure("private payload")):
                    with self.assertRaises(APIError) as unavailable:
                        generate_otp(**scope)
                self.assertEqual(unavailable.exception.error_code, "OTP-011")
                self.assertEqual(cache.get(key) is not None, should_keep)
