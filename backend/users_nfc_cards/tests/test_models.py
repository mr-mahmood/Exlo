# users_nfc_cards/tests/test_models.py

from django.db import IntegrityError, transaction
from django.test import TestCase
from core.errors import APIError, UserNfcCardError
from users.models import User
from users_nfc_cards.models import UserNfcCard
from django.conf import settings


class UserNfcCardTestBase(TestCase):
    def setUp(self):
        settings.DEBUG = True
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
        self.staff = User.objects.create_user(
            phone_number="09120000003",
            password="testpassword123",
            first_name="E",
            last_name="F",
        )


class FindCardTests(UserNfcCardTestBase):
    def test_returns_card_when_uid_exists(self):
        card = UserNfcCard.objects.create(user=self.user, uid="04A32B")

        result = UserNfcCard.objects.find_card("04A32B")

        self.assertEqual(result.pk, card.pk)
        self.assertEqual(result.uid, "04A32B")

    def test_raises_card_not_found_when_uid_missing(self):
        with self.assertRaises(APIError) as ctx:
            UserNfcCard.objects.find_card("NOPE")

        self.assertEqual(
            ctx.exception.error_code,
            UserNfcCardError.CARD_NOT_FOUND[0],
        )


class AssignCardTests(UserNfcCardTestBase):
    def test_creates_card_for_user_without_existing_card(self):
        card: UserNfcCard = UserNfcCard.objects.assign_card(
            user=self.user,
            uid="04A32B",
            assigned_by=self.staff,
        )

        self.assertEqual(card.user.id, self.user.id)
        self.assertEqual(card.uid, "04A32B")
        self.assertEqual(card.assigned_by.id, self.staff.id)

    def test_strips_whitespace_from_uid(self):
        card = UserNfcCard.objects.assign_card(
            user=self.user,
            uid="  04A32B  ",
        )

        self.assertEqual(card.uid, "04A32B")

    def test_raises_card_not_found_for_empty_uid(self):
        with self.assertRaises(APIError) as ctx:
            UserNfcCard.objects.assign_card(user=self.user, uid="")

        self.assertEqual(
            ctx.exception.error_code,
            UserNfcCardError.CARD_NOT_FOUND[0],
        )

    def test_raises_card_not_found_for_whitespace_only_uid(self):
        with self.assertRaises(APIError) as ctx:
            UserNfcCard.objects.assign_card(user=self.user, uid="   ")

        self.assertEqual(
            ctx.exception.error_code,
            UserNfcCardError.CARD_NOT_FOUND[0],
        )

    def test_replaces_existing_card_for_same_user(self):
        first = UserNfcCard.objects.assign_card(user=self.user, uid="OLD123")
        second = UserNfcCard.objects.assign_card(user=self.user, uid="NEW456")

        self.assertNotEqual(first.pk, second.pk)
        self.assertFalse(UserNfcCard.objects.filter(pk=first.pk).exists())
        self.assertEqual(UserNfcCard.objects.filter(user=self.user).count(), 1)
        self.assertEqual(second.uid, "NEW456")

    def test_raises_when_uid_claimed_by_different_user(self):
        UserNfcCard.objects.assign_card(user=self.other_user, uid="CLAIMED")

        with self.assertRaises(APIError) as ctx:
            UserNfcCard.objects.assign_card(user=self.user, uid="CLAIMED")

        self.assertEqual(
            ctx.exception.error_code,
            UserNfcCardError.CARD_ALREADY_ASSIGNED[0],
        )
        # The other user's card is untouched.
        self.assertTrue(
            UserNfcCard.objects.filter(user=self.other_user, uid="CLAIMED").exists()
        )

    def test_reassigning_same_uid_to_same_user_is_allowed(self):
        # The pre-check uses .exclude(user=user), so re-assigning a user's
        # own UID passes the pre-check and works.
        first = UserNfcCard.objects.assign_card(user=self.user, uid="SAME123")
        second = UserNfcCard.objects.assign_card(user=self.user, uid="SAME123")

        self.assertNotEqual(first.pk, second.pk)
        self.assertEqual(second.uid, "SAME123")
        self.assertEqual(UserNfcCard.objects.filter(user=self.user).count(), 1)

    def test_raises_when_uid_claimed_by_different_user_via_integrity_error(self):
        """
        Simulate the race: the pre-check passes (no existing row visible),
        then another transaction inserts the same UID. The unique constraint
        fires and the manager converts it to CARD_ALREADY_ASSIGNED.
        """
        UserNfcCard.objects.create(user=self.other_user, uid="RACED")

        # Force the pre-check to miss by monkeypatching exists to return False,
        # simulating what happens when two requests race past the check.
        from users_nfc_cards.models import UserNfcCardManager

        original_exists = UserNfcCardManager.exists

        def fake_exists(self):
            return False

        UserNfcCardManager.exists = fake_exists
        try:
            with self.assertRaises(APIError) as ctx:
                UserNfcCard.objects.assign_card(user=self.user, uid="RACED")
            self.assertEqual(
                ctx.exception.error_code,
                UserNfcCardError.CARD_ALREADY_ASSIGNED[0],
            )
        finally:
            UserNfcCardManager.exists = original_exists

    def test_card_unique_constraint_on_uid(self):
        UserNfcCard.objects.create(user=self.user, uid="UNIQ1")

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                UserNfcCard.objects.create(user=self.other_user, uid="UNIQ1")

    def test_user_one_to_one_constraint(self):
        UserNfcCard.objects.create(user=self.user, uid="U1")

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                UserNfcCard.objects.create(user=self.user, uid="U2")

    def test_protect_on_user_deletion(self):
        UserNfcCard.objects.create(user=self.user, uid="PROTECT1")

        with self.assertRaises(Exception):  # ProtectedError
            self.user.delete()
