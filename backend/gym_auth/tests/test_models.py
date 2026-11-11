# gym_auth/tests/test_models.py

import uuid

from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone
from django.db.models.deletion import ProtectedError

from gym.models import Gym
from gym_auth.models import UserGymRole
from users.models import User
from core.errors import APIError


class UserGymRoleModelTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            phone_number="09120000000",
            first_name="Test",
            last_name="User",
        )

        self.gym = Gym.objects.create(
            name="Test Gym",
            province="Tehran",
            city="Tehran",
            address="Test Address",
        )

    def test_create_owner(self):
        role = UserGymRole.objects.create_owner(
            user=self.user,
            gym=self.gym,
        )

        saved_role = UserGymRole.objects.get(
            user=self.user,
            gym=self.gym,
            role=UserGymRole.Role.OWNER,
        )

        self.assertEqual(role, saved_role)
        self.assertEqual(saved_role.user, self.user)
        self.assertEqual(saved_role.gym, self.gym)
        self.assertEqual(saved_role.role, UserGymRole.Role.OWNER)

    def test_create_coach(self):
        UserGymRole.objects.create_coach(
            user=self.user,
            gym=self.gym,
        )

        self.assertTrue(
            UserGymRole.objects.filter(
                user=self.user,
                gym=self.gym,
                role=UserGymRole.Role.COACH,
            ).exists()
        )

    def test_database_rejects_second_owner(self):
        UserGymRole.objects.create_owner(user=self.user, gym=self.gym)
        other = User.objects.create_user(phone_number="09120000001")
        with self.assertRaises(IntegrityError), transaction.atomic():
            UserGymRole.objects.create(user=other, gym=self.gym, role="OWNER")

    def test_database_rejects_promoting_staff_to_second_owner(self):
        UserGymRole.objects.create_owner(user=self.user, gym=self.gym)
        other = User.objects.create_user(phone_number="09120000001")
        staff = UserGymRole.objects.create_staff(user=other, gym=self.gym)
        with self.assertRaises(IntegrityError), transaction.atomic():
            UserGymRole.objects.filter(pk=staff.pk).update(role="OWNER")

    def test_multiple_coaches_and_staff_remain_allowed(self):
        other = User.objects.create_user(phone_number="09120000001")
        for create_role in (UserGymRole.objects.create_coach, UserGymRole.objects.create_staff):
            first = create_role(user=self.user, gym=self.gym)
            second = create_role(user=other, gym=self.gym)
            self.assertNotEqual(first.pk, second.pk)

    def test_create_staff(self):
        UserGymRole.objects.create_staff(
            user=self.user,
            gym=self.gym,
        )

        self.assertTrue(
            UserGymRole.objects.filter(
                user=self.user,
                gym=self.gym,
                role=UserGymRole.Role.STAFF,
            ).exists()
        )

    def test_default_role_is_staff(self):
        role = UserGymRole.objects.create(
            user=self.user,
            gym=self.gym,
        )

        self.assertEqual(role.role, UserGymRole.Role.STAFF)

    def test_id_is_uuid(self):
        role = UserGymRole.objects.create_owner(
            user=self.user,
            gym=self.gym,
        )

        self.assertIsInstance(role.id, uuid.UUID)

    def test_created_at_is_populated(self):
        role = UserGymRole.objects.create_owner(
            user=self.user,
            gym=self.gym,
        )

        self.assertIsNotNone(role.created_at)
        self.assertLessEqual(role.created_at, timezone.now())

    def test_same_user_can_have_different_roles_in_same_gym(self):
        owner = UserGymRole.objects.create_owner(
            user=self.user,
            gym=self.gym,
        )
        coach = UserGymRole.objects.create_coach(
            user=self.user,
            gym=self.gym,
        )
        staff = UserGymRole.objects.create_staff(
            user=self.user,
            gym=self.gym,
        )

        self.assertEqual(
            UserGymRole.objects.filter(
                user=self.user,
                gym=self.gym,
            ).count(),
            3,
        )

        self.assertEqual(owner.role, UserGymRole.Role.OWNER)
        self.assertEqual(coach.role, UserGymRole.Role.COACH)
        self.assertEqual(staff.role, UserGymRole.Role.STAFF)

    def test_duplicate_same_role_is_rejected(self):
        UserGymRole.objects.create_owner(
            user=self.user,
            gym=self.gym,
        )

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                # Raw inserts must still be protected by the database constraint.
                UserGymRole.objects.create(
                    user=self.user,
                    gym=self.gym,
                    role=UserGymRole.Role.OWNER,
                )

    def test_same_role_is_allowed_for_different_gyms(self):
        second_gym = Gym.objects.create(
            name="Second Gym",
            province="Tehran",
            city="Tehran",
            address="Second Address",
        )

        first_role = UserGymRole.objects.create_owner(
            user=self.user,
            gym=self.gym,
        )
        second_role = UserGymRole.objects.create_owner(
            user=self.user,
            gym=second_gym,
        )

        self.assertNotEqual(first_role.gym, second_role.gym)
        self.assertEqual(
            UserGymRole.objects.filter(
                user=self.user,
                role=UserGymRole.Role.OWNER,
            ).count(),
            2,
        )

    def test_creation_helpers_report_duplicate_roles(self):
        for create_role in (
            UserGymRole.objects.create_owner,
            UserGymRole.objects.create_coach,
            UserGymRole.objects.create_staff,
        ):
            with self.subTest(helper=create_role.__name__):
                original = create_role(user=self.user, gym=self.gym)
                with self.assertRaises(APIError) as raised:
                    with transaction.atomic():
                        create_role(user=self.user, gym=self.gym)

                self.assertEqual(raised.exception.error_code, "ROLE_002")
                self.assertEqual(raised.exception.status_code, 400)
                self.assertEqual(
                    UserGymRole.objects.get(
                        user=self.user, gym=self.gym, role=original.role
                    ).pk,
                    original.pk,
                )

    def test_creation_helpers_preserve_unrelated_integrity_errors(self):
        for create_role in (
            UserGymRole.objects.create_owner,
            UserGymRole.objects.create_coach,
            UserGymRole.objects.create_staff,
        ):
            with self.subTest(helper=create_role.__name__):
                with self.assertRaises(IntegrityError):
                    with transaction.atomic():
                        create_role(user=None, gym=self.gym)
        self.assertFalse(UserGymRole.objects.exists())

    def test_user_deletion_is_protected(self):
        UserGymRole.objects.create_owner(
            user=self.user,
            gym=self.gym,
        )

        with self.assertRaises(ProtectedError):
            self.user.delete()

    def test_gym_deletion_is_protected(self):
        UserGymRole.objects.create_owner(
            user=self.user,
            gym=self.gym,
        )

        with self.assertRaises(ProtectedError):
            self.gym.delete()
