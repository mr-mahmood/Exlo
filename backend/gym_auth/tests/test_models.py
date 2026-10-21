# gym_auth/tests/test_models.py

import uuid

from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone
from django.db.models.deletion import ProtectedError

from gym.models import Gym
from gym_auth.models import UserGymRole
from users.models import User


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
                UserGymRole.objects.create_owner(
                    user=self.user,
                    gym=self.gym,
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
