# users/tests/test_views.py

import io
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from threading import Barrier
from unittest.mock import patch
from django.conf import settings
from django.core.cache import cache
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, close_old_connections, connections, transaction
from django.test import TestCase, TransactionTestCase, override_settings
from django.urls import reverse
from PIL import Image
from rest_framework import status
from rest_framework.test import APIClient
from commerce_wallet.models import Wallet
from core.errors import (
    AuthenticationError,
    OTPError,
    SignUpError,
    UserValidationError,
    UserAccountError,
)
from users.models import User
from users_referrals.models import Referral
from users_sessions.models import Session


class SignupTestHelpers:
    """Shared OTP/setup assertions; not itself a test class."""

    def set_up_signup(self):
        cache.clear()
        self.addCleanup(cache.clear)
        self.client = APIClient()
        self.phone = "09123456789"
        self.verified_phone = self.phone
        self.url = reverse("users:user-signup")
        self.signup_url = self.url

    def verify_phone(self, phone=None, client=None):
        phone = phone or self.phone
        client = client if client is not None else self.client
        response = client.post(
            reverse("authentication:login-request"),
            {"phone_number": phone},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        response = client.post(
            reverse("authentication:login-verify"),
            {"phone_number": phone, "otp": "123456"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.json()["data"]["new_user"])
        self.assertIn("signup_token", response.cookies)
        return response

    def assert_denied(self, response):
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            response.json()["error_code"],
            SignUpError.SIGN_UP_NOT_ALLOWED[0],
        )
        self.assertNotIn("access_token", response.cookies)
        self.assertNotIn("refresh_token", response.cookies)

    def assert_no_account(self):
        self.assertFalse(User.objects.exists())
        self.assertFalse(Wallet.objects.exists())
        self.assertFalse(Session.objects.exists())

    def assert_proof_consumed(self, phone=None):
        phone = phone or self.phone
        self.assertIsNone(cache.get(f"signup_verified_{phone}"))

    def expire_login_cooldown(self):
        self.assertTrue(cache.touch(f"otp:login:-:{self.phone}", -1))


class UserSignupViewTest(SignupTestHelpers, TestCase):
    """Original signup coverage updated to the one-attempt proof contract."""

    def setUp(self):
        self.set_up_signup()
        self.verify_phone()
        self.valid_data = {
            "phone_number": self.phone,
            "first_name": "John",
            "last_name": "Doe",
            "gender": User.Gender.MALE,
            "date_of_birth": date(1990, 1, 1),
        }

    # Original success cases.

    def test_signup_success(self):
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(self.url, self.valid_data)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn("user", response.data)

        user = User.objects.get(phone_number=self.phone)
        self.assertEqual(user.first_name, self.valid_data["first_name"])
        self.assertEqual(user.last_name, self.valid_data["last_name"])
        self.assertEqual(user.gender, self.valid_data["gender"])
        self.assertEqual(user.date_of_birth, self.valid_data["date_of_birth"])
        self.assertIsNotNone(user.referral_code)
        self.assertTrue(user.is_active)
        self.assertEqual(Wallet.objects.filter(owner=user).count(), 1)
        self.assertFalse(Referral.objects.filter(referred_user=user).exists())

        session = Session.objects.get(user=user)
        self.assertIsNotNone(session.id)
        self.assertEqual(session.ip_address, "127.0.0.1")

        self.assertIn("access_token", response.cookies)
        self.assertIn("refresh_token", response.cookies)
        self.assertEqual(set(response.json()["data"]), {"user"})
        for name in ("access_token", "refresh_token"):
            self.assertTrue(response.cookies[name]["httponly"])
            self.assertNotIn(response.cookies[name].value, response.content.decode())
        self.assertEqual(response.cookies["signup_token"]["max-age"], 0)
        self.assertEqual(response.cookies["signup_token"]["path"], "/api/users/signup/")
        self.assert_proof_consumed()

    def test_signup_success_with_referral(self):
        referrer = User.objects.create_user(
            phone_number="09123456788",
            first_name="Referrer",
            last_name="User",
            gender=User.Gender.MALE,
        )
        data = {**self.valid_data, "referral": referrer.referral_code}
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        user = User.objects.get(phone_number=self.phone)
        referral = Referral.objects.get(referred_user=user)
        self.assertEqual(referral.referrer, referrer)
        self.assertIsNotNone(referral.referred_at)
        self.assert_proof_consumed()

    def test_signup_success_with_padded_referral(self):
        referrer = User.objects.create_user(
            phone_number="09123456788",
            first_name="Referrer",
            last_name="User",
            gender=User.Gender.MALE,
        )
        data = {**self.valid_data, "referral": f"  {referrer.referral_code}  "}

        response = self.client.post(self.url, data, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(response.json()["success"])
        user = User.objects.get(phone_number=self.phone)
        referral = Referral.objects.get()
        self.assertEqual(referral.referrer, referrer)
        self.assertEqual(referral.referred_user, user)
        self.assertEqual(Wallet.objects.filter(owner=user).count(), 1)
        self.assertEqual(Session.objects.filter(user=user).count(), 1)
        self.assertIn("access_token", response.cookies)
        self.assertIn("refresh_token", response.cookies)
        self.assert_proof_consumed()

    def test_signup_with_whitespace_only_referral(self):
        self.assert_signup_without_referral(" \t\n ")

    def test_signup_with_empty_referral(self):
        self.assert_signup_without_referral("")

    def test_signup_with_null_referral(self):
        self.assert_signup_without_referral(None)

    def assert_signup_without_referral(self, referral):
        data = {**self.valid_data, "referral": referral}

        response = self.client.post(self.url, data, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(response.json()["success"])
        user = User.objects.get(phone_number=self.phone)
        self.assertFalse(Referral.objects.exists())
        self.assertEqual(Wallet.objects.filter(owner=user).count(), 1)
        self.assertEqual(Session.objects.filter(user=user).count(), 1)
        self.assert_proof_consumed()

    # Original phone-verification cases.

    def test_signup_without_phone_verification(self):
        cache.clear()
        response = self.client.post(self.url, self.valid_data)
        self.assert_denied(response)

    def test_signup_with_expired_phone_verification(self):
        cache.expire(f"signup_verified_{self.phone}", 0)
        response = self.client.post(self.url, self.valid_data)
        self.assert_denied(response)

    def test_signup_with_wrong_phone_verification(self):
        data = {**self.valid_data, "phone_number": "09123456788"}
        response = self.client.post(self.url, data)
        self.assert_denied(response)
        self.assertIsNotNone(cache.get(f"signup_verified_{self.phone}"))

    # The original missing-fields loop must be split: a valid failed attempt
    # consumes the proof and each independent field needs a fresh test setup.

    def test_signup_missing_phone_number(self):
        data = self.valid_data.copy()
        data.pop("phone_number")
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.json()["error_code"], OTPError.PHONE_REQUIRED[0])
        # Missing phone is rejected before proof validation/consumption.
        self.assertIsNotNone(cache.get(f"signup_verified_{self.phone}"))

    def test_signup_missing_first_name(self):
        self.assert_missing_field_consumes_proof("first_name")

    def test_signup_missing_last_name(self):
        self.assert_missing_field_consumes_proof("last_name")

    def test_signup_missing_gender(self):
        self.assert_missing_field_consumes_proof("gender")

    def test_signup_missing_date_of_birth(self):
        self.assert_missing_field_consumes_proof("date_of_birth")

    def assert_missing_field_consumes_proof(self, field):
        data = self.valid_data.copy()
        data.pop(field)
        response = self.client.post(self.url, data)
        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
            f"Missing '{field}' must be rejected",
        )
        self.assert_proof_consumed()
        self.assertFalse(User.objects.filter(phone_number=self.phone).exists())

    def test_signup_rejects_non_string_phone(self):
        for phone in (9123456789, 1.5, True, [self.phone], {"phone": self.phone}):
            with self.subTest(phone=phone):
                self.assert_invalid_signup_phone(phone, UserValidationError.INVALID_PHONE_NUMBER[0])

    def test_signup_falsy_phone_preserves_required_error(self):
        for phone in (None, 0, False, [], {}):
            with self.subTest(phone=phone):
                self.assert_invalid_signup_phone(phone, OTPError.PHONE_REQUIRED[0])

    def assert_invalid_signup_phone(self, phone, error_code):
        proof_key = f"signup_verified_{self.phone}"
        original_proof = cache.get(proof_key)
        self.assertIsNotNone(original_proof)

        response = self.client.post(self.url, {**self.valid_data, "phone_number": phone}, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        body = response.json()
        self.assertFalse(body["success"])
        self.assertIsNone(body["data"])
        self.assertEqual(body["error_code"], error_code)
        for name in ("access_token", "refresh_token", "signup_token"):
            self.assertNotIn(name, response.cookies)
        self.assert_no_account()
        self.assertEqual(cache.get(proof_key), original_proof)

    def test_signup_invalid_phone(self):
        data = {**self.valid_data, "phone_number": "12345"}
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        # Phone validation happens before proof consumption.
        self.assertIsNotNone(cache.get(f"signup_verified_{self.phone}"))

    # Original duplicate and referral cases.

    def test_signup_duplicate_phone(self):
        User.objects.create_user(
            phone_number=self.phone,
            first_name="Existing",
            last_name="User",
            gender=User.Gender.MALE,
        )
        response = self.client.post(self.url, self.valid_data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["error_code"], SignUpError.PHONE_NUMBER_REUSE[0])
        self.assert_proof_consumed()
        self.assertEqual(User.objects.filter(phone_number=self.phone).count(), 1)

    def test_signup_with_invalid_referral(self):
        data = {**self.valid_data, "referral": "INVALID_CODE"}
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["error_code"], SignUpError.REFERRAL_CODE_NOT_VALID[0])
        self.assert_proof_consumed()
        self.assertFalse(User.objects.filter(phone_number=self.phone).exists())

    # Original names/Unicode cases.

    def test_signup_with_special_characters_in_name(self):
        data = {**self.valid_data, "first_name": "John-Doe", "last_name": "O'Brien"}
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        user = User.objects.get(phone_number=self.phone)
        self.assertEqual(user.first_name, "John-Doe")
        self.assertEqual(user.last_name, "O'Brien")
        self.assert_proof_consumed()

    def test_signup_with_unicode_characters(self):
        data = {**self.valid_data, "first_name": "José", "last_name": "García"}
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        user = User.objects.get(phone_number=self.phone)
        self.assertEqual(user.first_name, "José")
        self.assertEqual(user.last_name, "García")
        self.assert_proof_consumed()

    def test_signup_phone_already_verified_but_used(self):
        self.verify_phone("09123456788")
        User.objects.create_user(
            phone_number="09123456788",
            first_name="Existing",
            last_name="User",
            gender=User.Gender.MALE,
        )
        data = {**self.valid_data, "phone_number": "09123456788"}
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["error_code"], SignUpError.PHONE_NUMBER_REUSE[0])
        self.assert_proof_consumed("09123456788")

    def test_signup_self_referral_prevention(self):
        """Keep the original self-referral regression and check one-attempt cleanup."""
        original_create_user = User.objects.create_user
        created_user = None

        def mock_create_user(**kwargs):
            nonlocal created_user
            user = original_create_user(**kwargs)
            user.referral_code = "ABCDEF"
            user.save(update_fields=["referral_code"])
            created_user = user
            return user

        try:
            User.objects.create_user = mock_create_user
            data = {**self.valid_data, "referral": "ABCDEF"}
            response = self.client.post(self.url, data)
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
            self.assertEqual(response.data["error_code"], SignUpError.REFERRAL_CODE_NOT_VALID[0])
            self.assertFalse(Referral.objects.filter(referred_user=created_user).exists())
            self.assert_proof_consumed()
        finally:
            User.objects.create_user = original_create_user


