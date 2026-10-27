# users_nfc_cards/tests/test_models.py

from unittest.mock import patch
from django.core.cache import cache
from django.db import IntegrityError, transaction
from django.test import TestCase
from core.errors import APIError, UserNfcCardError
from users.models import User
from users_nfc_cards.models import UserNfcCard, UserNfcCardManager


class UserNfcCardTestBase(TestCase):
    def setUp(self):
        cache.clear()

        self.user = User.objects.create_user(
            phone_number="09120000001",
            password="testpassword123",
            first_name="A",
            last_name="B",
        )
        self.other_user = User.objects.create_user(
            phone_number="09120000002",
            password="testpassword123",
            first_name="C",
            last_name="D",
        )

    def tearDown(self):
        cache.clear()


class FindCardTests(UserNfcCardTestBase):
    def test_returns_card_when_uid_exists(self):
        card = UserNfcCard.objects.create(
            user=self.user,
            uid="04A32B",
        )

        result = UserNfcCard.objects.find_card("04A32B")

        self.assertEqual(result.pk, card.pk)
        self.assertEqual(result.uid, "04A32B")

    def test_strips_whitespace_from_uid(self):
        card = UserNfcCard.objects.create(
            user=self.user,
            uid="04A32B",
        )

        result = UserNfcCard.objects.find_card("  04A32B  ")

        self.assertEqual(result.pk, card.pk)

    def test_raises_invalid_uid_for_empty_uid(self):
        with self.assertRaises(APIError) as ctx:
            UserNfcCard.objects.find_card("")

        self.assertEqual(
            ctx.exception.error_code,
            UserNfcCardError.INVALID_UID[0],
        )

    def test_raises_invalid_uid_for_whitespace_only_uid(self):
        with self.assertRaises(APIError) as ctx:
            UserNfcCard.objects.find_card("   ")

        self.assertEqual(
            ctx.exception.error_code,
            UserNfcCardError.INVALID_UID[0],
        )

    def test_raises_card_not_found_when_uid_missing(self):
        with self.assertRaises(APIError) as ctx:
            UserNfcCard.objects.find_card("NOPE")

        self.assertEqual(
            ctx.exception.error_code,
            UserNfcCardError.CARD_NOT_FOUND[0],
        )


class AssignCardTests(UserNfcCardTestBase):
    def test_creates_card_for_user_without_existing_card(self):
        card = UserNfcCard.objects.assign_card(
            user=self.user,
            uid="04A32B",
        )

        self.assertEqual(card.user.id, self.user.id)
        self.assertEqual(card.uid, "04A32B")

    def test_strips_whitespace_from_uid(self):
        card = UserNfcCard.objects.assign_card(
            user=self.user,
            uid="  04A32B  ",
        )

        self.assertEqual(card.uid, "04A32B")

    def test_raises_invalid_uid_for_empty_uid(self):
        with self.assertRaises(APIError) as ctx:
            UserNfcCard.objects.assign_card(
                user=self.user,
                uid="",
            )

        self.assertEqual(
            ctx.exception.error_code,
            UserNfcCardError.INVALID_UID[0],
        )

    def test_raises_invalid_uid_for_whitespace_only_uid(self):
        with self.assertRaises(APIError) as ctx:
            UserNfcCard.objects.assign_card(
                user=self.user,
                uid="   ",
            )

        self.assertEqual(
            ctx.exception.error_code,
            UserNfcCardError.INVALID_UID[0],
        )

    def test_replaces_existing_card_for_same_user(self):
        first = UserNfcCard.objects.assign_card(
            user=self.user,
            uid="OLD123",
        )

        second = UserNfcCard.objects.assign_card(
            user=self.user,
            uid="NEW456",
        )

        self.assertNotEqual(first.pk, second.pk)
        self.assertFalse(UserNfcCard.objects.filter(pk=first.pk).exists())
        self.assertEqual(
            UserNfcCard.objects.filter(user=self.user).count(),
            1,
        )
        self.assertEqual(second.uid, "NEW456")

    def test_raises_when_uid_claimed_by_different_user(self):
        UserNfcCard.objects.assign_card(
            user=self.other_user,
            uid="CLAIMED",
        )

        with self.assertRaises(APIError) as ctx:
            UserNfcCard.objects.assign_card(
                user=self.user,
                uid="CLAIMED",
            )

        self.assertEqual(
            ctx.exception.error_code,
            UserNfcCardError.CARD_ALREADY_ASSIGNED[0],
        )

        self.assertTrue(
            UserNfcCard.objects.filter(
                user=self.other_user,
                uid="CLAIMED",
            ).exists()
        )

    def test_reassigning_same_uid_to_same_user_is_allowed(self):
        first = UserNfcCard.objects.assign_card(
            user=self.user,
            uid="SAME123",
        )

        second = UserNfcCard.objects.assign_card(
            user=self.user,
            uid="SAME123",
        )

        self.assertNotEqual(first.pk, second.pk)
        self.assertEqual(second.uid, "SAME123")
        self.assertEqual(
            UserNfcCard.objects.filter(user=self.user).count(),
            1,
        )

    def test_integrity_error_is_converted_to_card_already_assigned(self):
        with patch.object(
            UserNfcCardManager,
            "create",
            side_effect=IntegrityError,
        ):
            with self.assertRaises(APIError) as ctx:
                UserNfcCard.objects.assign_card(
                    user=self.user,
                    uid="RACED",
                )

        self.assertEqual(
            ctx.exception.error_code,
            UserNfcCardError.CARD_ALREADY_ASSIGNED[0],
        )

    def test_card_unique_constraint_on_uid(self):
        UserNfcCard.objects.create(
            user=self.user,
            uid="UNIQ1",
        )

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                UserNfcCard.objects.create(
                    user=self.other_user,
                    uid="UNIQ1",
                )

    def test_user_one_to_one_constraint(self):
        UserNfcCard.objects.create(
            user=self.user,
            uid="U1",
        )

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                UserNfcCard.objects.create(
                    user=self.user,
                    uid="U2",
                )

    def test_card_is_deleted_when_user_is_deleted(self):
        card = UserNfcCard.objects.create(
            user=self.user,
            uid="DELETE1",
        )

        self.user.delete()

        self.assertFalse(UserNfcCard.objects.filter(pk=card.pk).exists())


