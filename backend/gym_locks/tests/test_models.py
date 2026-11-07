# gym_locks/tests/test_models.py

from django.db import IntegrityError, transaction
from django.test import TestCase

from core.errors import APIError, GymLockerError
from gym.models import Gym
from gym_locks.models import GymLocker
from users.models import User


class GymLockerModelTest(TestCase):
    """Tests for GymLocker model methods and manager."""

    def setUp(self):
        self.gym = Gym.objects.create(
            name="Test Gym",
            province="Test Province",
            city="Test City",
            address="123 Test St",
            is_active=True,
        )

        self.other_gym = Gym.objects.create(
            name="Other Gym",
            province="Other Province",
            city="Other City",
            address="456 Other St",
            is_active=True,
        )

        self.user = User.objects.create_user(
            phone_number="09121234567",
            first_name="Test",
            last_name="User",
        )

        self.other_user = User.objects.create_user(
            phone_number="09129876543",
            first_name="Other",
            last_name="User",
        )

        self.locker: GymLocker = GymLocker.objects.create(
            gym=self.gym,
            number=1,
        )

    # ==================== ACTIVATE / DEACTIVATE ====================

    def test_activate_inactive_locker(self):
        self.locker.is_active = False
        self.locker.save(update_fields=["is_active"])

        self.locker.activate()

        self.assertTrue(self.locker.is_active)

        self.locker.refresh_from_db()
        self.assertTrue(self.locker.is_active)

    def test_activate_already_active_locker(self):
        self.assertTrue(self.locker.is_active)

        self.locker.activate()

        self.assertTrue(self.locker.is_active)

    def test_deactivate_active_locker(self):
        self.locker.deactivate()

        self.assertFalse(self.locker.is_active)

        self.locker.refresh_from_db()
        self.assertFalse(self.locker.is_active)

    def test_deactivate_already_inactive_locker(self):
        self.locker.deactivate()

        self.assertFalse(self.locker.is_active)

        self.locker.deactivate()

        self.locker.refresh_from_db()
        self.assertFalse(self.locker.is_active)

    # ==================== ADD LOCKERS ====================

    def test_add_lockers_creates_requested_count(self):
        lockers = GymLocker.objects.add_lockers(
            gym=self.gym,
            count=5,
        )

        self.assertEqual(len(lockers), 5)
        self.assertEqual(
            GymLocker.objects.filter(gym=self.gym).count(),
            6,  # One existing locker + five new lockers.
        )

    def test_add_lockers_assigns_sequential_numbers(self):
        lockers = GymLocker.objects.add_lockers(
            gym=self.gym,
            count=3,
        )

        self.assertEqual(
            sorted(locker.number for locker in lockers),
            [2, 3, 4],
        )

    def test_add_lockers_continues_after_highest_number(self):
        GymLocker.objects.create(
            gym=self.gym,
            number=10,
        )

        lockers = GymLocker.objects.add_lockers(
            gym=self.gym,
            count=2,
        )

        self.assertEqual(
            sorted(locker.number for locker in lockers),
            [11, 12],
        )

    def test_add_lockers_numbers_are_independent_per_gym(self):
        GymLocker.objects.create(
            gym=self.other_gym,
            number=20,
        )

        lockers = GymLocker.objects.add_lockers(
            gym=self.gym,
            count=2,
        )

        self.assertEqual(
            sorted(locker.number for locker in lockers),
            [2, 3],
        )

    def test_add_lockers_rejects_invalid_counts(self):
        invalid_counts = [
            0,
            -1,
            1.5,
            "3",
            None,
            True,
            False,
        ]

        for count in invalid_counts:
            with self.subTest(count=count):
                with self.assertRaises(APIError):
                    GymLocker.objects.add_lockers(
                        gym=self.gym,
                        count=count,
                    )

        self.assertEqual(
            GymLocker.objects.filter(gym=self.gym).count(),
            1,
        )

    # ==================== ASSIGN ====================

    def test_assign_available_locker(self):
        locker = GymLocker.objects.assign(
            gym=self.gym,
            user=self.user,
        )

        self.assertEqual(locker, self.locker)
        self.assertEqual(locker.assigned_user, self.user)

        locker.refresh_from_db()
        self.assertEqual(locker.assigned_user, self.user)

    def test_assign_skips_inactive_locker(self):
        self.locker.deactivate()

        available_locker = GymLocker.objects.create(
            gym=self.gym,
            number=2,
        )

        assigned_locker = GymLocker.objects.assign(
            gym=self.gym,
            user=self.user,
        )

        self.assertEqual(assigned_locker, available_locker)

    def test_assign_skips_already_assigned_locker(self):
        self.locker.assigned_user = self.other_user
        self.locker.save(update_fields=["assigned_user"])

        available_locker = GymLocker.objects.create(
            gym=self.gym,
            number=2,
        )

        assigned_locker = GymLocker.objects.assign(
            gym=self.gym,
            user=self.user,
        )

        self.assertEqual(assigned_locker, available_locker)

    def test_assign_rejects_user_already_assigned_in_same_gym(self):
        GymLocker.objects.assign(
            gym=self.gym,
            user=self.user,
        )

        with self.assertRaises(APIError) as context:
            GymLocker.objects.assign(
                gym=self.gym,
                user=self.user,
            )

        self.assertEqual(
            context.exception.args[0],
            GymLockerError.USER_ALREADY_ASSIGNED,
        )

    def test_assign_rejects_when_no_locker_is_available(self):
        self.locker.deactivate()

        with self.assertRaises(APIError) as context:
            GymLocker.objects.assign(
                gym=self.gym,
                user=self.user,
            )

        self.assertEqual(
            context.exception.args[0],
            GymLockerError.NO_AVAILABLE_LOCKER,
        )

    def test_assign_allows_same_user_in_another_gym(self):
        GymLocker.objects.assign(
            gym=self.gym,
            user=self.user,
        )

        GymLocker.objects.create(
            gym=self.other_gym,
            number=1,
        )

        locker = GymLocker.objects.assign(
            gym=self.other_gym,
            user=self.user,
        )

        self.assertEqual(locker.gym, self.other_gym)
        self.assertEqual(locker.assigned_user, self.user)

    # ==================== REMOVE ASSIGNMENT ====================

    def test_remove_assignment(self):
        assigned_locker = GymLocker.objects.assign(
            gym=self.gym,
            user=self.user,
        )

        removed_locker = GymLocker.objects.remove_assignment(
            gym=self.gym,
            user=self.user,
        )

        self.assertEqual(removed_locker, assigned_locker)
        self.assertIsNone(removed_locker.assigned_user)

        removed_locker.refresh_from_db()
        self.assertIsNone(removed_locker.assigned_user)

    def test_remove_assignment_rejects_unassigned_user(self):
        with self.assertRaises(APIError) as context:
            GymLocker.objects.remove_assignment(
                gym=self.gym,
                user=self.user,
            )

        self.assertEqual(
            context.exception.args[0],
            GymLockerError.USER_NOT_ASSIGNED,
        )

    def test_remove_assignment_does_not_remove_other_gyms_assignment(self):
        GymLocker.objects.create(
            gym=self.other_gym,
            number=1,
        )

        GymLocker.objects.assign(
            gym=self.other_gym,
            user=self.user,
        )

        with self.assertRaises(APIError) as context:
            GymLocker.objects.remove_assignment(
                gym=self.gym,
                user=self.user,
            )

        self.assertEqual(
            context.exception.args[0],
            GymLockerError.USER_NOT_ASSIGNED,
        )

        self.assertTrue(
            GymLocker.objects.filter(
                gym=self.other_gym,
                assigned_user=self.user,
            ).exists()
        )

    # ==================== GET LOCKERS ====================

    def test_get_gym_lockers_returns_only_requested_gym(self):
        other_locker = GymLocker.objects.create(
            gym=self.other_gym,
            number=1,
        )

        lockers = GymLocker.objects.get_gym_lockers(self.gym.id)

        self.assertQuerySetEqual(
            lockers.order_by("number"),
            [self.locker],
        )
        self.assertNotIn(other_locker, lockers)

    def test_get_lock_returns_locker_for_correct_gym(self):
        locker = GymLocker.objects.get_lock(
            gym=self.gym,
            locker_id=self.locker.id,
        )

        self.assertEqual(locker, self.locker)

    def test_get_lock_rejects_locker_from_another_gym(self):
        other_locker = GymLocker.objects.create(
            gym=self.other_gym,
            number=1,
        )

        with self.assertRaises(APIError) as context:
            GymLocker.objects.get_lock(
                gym=self.gym,
                locker_id=other_locker.id,
            )

        self.assertEqual(
            context.exception.args[0],
            GymLockerError.LOCKER_NOT_FOUND,
        )

    def test_get_user_locker_rejects_assignment_without_open_visit(self):
        GymLocker.objects.assign(
            gym=self.gym,
            user=self.user,
        )

        with self.assertRaises(APIError) as context:
            GymLocker.objects.get_user_locker(gym=self.gym, user=self.user)
        self.assertEqual(context.exception.args[0], GymLockerError.USER_NOT_ASSIGNED)

    def test_get_user_locker_rejects_unassigned_user(self):
        with self.assertRaises(APIError) as context:
            GymLocker.objects.get_user_locker(
                gym=self.gym,
                user=self.user,
            )

        self.assertEqual(
            context.exception.args[0],
            GymLockerError.USER_NOT_ASSIGNED,
        )

    def test_get_user_locker_rejects_inactive_locker(self):
        self.locker.assigned_user = self.user
        self.locker.save(update_fields=["assigned_user"])
        self.locker.deactivate()

        with self.assertRaises(APIError) as context:
            GymLocker.objects.get_user_locker(
                gym=self.gym,
                user=self.user,
            )

        self.assertEqual(
            context.exception.args[0],
            GymLockerError.USER_NOT_ASSIGNED,
        )

    # ==================== DATABASE CONSTRAINTS ====================

    def test_locker_number_must_be_unique_per_gym(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                GymLocker.objects.create(
                    gym=self.gym,
                    number=self.locker.number,
                )

    def test_locker_number_can_repeat_in_another_gym(self):
        locker = GymLocker.objects.create(
            gym=self.other_gym,
            number=self.locker.number,
        )

        self.assertEqual(locker.number, self.locker.number)

    def test_user_cannot_have_two_assigned_lockers_in_same_gym(self):
        self.locker.assigned_user = self.user
        self.locker.save(update_fields=["assigned_user"])

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                GymLocker.objects.create(
                    gym=self.gym,
                    number=2,
                    assigned_user=self.user,
                )

    def test_user_can_have_multiple_unassigned_lockers(self):
        locker: GymLocker = GymLocker.objects.create(
            gym=self.gym,
            number=2,
        )

        self.assertIsNone(locker.assigned_user)