class SignupVerificationTests(SignupTestHelpers, TestCase):
    """Cookie-bound verification proof, expiry, replay and failure semantics."""

    def setUp(self):
        self.set_up_signup()
        self.data = {
            "phone_number": self.phone,
            "first_name": "Alice",
            "last_name": "Example",
            "gender": User.Gender.FEMALE,
            "date_of_birth": "1990-01-01",
        }

    def test_another_clients_verification_cannot_authorize_signup(self):
        self.verify_phone()
        key = f"signup_verified_{self.phone}"
        record = cache.get(key)
        attacker = APIClient()
        response = attacker.post(self.signup_url, self.data, format="json")
        self.assert_denied(response)
        self.assertEqual(cache.get(key), record)
        self.assert_no_account()
        # An unauthorized attempt must not harm the real verified client.
        response = self.client.post(self.signup_url, self.data, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_cookie_signup_consumes_proof_and_creates_complete_account(self):
        verification = self.verify_phone()
        cookie = verification.cookies["signup_token"]
        self.assertEqual(len(cookie.value), 43)
        self.assertTrue(cookie["httponly"])
        self.assertEqual(cookie["max-age"], 600)
        self.assertEqual(cookie["path"], "/api/users/signup/")
        self.assertEqual(cookie["samesite"], settings.SESSION_COOKIE_SAMESITE)
        self.assertEqual(bool(cookie["secure"]), settings.SESSION_COOKIE_SECURE)
        self.assertEqual(verification.json()["data"], {"user": None, "new_user": True})
        self.assertNotIn(cookie.value, verification.content.decode())

        key = f"signup_verified_{self.phone}"
        record = cache.get(key)
        self.assertEqual(record["phone_number"], self.phone)
        self.assertNotIn(cookie.value, str(record))
        self.assertGreater(cache.ttl(key), 0)
        self.assertLessEqual(cache.ttl(key), 600)

        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(self.signup_url, self.data, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(response.json()["success"])
        self.assertIsNone(response.json()["error_code"])
        self.assertEqual(set(response.json()["data"]), {"user"})
        self.assertIn("access_token", response.cookies)
        self.assertIn("refresh_token", response.cookies)
        for name in ("access_token", "refresh_token"):
            self.assertTrue(response.cookies[name]["httponly"])
            self.assertNotIn(response.cookies[name].value, response.content.decode())
        self.assertEqual(response.cookies["signup_token"]["max-age"], 0)
        self.assertEqual(response.cookies["signup_token"]["path"], "/api/users/signup/")

        user = User.objects.get(phone_number=self.phone)
        self.assertEqual(user.first_name, "Alice")
        self.assertEqual(Wallet.objects.get(owner=user).balance, 0)
        self.assertEqual(Session.objects.filter(user=user).count(), 1)
        self.assert_proof_consumed()
        profile = self.client.get(reverse("users:dashboard"))
        self.assertEqual(profile.status_code, status.HTTP_200_OK)
        self.assertEqual(profile.json()["data"]["user"]["phone_number"], self.phone)

        replay = APIClient()
        replay.cookies["signup_token"] = cookie.value
        self.assert_denied(replay.post(self.signup_url, self.data, format="json"))
        self.assertEqual(User.objects.count(), 1)
        self.assertEqual(Wallet.objects.count(), 1)
        self.assertEqual(Session.objects.count(), 1)

    @override_settings(SESSION_COOKIE_SECURE=True, SESSION_COOKIE_DOMAIN=".example.com")
    def test_signup_cookie_uses_configured_security_attributes(self):
        response = self.verify_phone()
        cookie = response.cookies["signup_token"]
        self.assertTrue(cookie["secure"])
        self.assertTrue(cookie["httponly"])
        self.assertEqual(cookie["domain"], ".example.com")
        response = self.client.post(self.signup_url, self.data, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.cookies["signup_token"]["domain"], ".example.com")
        self.assertEqual(response.cookies["signup_token"]["max-age"], 0)

    def test_signup_body_token_cannot_replace_cookie(self):
        verification = self.verify_phone()
        token = verification.cookies["signup_token"].value
        record = cache.get(f"signup_verified_{self.phone}")
        response = APIClient().post(self.signup_url, {**self.data, "signup_token": token}, format="json")
        self.assert_denied(response)
        self.assert_no_account()
        self.assertEqual(cache.get(f"signup_verified_{self.phone}"), record)

    def test_wrong_or_malformed_secrets_are_rejected_without_consuming_proof(self):
        verification = self.verify_phone()
        valid_token = verification.cookies["signup_token"].value
        key = f"signup_verified_{self.phone}"
        record = cache.get(key)
        for token in ("", "short", "A" * 43, "!" * 43, "A" * 44):
            with self.subTest(token=token):
                self.client.cookies["signup_token"] = token
                response = self.client.post(self.signup_url, self.data, format="json")
                self.assert_denied(response)
                self.assert_no_account()
                self.assertEqual(cache.get(key), record)
        self.client.cookies["signup_token"] = valid_token
        response = self.client.post(self.signup_url, self.data, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assert_proof_consumed()

    def test_proof_is_bound_to_phone_number(self):
        self.verify_phone()
        key = f"signup_verified_{self.phone}"
        record = cache.get(key)
        response = self.client.post(
            self.signup_url,
            {**self.data, "phone_number": "09123456788"},
            format="json",
        )
        self.assert_denied(response)
        self.assert_no_account()
        self.assertEqual(cache.get(key), record)

    def test_normalized_phone_uses_the_same_proof(self):
        self.verify_phone()
        response = self.client.post(
            self.signup_url,
            {**self.data, "phone_number": f" {self.phone} "},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(User.objects.get().phone_number, self.phone)
        self.assert_proof_consumed()

    def test_expired_proof_is_rejected(self):
        self.verify_phone()
        key = f"signup_verified_{self.phone}"
        cache.expire(key, 0)
        self.assertIsNone(cache.get(key))
        self.assert_denied(self.client.post(self.signup_url, self.data, format="json"))
        self.assert_no_account()

    def test_new_verification_replaces_the_old_secret(self):
        first_client = APIClient()
        first = self.verify_phone(client=first_client)
        self.expire_login_cooldown()
        second = self.verify_phone()
        self.assertNotEqual(
            first.cookies["signup_token"].value,
            second.cookies["signup_token"].value,
        )
        self.assert_denied(first_client.post(self.signup_url, self.data, format="json"))
        self.assert_no_account()
        response = self.client.post(self.signup_url, self.data, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assert_proof_consumed()

    def test_legacy_or_inconsistent_cache_records_do_not_authorize_signup(self):
        self.verify_phone()
        key = f"signup_verified_{self.phone}"
        original = cache.get(key)
        for record in (
            {"phone_number": self.phone},
            {**original, "phone_number": "09123456788"},
            {**original, "proof_hash": None},
            "legacy-marker",
        ):
            with self.subTest(record=record):
                cache.set(key, record, 600)
                self.assert_denied(self.client.post(self.signup_url, self.data, format="json"))
                self.assert_no_account()
                self.assertEqual(cache.get(key), record)

    def test_validation_failure_consumes_proof_and_requires_fresh_otp(self):
        self.verify_phone()
        response = self.client.post(self.signup_url, {**self.data, "first_name": "A"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assert_no_account()
        self.assert_proof_consumed()
        self.assert_denied(self.client.post(self.signup_url, self.data, format="json"))
        self.expire_login_cooldown()
        self.verify_phone()
        response = self.client.post(self.signup_url, self.data, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assert_proof_consumed()

    def test_creation_failure_rolls_back_and_consumes_proof(self):
        self.verify_phone()
        with patch.object(Session, "create_session", side_effect=RuntimeError("creation failed")):
            with self.assertRaisesMessage(RuntimeError, "creation failed"):
                self.client.post(self.signup_url, self.data, format="json")
        self.assert_no_account()
        self.assert_proof_consumed()
        self.assert_denied(self.client.post(self.signup_url, self.data, format="json"))
        self.expire_login_cooldown()
        self.verify_phone()
        response = self.client.post(self.signup_url, self.data, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assert_proof_consumed()

    def test_outer_rollback_still_consumes_verification(self):
        self.verify_phone()
        with transaction.atomic():
            response = self.client.post(self.signup_url, self.data, format="json")
            self.assertEqual(response.status_code, status.HTTP_201_CREATED)
            self.assert_proof_consumed()  # Redis deletion is not rolled back with SQL.
            transaction.set_rollback(True)
        self.assert_no_account()
        self.assert_proof_consumed()


class SignupConcurrencyTests(SignupTestHelpers, TransactionTestCase):
    """Requires a real shared Redis cache and PostgreSQL for realistic concurrency."""

    def setUp(self):
        self.set_up_signup()
        self.data = {
            "phone_number": self.phone,
            "first_name": "Alice",
            "last_name": "Example",
            "gender": User.Gender.FEMALE,
            "date_of_birth": "1990-01-01",
        }
        verification = self.verify_phone()
        self.token = verification.cookies["signup_token"].value

    def test_proof_is_consumed_before_database_commit(self):
        key = f"signup_verified_{self.phone}"
        client = APIClient()
        client.cookies["signup_token"] = self.token
        with transaction.atomic():
            response = client.post(self.signup_url, self.data, format="json")
            self.assertEqual(response.status_code, status.HTTP_201_CREATED)
            self.assertIsNone(cache.get(key))
        self.assertIsNone(cache.get(key))
        self.assertEqual(User.objects.filter(phone_number=self.phone).count(), 1)
        self.assertEqual(Wallet.objects.count(), 1)
        self.assertEqual(Session.objects.count(), 1)

    def test_concurrent_signups_create_exactly_one_complete_account(self):
        barrier = Barrier(2)

        def signup():
            close_old_connections()
            try:
                client = APIClient()
                client.cookies["signup_token"] = self.token
                barrier.wait(timeout=10)
                response = client.post(self.signup_url, self.data, format="json")
                return response.status_code, response.json()
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: signup(), range(2)))

        self.assertEqual(sorted(code for code, _ in results), [201, 400])
        denied = next(payload for code, payload in results if code == 400)
        self.assertEqual(denied["error_code"], SignUpError.SIGN_UP_NOT_ALLOWED[0])
        user = User.objects.get(phone_number=self.phone)
        self.assertEqual(Wallet.objects.filter(owner=user).count(), 1)
        self.assertEqual(Session.objects.filter(user=user).count(), 1)
        self.assert_proof_consumed()

    def test_lock_contention_rejects_signup_without_consuming_proof(self):
        client = APIClient()
        client.cookies["signup_token"] = self.token
        lock = cache.lock(f"signup_verification_lock_{self.phone}", timeout=10)
        self.assertTrue(lock.acquire(blocking=False))
        try:
            response = client.post(self.signup_url, self.data, format="json")
            self.assert_denied(response)
            self.assert_no_account()
            self.assertIsNotNone(cache.get(f"signup_verified_{self.phone}"))
        finally:
            lock.release()
        response = client.post(self.signup_url, self.data, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assert_proof_consumed()


class PhoneChangeFlowTest(TestCase):
    """Test phone change flow (4 steps)"""

    def setUp(self):
        self.client = APIClient()
        cache.clear()

        self.user = User.objects.create_user(
            phone_number="09123456789",
            first_name="John",
            last_name="Doe",
            gender=User.Gender.MALE,
        )
        self.client.force_authenticate(user=self.user)

        self.old_request_url = reverse("users:phone-change-old-request")
        self.old_verify_url = reverse("users:phone-change-old-verify")
        self.new_request_url = reverse("users:phone-change-new-request")
        self.new_verify_url = reverse("users:phone-change-new-verify")

    def tearDown(self):
        cache.clear()

    def verify_old_phone(self):
        response = self.client.post(self.old_request_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        response = self.client.post(self.old_verify_url, {"otp": "123456"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def request_new_phone(self, phone):
        self.verify_old_phone()
        response = self.client.post(self.new_request_url, {"phone_number": phone}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def assert_confirmation_conflict(self, response, owner):
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        body = response.json()
        self.assertFalse(body["success"])
        self.assertIsNone(body["data"])
        self.assertEqual(body["error_code"], SignUpError.PHONE_NUMBER_REUSE[0])
        self.user.refresh_from_db()
        self.assertEqual(self.user.phone_number, "09123456789")
        self.assertEqual(User.objects.get(phone_number="09123456711"), owner)
        self.assertIsNone(cache.get(f"phone_change_step_{self.user.id}"))

    # ========== SUCCESS FLOW ==========
    def test_repeat_new_phone_request_preserves_state(self):
        phone = "09123456711"
        self.request_new_phone(phone)
        state_key = f"phone_change_step_{self.user.id}"
        original_state = cache.get(state_key)
        cache.touch(state_key, 60)

        response = self.client.post(self.new_request_url, {"phone_number": f" {phone} "})
        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.json()["error_code"], OTPError.OTP_ALREADY_ACTIVE[0])
        self.assertGreater(int(response["Retry-After"]), 0)
        self.assertEqual(cache.get(state_key), original_state)
        self.assertLessEqual(cache.ttl(state_key), 60)

        response = self.client.post(self.new_request_url, {"phone_number": "09123456712"})
        self.assertEqual(response.json()["error_code"], OTPError.OLD_PHONE_VERIFICATION_REQUIRED[0])
        self.assertEqual(cache.get(state_key), original_state)

        otp_key = f"otp:new_phone:{self.user.pk}:{phone}"
        cache.touch(otp_key, -1)
        response = self.client.post(self.new_request_url, {"phone_number": phone})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(cache.get(state_key), original_state)
        self.assertLessEqual(cache.ttl(state_key), 60)
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(self.new_verify_url, {"otp": "123456"})
        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertEqual(self.user.phone_number, phone)

    def test_complete_phone_change_flow(self):
        """Test complete phone change flow with all steps"""
        new_phone = "09123456711"

        response = self.client.post(self.old_request_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        cache_key = f"otp:old_phone:{self.user.pk}:{self.user.phone_number}"
        self.assertIsNotNone(cache.get(cache_key))

        state_key = f"phone_change_step_{self.user.id}"
        state = cache.get(state_key)
        self.assertIsNotNone(state)
        self.assertEqual(state["step"], "old_otp_sent")
        self.assertEqual(state["user_id"], self.user.id)

        response = self.client.post(self.old_verify_url, {"otp": "123456"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsNone(cache.get(cache_key)[1])

        state = cache.get(state_key)
        self.assertIsNotNone(state)
        self.assertEqual(state["step"], "old_verified")

        response = self.client.post(self.new_request_url, {"phone_number": new_phone})
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        new_cache_key = f"otp:new_phone:{self.user.pk}:{new_phone}"
        self.assertIsNotNone(cache.get(new_cache_key))

        state = cache.get(state_key)
        self.assertIsNotNone(state)
        self.assertEqual(state["step"], "new_otp_sent")
        self.assertEqual(state["new_phone"], new_phone)

        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(self.new_verify_url, {"otp": "123456"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("user", response.data)
        self.assertEqual(response.data["user"]["phone_number"], new_phone)

        self.user.refresh_from_db()
        self.assertEqual(self.user.phone_number, new_phone)

        self.assertIsNone(cache.get(state_key))
        self.assertIsNone(cache.get(new_cache_key)[1])

    def test_new_phone_request_caches_normalized_phone(self):
        self.request_new_phone(" 09123456711 ")

        state = cache.get(f"phone_change_step_{self.user.id}")
        self.assertEqual(state["new_phone"], "09123456711")
        self.assertIsNotNone(cache.get(f"otp:new_phone:{self.user.pk}:09123456711"))
        self.assertIsNone(cache.get(f"otp:new_phone:{self.user.pk}: 09123456711 "))
        self.user.refresh_from_db()
        self.assertEqual(self.user.phone_number, "09123456789")

    def test_padded_current_phone_is_rejected(self):
        self.verify_old_phone()
        state_key = f"phone_change_step_{self.user.id}"
        original_state = cache.get(state_key)

        response = self.client.post(
            self.new_request_url,
            {"phone_number": f" {self.user.phone_number} "},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.json()["error_code"], UserAccountError.SAME_PHONE_AS_CURRENT[0])
        self.assertEqual(cache.get(state_key), original_state)
        self.assertIsNone(cache.get(f"otp:new_phone:{self.user.pk}: {self.user.phone_number} "))

    def test_padded_phone_change_completes(self):
        self.request_new_phone(" 09123456711 ")
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(self.new_verify_url, {"otp": "123456"})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()["data"]["user"]["phone_number"], "09123456711")
        self.user.refresh_from_db()
        self.assertEqual(self.user.phone_number, "09123456711")
        self.assertIsNone(cache.get(f"phone_change_step_{self.user.id}"))
        self.assertIsNone(cache.get(f"otp:new_phone:{self.user.pk}:09123456711")[1])

    def test_phone_change_state_is_cleared_after_commit(self):
        self.request_new_phone("09123456711")
        state_key = f"phone_change_step_{self.user.id}"
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(self.new_verify_url, {"otp": "123456"})
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertIsNotNone(cache.get(state_key))
        self.assertIsNone(cache.get(state_key))

    def test_phone_change_rollback_preserves_pending_state(self):
        self.request_new_phone("09123456711")
        state_key = f"phone_change_step_{self.user.id}"
        original_state = cache.get(state_key)
        with self.captureOnCommitCallbacks(execute=True):
            with transaction.atomic():
                response = self.client.post(self.new_verify_url, {"otp": "123456"})
                self.assertEqual(response.status_code, status.HTTP_200_OK)
                transaction.set_rollback(True)
        self.user.refresh_from_db()
        self.assertEqual(self.user.phone_number, "09123456789")
        self.assertEqual(cache.get(state_key), original_state)
        # Redis OTP consumption is not rolled back with the database.
        replay = self.client.post(self.new_verify_url, {"otp": "123456"})
        self.assertEqual(replay.json()["error_code"], OTPError.OTP_NOT_FOUND[0])
        self.assertTrue(cache.touch(f"otp:new_phone:{self.user.pk}:09123456711", -1))
        self.assertEqual(self.client.post(self.new_request_url, {"phone_number": "09123456711"}).status_code, 200)
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(self.new_verify_url, {"otp": "123456"})
        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertEqual(self.user.phone_number, "09123456711")

    def test_new_phone_claimed_before_confirmation(self):
        self.request_new_phone("09123456711")
        owner = User.objects.create_user(
            phone_number="09123456711",
            first_name="Other",
            last_name="User",
            gender=User.Gender.MALE,
        )
        other_state_key = f"phone_change_step_{owner.id}"
        other_state = {"step": "old_verified", "user_id": owner.id}
        cache.set(other_state_key, other_state, 300)
        original_otp = cache.get(f"otp:new_phone:{self.user.pk}:09123456711")

        response = self.client.post(self.new_verify_url, {"otp": "123456"})

        self.assert_confirmation_conflict(response, owner)
        self.assertEqual(cache.get(f"otp:new_phone:{self.user.pk}:09123456711"), original_otp)
        self.assertEqual(cache.get(other_state_key), other_state)

    def test_unrelated_confirmation_integrity_error_is_not_masked(self):
        self.request_new_phone("09123456711")
        state_key = f"phone_change_step_{self.user.id}"
        with patch.object(User, "save", side_effect=IntegrityError("unrelated failure")):
            with self.assertRaisesMessage(IntegrityError, "unrelated failure"):
                self.client.post(self.new_verify_url, {"otp": "123456"})
        self.user.refresh_from_db()
        self.assertEqual(self.user.phone_number, "09123456789")
        self.assertIsNotNone(cache.get(state_key))

    def test_new_phone_request_rejects_invalid_input(self):
        self.verify_old_phone()
        state_key = f"phone_change_step_{self.user.id}"
        original_state = cache.get(state_key)
        for phone in (
            9123456789,
            True,
            ["09123456711"],
            {"phone": "09123456711"},
            "invalid",
        ):
            with self.subTest(phone=phone):
                response = self.client.post(self.new_request_url, {"phone_number": phone}, format="json")
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertEqual(
                    response.json()["error_code"],
                    UserValidationError.INVALID_PHONE_NUMBER[0],
                )
                self.assertEqual(cache.get(state_key), original_state)
        self.user.refresh_from_db()
        self.assertEqual(self.user.phone_number, "09123456789")
        self.assertIsNone(cache.get(f"otp:new_phone:{self.user.pk}:09123456711"))

    def test_new_otp_verify_missing_target(self):
        cache.set(
            f"phone_change_step_{self.user.id}",
            {"step": "new_otp_sent", "user_id": self.user.id},
            300,
        )
        response = self.client.post(self.new_verify_url, {"otp": "123456"})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.json()["error_code"], OTPError.NEW_PHONE_NOT_FOUND[0])
        self.user.refresh_from_db()
        self.assertEqual(self.user.phone_number, "09123456789")

    def test_phone_change_flow_old_otp_expiry(self):
        """Test OTP expiry during phone change flow"""
        response = self.client.post(self.old_request_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        state_key = f"phone_change_step_{self.user.id}"
        cache.set(state_key, {"step": "old_otp_sent", "user_id": self.user.id}, -1)

        response = self.client.post(self.old_verify_url, {"otp": "123456"})
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(response.data["error_code"], OTPError.OTP_NOT_FOUND[0])

    # ========== ERROR CASES - OLD PHONE ==========
    def test_old_otp_verify_without_state(self):
        """Test verifying old OTP without any state"""
        response = self.client.post(self.old_verify_url, {"otp": "123456"})
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(response.data["error_code"], OTPError.OTP_NOT_FOUND[0])

    def test_old_otp_verify_invalid_otp(self):
        """Test verifying old OTP with invalid code"""
        response = self.client.post(self.old_request_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        response = self.client.post(self.old_verify_url, {"otp": "999999"})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["error_code"], OTPError.OTP_INVALID[0])

        state = cache.get(f"phone_change_step_{self.user.id}")
        self.assertEqual(state["step"], "old_otp_sent")

    def test_old_otp_verify_wrong_step(self):
        """Test verifying old OTP at wrong step"""
        state_key = f"phone_change_step_{self.user.id}"
        cache.set(state_key, {"step": "old_verified", "user_id": self.user.id})

        response = self.client.post(self.old_verify_url, {"otp": "123456"})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["error_code"], OTPError.INVALID_STEP[0])

    def test_old_otp_request_missing_otp(self):
        """Test old OTP verification without OTP code"""
        response = self.client.post(self.old_request_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        response = self.client.post(self.old_verify_url, {})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["error_code"], OTPError.PHONE_REQUIRED[0])

    # ========== ERROR CASES - NEW PHONE ==========
    def test_new_otp_request_without_old_verification(self):
        """Test requesting new phone OTP without old verification"""
        response = self.client.post(self.new_request_url, {"phone_number": "09123456788"})
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(response.data["error_code"], OTPError.OTP_NOT_FOUND[0])

    def test_new_otp_request_missing_phone(self):
        """Test new phone OTP request without phone number"""
        self.verify_old_phone()

        response = self.client.post(self.new_request_url, {})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["error_code"], OTPError.PHONE_REQUIRED[0])

    def test_new_otp_request_duplicate_phone(self):
        """Test changing to a phone that already exists"""
        User.objects.create_user(
            phone_number="09123456788",
            first_name="Existing",
            last_name="User",
            gender=User.Gender.MALE,
        )

        self.verify_old_phone()

        response = self.client.post(self.new_request_url, {"phone_number": "09123456788"})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["error_code"], SignUpError.PHONE_NUMBER_REUSE[0])

    def test_new_otp_request_same_phone(self):
        """Test changing to the same phone number"""
        self.verify_old_phone()

        response = self.client.post(self.new_request_url, {"phone_number": self.user.phone_number})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["error_code"], UserAccountError.SAME_PHONE_AS_CURRENT[0])

    def test_new_otp_verify_without_state(self):
        """Test verifying new phone OTP without state"""
        response = self.client.post(self.new_verify_url, {"otp": "123456"})
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_new_otp_verify_invalid_otp(self):
        """Test verifying new phone OTP with invalid code"""
        self.request_new_phone("09123456788")

        response = self.client.post(self.new_verify_url, {"otp": "999999"})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["error_code"], OTPError.OTP_INVALID[0])

    def test_new_otp_verify_wrong_step(self):
        """Test verifying new OTP at wrong step"""
        state_key = f"phone_change_step_{self.user.id}"
        cache.set(state_key, {"step": "old_verified", "user_id": self.user.id})

        response = self.client.post(self.new_verify_url, {"otp": "123456"})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["error_code"], OTPError.INVALID_STEP[0])

    def test_new_otp_verify_missing_otp(self):
        """Test new OTP verification without OTP code"""
        self.request_new_phone("09123456788")

        response = self.client.post(self.new_verify_url, {})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["error_code"], OTPError.PHONE_REQUIRED[0])

    def test_new_otp_verify_expired_state(self):
        """Test verifying new phone with expired state"""
        self.request_new_phone("09123456788")

        state_key = f"phone_change_step_{self.user.id}"
        cache.set(state_key, {"step": "new_otp_sent", "user_id": self.user.id}, -1)

        response = self.client.post(self.new_verify_url, {"otp": "123456"})
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    # ========== AUTHENTICATION TESTS ==========
    def test_phone_change_unauthenticated(self):
        """Test phone change endpoints without authentication"""
        client = APIClient()

        response = client.post(self.old_request_url)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["error_code"], AuthenticationError.TOKEN_NOT_PROVIDE[0])

    def test_phone_change_inactive_user(self):
        """Test phone change for inactive user"""
        self.user.is_active = False
        self.user.save()

        response = self.client.post(self.old_request_url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class UserProfileViewTest(TestCase):
    """Test user profile view"""

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            phone_number="09123456789",
            first_name="John",
            last_name="Doe",
            gender=User.Gender.MALE,
            date_of_birth=date(1990, 1, 1),
        )
        self.url = reverse("users:dashboard")
        self.update_url = reverse("users:profile-update")
        self.client.force_authenticate(user=self.user)

    def _upload_profile_picture(self, user=None):
        user = user or self.user
        client = APIClient()
        client.force_authenticate(user=user)
        image_bytes = io.BytesIO()
        Image.new("RGB", (16, 16), color="red").save(image_bytes, format="PNG")
        image_file = SimpleUploadedFile("profile.png", image_bytes.getvalue(), content_type="image/png")
        response = client.put(self.update_url, {"profile_picture": image_file}, format="multipart")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        user.refresh_from_db()
        return user.profile_picture.name

    # ========== GET TESTS ==========

    def test_profile_routes_keep_head_and_options(self):
        response = self.client.head(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.content, b"")
        for url in [self.url, self.update_url]:
            with self.subTest(url=url):
                response = self.client.options(url)
                self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_profile_update_rendered_response(self):
        response = self.client.put(self.update_url, {"first_name": "Jane"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        payload = response.json()
        self.assertTrue(payload["success"])
        self.assertIsNone(payload["error_code"])
        self.assertEqual(payload["data"]["user"]["first_name"], "Jane")
        self.assertEqual(payload["data"]["user"]["last_name"], "Doe")

    def test_profile_update_inactive_user(self):
        self.user.is_active = False
        self.user.save()
        response = self.client.put(self.update_url, {"first_name": "Changed"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, "John")

    def test_get_profile_success(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("user", response.data)
        user_data = response.data["user"]
        self.assertEqual(user_data["phone_number"], "09123456789")
        self.assertEqual(user_data["first_name"], "John")
        self.assertEqual(user_data["last_name"], "Doe")
        self.assertEqual(user_data["gender"], User.Gender.MALE)
        self.assertEqual(user_data["date_of_birth"], "1990-01-01")
        self.assertIn("referral_code", user_data)

    def test_get_profile_unauthenticated(self):
        client = APIClient()
        response = client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["error_code"], AuthenticationError.TOKEN_NOT_PROVIDE[0])

    def test_get_profile_inactive_user(self):
        self.user.is_active = False
        self.user.save()
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    # ========== UPDATE (PUT) TESTS ==========
    def test_update_profile_success(self):
        data = {
            "first_name": "Jane",
            "last_name": "Smith",
            "gender": User.Gender.FEMALE,
            "date_of_birth": date(1995, 5, 5),
        }
        response = self.client.put(self.update_url, data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        user_data = response.data["user"]
        self.assertEqual(user_data["first_name"], "Jane")
        self.assertEqual(user_data["last_name"], "Smith")
        self.assertEqual(user_data["gender"], User.Gender.FEMALE)
        self.assertEqual(user_data["date_of_birth"], "1995-05-05")
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, "Jane")
        self.assertEqual(self.user.last_name, "Smith")
        self.assertEqual(self.user.gender, User.Gender.FEMALE)
        self.assertEqual(self.user.date_of_birth, date(1995, 5, 5))

    def test_update_profile_partial(self):
        data = {"first_name": "Jane"}
        response = self.client.put(self.update_url, data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, "Jane")
        self.assertEqual(self.user.last_name, "Doe")
        self.assertEqual(self.user.gender, User.Gender.MALE)

    def test_update_profile_multiple_fields(self):
        data = {
            "first_name": "Jane",
            "last_name": "Smith",
        }
        response = self.client.put(self.update_url, data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, "Jane")
        self.assertEqual(self.user.last_name, "Smith")

    def test_update_profile_phone_number_read_only(self):
        data = {"phone_number": "09999999999"}
        response = self.client.put(self.update_url, data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertEqual(self.user.phone_number, "09123456789")

    # ========== VALIDATION (single representative) ==========
    def test_update_profile_invalid_first_name(self):
        data = {"first_name": "Jo"}
        response = self.client.put(self.update_url, data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["error_code"], UserValidationError.INVALID_NAME[0])

    # ========== AUTHENTICATION TESTS ==========
    def test_update_profile_unauthenticated(self):
        client = APIClient()
        data = {"first_name": "Jane"}
        response = client.put(self.update_url, data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["error_code"], AuthenticationError.TOKEN_NOT_PROVIDE[0])

    def test_update_profile_picture_with_invalid_file_type(self):
        """Test updating profile picture with invalid file type"""
        from django.core.files.uploadedfile import SimpleUploadedFile

        # Create a dummy text file (not an image)
        invalid_file = SimpleUploadedFile("profile.txt", b"This is a text file", content_type="text/plain")

        data = {
            "profile_picture": invalid_file,
        }

        response = self.client.put(self.update_url, data, format="multipart")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        # The error is wrapped in a VALIDATION_ERROR response
        self.assertEqual(response.data["error_code"], "VALIDATION_ERROR")

    # ========== DATE OF BIRTH NULL HANDLING ==========
    def test_update_profile_date_of_birth_to_null(self):
        """Test explicitly setting date_of_birth to null"""
        data = {"date_of_birth": None}

        response = self.client.put(self.update_url, data, format="json")

        # Your API wraps validation errors
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["error_code"], "VALIDATION_ERROR")

    def test_update_profile_date_of_birth_to_empty_string(self):
        """Test sending empty string for date_of_birth"""
        data = {"date_of_birth": ""}

        response = self.client.put(self.update_url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["error_code"], "VALIDATION_ERROR")

    # ========== PROFILE PICTURE UPDATE ==========
    def test_reset_profile_picture_to_default(self):
        previous_name = self._upload_profile_picture()
        storage = self.user.profile_picture.storage

        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.put(self.update_url, {"profile_picture": None}, format="json")
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.user.refresh_from_db()
            self.assertEqual(
                self.user.profile_picture.name,
                "profile_pics/default_profile_image.png",
            )
            self.assertTrue(storage.exists(previous_name))

        self.assertFalse(storage.exists(previous_name))
        payload = response.json()
        self.assertTrue(payload["success"])
        self.assertIsNone(payload["error_code"])
        self.assertEqual(
            payload["data"]["user"]["profile_picture"],
            "http://testserver/media/profile_pics/default_profile_image.png",
        )

    def test_omitted_profile_picture_preserves_upload(self):
        previous_name = self._upload_profile_picture()
        storage = self.user.profile_picture.storage

        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.put(self.update_url, {"first_name": "Jane"}, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, "Jane")
        self.assertEqual(self.user.profile_picture.name, previous_name)
        self.assertTrue(storage.exists(previous_name))

    def test_repeated_picture_resets_preserve_shared_default(self):
        previous_name = self._upload_profile_picture()
        storage = self.user.profile_picture.storage
        default_name = "profile_pics/default_profile_image.png"
        if not storage.exists(default_name):
            storage.save(default_name, ContentFile(b"shared default image"))
            self.addCleanup(storage.delete, default_name)

        for attempt in range(2):
            with self.subTest(attempt=attempt):
                with self.captureOnCommitCallbacks(execute=True):
                    response = self.client.put(self.update_url, {"profile_picture": None}, format="json")

                self.assertEqual(response.status_code, status.HTTP_200_OK)
                self.user.refresh_from_db()
                self.assertEqual(self.user.profile_picture.name, default_name)
                self.assertTrue(storage.exists(default_name))
                self.assertFalse(storage.exists(previous_name))

    def test_invalid_picture_reset_preserves_upload(self):
        previous_name = self._upload_profile_picture()
        storage = self.user.profile_picture.storage

        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.put(
                self.update_url,
                {"profile_picture": None, "first_name": "Jo"},
                format="json",
            )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, "John")
        self.assertEqual(self.user.profile_picture.name, previous_name)
        self.assertTrue(storage.exists(previous_name))

    def test_picture_reset_only_changes_authenticated_user(self):
        previous_name = self._upload_profile_picture()
        storage = self.user.profile_picture.storage
        other_user = User.objects.create_user(
            phone_number="09123456788",
            first_name="Other",
            last_name="User",
            gender=User.Gender.FEMALE,
        )
        other_picture_name = self._upload_profile_picture(other_user)

        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.put(
                self.update_url,
                {"profile_picture": None, "id": str(other_user.id)},
                format="json",
            )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertEqual(self.user.profile_picture.name, "profile_pics/default_profile_image.png")
        self.assertFalse(storage.exists(previous_name))
        other_user.refresh_from_db()
        self.assertEqual(other_user.profile_picture.name, other_picture_name)
        self.assertTrue(storage.exists(other_picture_name))

    def test_picture_reset_requires_active_authenticated_user(self):
        previous_name = self._upload_profile_picture()
        storage = self.user.profile_picture.storage
        self.user.is_active = False
        self.user.save(update_fields=["is_active"])

        for client, expected_status in (
            (APIClient(), status.HTTP_400_BAD_REQUEST),
            (self.client, status.HTTP_404_NOT_FOUND),
        ):
            with self.subTest(expected_status=expected_status):
                with self.captureOnCommitCallbacks(execute=True):
                    response = client.put(self.update_url, {"profile_picture": None}, format="json")

                self.assertEqual(response.status_code, expected_status)
                self.user.refresh_from_db()
                self.assertEqual(self.user.profile_picture.name, previous_name)
                self.assertTrue(storage.exists(previous_name))

    def test_picture_cleanup_failure_does_not_fail_reset(self):
        previous_name = self._upload_profile_picture()
        storage = self.user.profile_picture.storage

        with patch.object(storage, "delete", side_effect=OSError("storage unavailable")):
            with self.assertLogs("django.test", level="ERROR") as logs:
                with self.captureOnCommitCallbacks(execute=True):
                    response = self.client.put(self.update_url, {"profile_picture": None}, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.json()["success"])
        self.user.refresh_from_db()
        self.assertEqual(self.user.profile_picture.name, "profile_pics/default_profile_image.png")
        self.assertTrue(storage.exists(previous_name))
        self.assertIn("storage unavailable", "\n".join(logs.output))

    def test_picture_cleanup_preserves_subsequent_upload(self):
        previous_name = self._upload_profile_picture()
        storage = self.user.profile_picture.storage

        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.put(self.update_url, {"profile_picture": None}, format="json")
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            new_name = self._upload_profile_picture()
            self.assertTrue(storage.exists(previous_name))

        self.user.refresh_from_db()
        self.assertEqual(self.user.profile_picture.name, new_name)
        self.assertTrue(storage.exists(new_name))
        self.assertFalse(storage.exists(previous_name))

    def test_update_profile_picture(self):
        # Create a valid image file
        image = Image.new("RGB", (100, 100), color="red")
        image_bytes = io.BytesIO()
        image.save(image_bytes, format="JPEG")
        image_bytes.seek(0)

        image_file = SimpleUploadedFile("profile.jpg", image_bytes.read(), content_type="image/jpeg")

        data = {
            "profile_picture": image_file,
        }

        response = self.client.put(self.update_url, data, format="multipart")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Verify the profile picture was updated
        self.user.refresh_from_db()
        self.assertIsNotNone(self.user.profile_picture)
        # Should be saved as WebP
        self.assertTrue(self.user.profile_picture.name.endswith(".webp"))

        # Verify it's a valid WebP image
        img = Image.open(self.user.profile_picture)
        self.assertEqual(img.format, "WEBP")

    def test_update_profile_picture_with_png(self):

        # Create a PNG image
        image = Image.new("RGB", (100, 100), color="blue")
        image_bytes = io.BytesIO()
        image.save(image_bytes, format="PNG")
        image_bytes.seek(0)

        image_file = SimpleUploadedFile("profile.png", image_bytes.read(), content_type="image/png")

        data = {
            "profile_picture": image_file,
        }

        response = self.client.put(self.update_url, data, format="multipart")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Verify the profile picture was converted to WebP
        self.user.refresh_from_db()
        self.assertIsNotNone(self.user.profile_picture)
        self.assertTrue(self.user.profile_picture.name.endswith(".webp"))

        img = Image.open(self.user.profile_picture)
        self.assertEqual(img.format, "WEBP")

    def test_update_profile_picture_with_webp(self):

        # Create a WEBP image
        image = Image.new("RGB", (100, 100), color="green")
        image_bytes = io.BytesIO()
        image.save(image_bytes, format="WEBP")
        image_bytes.seek(0)

        image_file = SimpleUploadedFile("profile.webp", image_bytes.read(), content_type="image/webp")

        data = {
            "profile_picture": image_file,
        }

        response = self.client.put(self.update_url, data, format="multipart")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # WebP should remain WebP
        self.user.refresh_from_db()
        self.assertIsNotNone(self.user.profile_picture)
        self.assertTrue(self.user.profile_picture.name.endswith(".webp"))

        img = Image.open(self.user.profile_picture)
        self.assertEqual(img.format, "WEBP")