class FindOrAssignCardTests(UserNfcCardTestBase):
    def test_returns_existing_card_without_assignment(self):
        card = UserNfcCard.objects.create(
            user=self.user,
            uid="EXISTING",
        )

        result, assigned = UserNfcCard.objects.find_or_assign_card(
            uid="EXISTING",
            gym_id="gym-1",
        )

        self.assertEqual(result.pk, card.pk)
        self.assertFalse(assigned)

    def test_assigns_unassigned_uid_to_pending_user(self):
        cache.set(
            "nfc_card_assign_gym-1",
            self.user.pk,
            timeout=300,
        )

        card, assigned = UserNfcCard.objects.find_or_assign_card(
            uid="NEW123",
            gym_id="gym-1",
        )

        self.assertTrue(assigned)
        self.assertEqual(card.user.id, self.user.pk)
        self.assertEqual(card.uid, "NEW123")

    def test_deletes_pending_assignment_after_success(self):
        key = "nfc_card_assign_gym-1"

        cache.set(
            key,
            self.user.pk,
            timeout=300,
        )

        UserNfcCard.objects.find_or_assign_card(
            uid="NEW123",
            gym_id="gym-1",
        )

        self.assertIsNone(cache.get(key))

    def test_raises_card_not_found_without_pending_assignment(self):
        with self.assertRaises(APIError) as ctx:
            UserNfcCard.objects.find_or_assign_card(
                uid="UNKNOWN",
                gym_id="gym-1",
            )

        self.assertEqual(
            ctx.exception.error_code,
            UserNfcCardError.CARD_NOT_FOUND[0],
        )

    def test_existing_uid_takes_precedence_over_pending_assignment(self):
        existing = UserNfcCard.objects.create(
            user=self.other_user,
            uid="EXISTING",
        )

        cache.set(
            "nfc_card_assign_gym-1",
            self.user.pk,
            timeout=300,
        )

        result, assigned = UserNfcCard.objects.find_or_assign_card(
            uid="EXISTING",
            gym_id="gym-1",
        )

        self.assertEqual(result.pk, existing.pk)
        self.assertFalse(assigned)

        self.assertEqual(
            existing.user_id,
            self.other_user.pk,
        )

    def test_pending_assignment_is_not_consumed_when_uid_is_already_assigned(self):
        key = "nfc_card_assign_gym-1"

        UserNfcCard.objects.create(
            user=self.other_user,
            uid="EXISTING",
        )

        cache.set(
            key,
            self.user.pk,
            timeout=300,
        )

        UserNfcCard.objects.find_or_assign_card(
            uid="EXISTING",
            gym_id="gym-1",
        )

        self.assertEqual(
            cache.get(key),
            self.user.pk,
        )

    def test_assigning_replaces_pending_users_existing_card(self):
        UserNfcCard.objects.create(
            user=self.user,
            uid="OLD123",
        )

        cache.set(
            "nfc_card_assign_gym-1",
            self.user.pk,
            timeout=300,
        )

        card, assigned = UserNfcCard.objects.find_or_assign_card(
            uid="NEW123",
            gym_id="gym-1",
        )

        self.assertTrue(assigned)
        self.assertEqual(card.uid, "NEW123")
        self.assertFalse(UserNfcCard.objects.filter(uid="OLD123").exists())
        self.assertEqual(
            UserNfcCard.objects.filter(user=self.user).count(),
            1,
        )

    def test_raises_invalid_uid_for_empty_uid(self):
        with self.assertRaises(APIError) as ctx:
            UserNfcCard.objects.find_or_assign_card(
                uid="",
                gym_id="gym-1",
            )

        self.assertEqual(
            ctx.exception.error_code,
            UserNfcCardError.INVALID_UID[0],
        )

    def test_raises_invalid_uid_for_whitespace_only_uid(self):
        with self.assertRaises(APIError) as ctx:
            UserNfcCard.objects.find_or_assign_card(
                uid="   ",
                gym_id="gym-1",
            )

        self.assertEqual(
            ctx.exception.error_code,
            UserNfcCardError.INVALID_UID[0],
        )

    def test_raises_invalid_uid_for_Not_string_uid(self):
        with self.assertRaises(APIError) as ctx:
            UserNfcCard.objects.find_or_assign_card(
                uid=1523,
                gym_id="gym-1",
            )

        self.assertEqual(
            ctx.exception.error_code,
            UserNfcCardError.INVALID_UID[0],
        )
