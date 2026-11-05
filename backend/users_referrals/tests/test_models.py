# user_referrals/tests/test_models.py


from django.test import TestCase
from django.db import IntegrityError
from users.models import User
from users_referrals.models import Referral
from django.utils import timezone
from datetime import timedelta
from django.db import transaction
from core.errors import APIError, ReferralError


class ReferralModelTest(TestCase):
    """Test Referral model"""

    def setUp(self):
        self.referrer = User.objects.create_user(
            phone_number="09123456788",
            first_name="Referrer",
            last_name="User",
            gender=User.Gender.MALE,
        )

        self.referred = User.objects.create_user(
            phone_number="09123456789",
            first_name="Referred",
            last_name="User",
            gender=User.Gender.MALE,
        )

    def test_create_referral(self):
        """Test creating a referral"""
        referral = Referral.objects.create(
            referrer=self.referrer, referred_user=self.referred
        )

        self.assertEqual(referral.referrer, self.referrer)
        self.assertEqual(referral.referred_user, self.referred)
        self.assertIsNotNone(referral.referred_at)
        self.assertIsNotNone(referral.created_at)

    def test_unique_together_constraint(self):
        """Test unique_together constraint"""
        Referral.objects.create(referrer=self.referrer, referred_user=self.referred)

        with self.assertRaises(IntegrityError):
            Referral.objects.create(referrer=self.referrer, referred_user=self.referred)

    def test_referral_str(self):
        """Test string representation"""
        referral = Referral.objects.create(
            referrer=self.referrer, referred_user=self.referred
        )

        expected = f"{self.referred} referred by {self.referrer}"
        self.assertEqual(str(referral), expected)

    def test_cannot_refer_self(self):
        """Test a user cannot refer themselves"""
        with self.assertRaises(APIError) as context:
            Referral.objects.create(referrer=self.referrer, referred_user=self.referrer)

        self.assertEqual(
            context.exception.error_code, ReferralError.SELF_REFERRAL_NOT_ALLOWED[0]
        )

    def test_bulk_create_rejects_self_referral(self):
        for ignore_conflicts in (False, True):
            with self.subTest(ignore_conflicts=ignore_conflicts):
                with self.assertRaises(IntegrityError) as context:
                    with transaction.atomic():
                        Referral.objects.bulk_create(
                            [
                                Referral(
                                    referrer=self.referrer, referred_user=self.referred
                                ),
                                Referral(
                                    referrer=self.referrer, referred_user=self.referrer
                                ),
                            ],
                            ignore_conflicts=ignore_conflicts,
                        )

                self.assertEqual(
                    context.exception.__cause__.diag.constraint_name,
                    "referral_no_self_referral",
                )
                self.assertFalse(Referral.objects.exists())

    def test_queryset_update_rejects_self_referral(self):
        referral = Referral.objects.create(
            referrer=self.referrer, referred_user=self.referred
        )
        for field, value in (
            ("referrer_id", self.referred.pk),
            ("referred_user_id", self.referrer.pk),
        ):
            with self.subTest(field=field):
                with self.assertRaises(IntegrityError) as context:
                    with transaction.atomic():
                        Referral.objects.filter(pk=referral.pk).update(**{field: value})

                self.assertEqual(
                    context.exception.__cause__.diag.constraint_name,
                    "referral_no_self_referral",
                )
                referral.refresh_from_db()
                self.assertEqual(referral.referrer_id, self.referrer.pk)
                self.assertEqual(referral.referred_user_id, self.referred.pk)

    def test_bulk_update_rejects_self_referral(self):
        referral = Referral.objects.create(
            referrer=self.referrer, referred_user=self.referred
        )
        referral.referred_user = self.referrer

        with self.assertRaises(IntegrityError) as context:
            with transaction.atomic():
                Referral.objects.bulk_update([referral], ["referred_user"])

        self.assertEqual(
            context.exception.__cause__.diag.constraint_name,
            "referral_no_self_referral",
        )
        referral.refresh_from_db()
        self.assertEqual(referral.referrer_id, self.referrer.pk)
        self.assertEqual(referral.referred_user_id, self.referred.pk)

    def test_bulk_and_queryset_updates_allow_distinct_users(self):
        other_referrer = User.objects.create_user(
            phone_number="09123456787",
            first_name="Another",
            last_name="Referrer",
            gender=User.Gender.MALE,
        )
        referral = Referral.objects.create(
            referrer=self.referrer, referred_user=self.referred
        )
        referral.referrer = other_referrer

        Referral.objects.bulk_update([referral], ["referrer"])
        referral.refresh_from_db()
        self.assertEqual(referral.referrer_id, other_referrer.pk)
        self.assertEqual(referral.referred_user_id, self.referred.pk)

        Referral.objects.filter(pk=referral.pk).update(referred_user=self.referrer)
        referral.refresh_from_db()
        self.assertEqual(referral.referrer_id, other_referrer.pk)
        self.assertEqual(referral.referred_user_id, self.referrer.pk)

    def test_referral_relationships(self):
        """Test referral relationships"""
        referral = Referral.objects.create(
            referrer=self.referrer, referred_user=self.referred
        )

        # Test reverse relationships
        self.assertEqual(self.referrer.recruits.count(), 1)
        self.assertEqual(self.referred.sponsor.count(), 1)
        self.assertEqual(self.referrer.recruits.first(), referral)
        self.assertEqual(self.referred.sponsor.first(), referral)

    def test_referral_auto_timestamps(self):
        """Test that timestamps are automatically set"""
        referral = Referral.objects.create(
            referrer=self.referrer, referred_user=self.referred
        )

        self.assertIsNotNone(referral.referred_at)
        self.assertIsNotNone(referral.created_at)
        self.assertIsNotNone(referral.updated_at)

        # referred_at should be set to current time
        now = timezone.now()
        time_diff = now - referral.referred_at
        self.assertLess(time_diff.total_seconds(), 1)  # Less than 1 second difference

    def test_referral_updated_at_updates(self):
        """Test that updated_at is updated when model changes"""
        referral = Referral.objects.create(
            referrer=self.referrer, referred_user=self.referred
        )

        old_updated_at = referral.updated_at

        # Wait a moment
        import time

        time.sleep(0.1)

        # Make a change and save
        referral.referred_at = timezone.now()
        referral.save()
        referral.refresh_from_db()

        self.assertNotEqual(referral.updated_at, old_updated_at)

    def test_referral_model_meta(self):
        """Test model meta configuration"""
        # Check db_table
        self.assertEqual(Referral._meta.db_table, "user_referrals")

        # Check ordering
        self.assertEqual(Referral._meta.ordering, ["-created_at"])

        # Check unique_together - Django stores as tuple of tuples
        self.assertEqual(
            Referral._meta.unique_together, (("referrer", "referred_user"),)
        )

    def test_referral_related_names(self):
        """Test the related names work correctly"""
        referral = Referral.objects.create(
            referrer=self.referrer, referred_user=self.referred
        )

        # Test recruits (people I recruited)
        recruits = self.referrer.recruits.all()
        self.assertEqual(recruits.count(), 1)
        self.assertEqual(recruits.first(), referral)

        # Test sponsor (who recruited me)
        sponsors = self.referred.sponsor.all()
        self.assertEqual(sponsors.count(), 1)
        self.assertEqual(sponsors.first(), referral)

        # Test multiple referrals
        another_referred = User.objects.create_user(
            phone_number="09123456780",
            first_name="Another",
            last_name="User",
            gender=User.Gender.MALE,
        )

        referral2 = Referral.objects.create(
            referrer=self.referrer, referred_user=another_referred
        )

        self.assertEqual(self.referrer.recruits.count(), 2)
        self.assertEqual(self.referred.sponsor.count(), 1)

    def test_referral_cascade_delete(self):
        """Test that referrals are deleted when users are deleted"""
        referral = Referral.objects.create(
            referrer=self.referrer, referred_user=self.referred
        )

        self.assertEqual(Referral.objects.count(), 1)

        # Delete referrer - should cascade delete
        self.referrer.delete()
        self.assertEqual(Referral.objects.count(), 0)

    def test_referral_cascade_delete_referred(self):
        """Test that referrals are deleted when referred user is deleted"""
        referral = Referral.objects.create(
            referrer=self.referrer, referred_user=self.referred
        )

        self.assertEqual(Referral.objects.count(), 1)

        # Delete referred user - should cascade delete
        self.referred.delete()
        self.assertEqual(Referral.objects.count(), 0)

    def test_referral_duplicate_prevention(self):
        """Test that the unique_together constraint prevents duplicates"""
        Referral.objects.create(referrer=self.referrer, referred_user=self.referred)

        # Attempt to create duplicate - wrap in atomic block to handle error
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Referral.objects.create(
                    referrer=self.referrer, referred_user=self.referred
                )

        # But should allow different referrer for same referred user
        another_referrer = User.objects.create_user(
            phone_number="09123456787",
            first_name="Another",
            last_name="Referrer",
            gender=User.Gender.MALE,
        )

        referral2 = Referral.objects.create(
            referrer=another_referrer, referred_user=self.referred
        )
        self.assertEqual(referral2.referrer, another_referrer)
        self.assertEqual(referral2.referred_user, self.referred)

    def test_referral_field_constraints(self):
        """Test field constraints"""
        referral = Referral.objects.create(
            referrer=self.referrer, referred_user=self.referred
        )

        # Test UUID field is automatically set
        self.assertIsNotNone(referral.id)
        self.assertEqual(len(str(referral.id)), 36)  # UUID format

        # Test that id is not editable
        field = Referral._meta.get_field("id")
        self.assertFalse(field.editable)

    def test_referral_referred_at_custom_value(self):
        """Test that referred_at can be set to a custom value"""
        custom_time = timezone.now() - timedelta(days=7)
        referral = Referral.objects.create(
            referrer=self.referrer, referred_user=self.referred, referred_at=custom_time
        )

        self.assertEqual(referral.referred_at.date(), custom_time.date())

    def test_referral_bulk_create(self):
        """Test bulk creating multiple referrals"""
        users = []
        for i in range(3):
            user = User.objects.create_user(
                phone_number=f"091234567{80 + i}",
                first_name=f"User{i}",
                last_name="Test",
                gender=User.Gender.MALE,
            )
            users.append(user)

        referrals = []
        for user in users:
            referral = Referral(referrer=self.referrer, referred_user=user)
            referrals.append(referral)

        Referral.objects.bulk_create(referrals)

        self.assertEqual(Referral.objects.filter(referrer=self.referrer).count(), 3)
