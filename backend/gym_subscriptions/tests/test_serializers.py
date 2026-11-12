# gym_subscriptions/tests/test_serializers.py


from datetime import timedelta
from django.test import TestCase
from django.utils import timezone
from commerce_orders.models import Order
from gym.models import Gym
from gym_plans.models import GymMembershipPlan
from gym_subscriptions.models import GymSubscription
from gym_subscriptions.serializers import GymSubscriptionReadSerializer
from users.models import User


class GymSubscriptionSerializerTestBase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            phone_number="09120000001",
            password="testpassword123",
        )

        self.gym = Gym.objects.create(
            name="Test Gym",
            province="Tehran",
            city="Tehran",
            address="Test Address",
        )

        self.plan = GymMembershipPlan.objects.create_plan(
            name="Monthly Plan",
            gym=self.gym,
            duration_months=1,
            visit_limit=30,
            price=10000,
        )

        self.order = Order.objects.create(
            seller=User.objects.get_or_create(phone_number="09999999999")[0],
            buyer=self.user,
            status=Order.Status.SUCCEEDED,
            subtotal_amount=10000,
            discount_amount=0,
            tax_amount=0,
            succeeded_at=timezone.now(),
            commerce_product=self.plan.id,
            product_snapshot={"id": str(self.plan.pk), "name": self.plan.name},
        )

    def make_subscription(self, **overrides):
        defaults = dict(
            subscriber=self.user,
            plan=self.plan,
            order=self.order,
            status=GymSubscription.Status.PENDING,
            initial_visits=self.plan.visit_limit,
            remaining_visits=self.plan.visit_limit,
            duration_months=self.plan.duration_months,
        )
        defaults.update(overrides)
        return GymSubscription.objects.create(**defaults)


# ============================================================================
# Field presence
# ============================================================================
class GymSubscriptionSerializerFieldsTests(GymSubscriptionSerializerTestBase):
    def test_serializer_outputs_all_declared_fields(self):
        sub = self.make_subscription()
        data = GymSubscriptionReadSerializer(sub).data

        expected_keys = {
            "id",
            "plan",
            "gym",
            "status",
            "end_reason",
            "initial_visits",
            "remaining_visits",
            "started_at",
            "expires_at",
            "cancelled_at",
            "created_at",
            "updated_at",
        }
        self.assertEqual(set(data.keys()), expected_keys)

    def test_initial_visits_reports_snapshot_when_visits_have_been_used(self):
        sub = self.make_subscription(remaining_visits=29)
        data = GymSubscriptionReadSerializer(sub).data
        self.assertEqual(data["initial_visits"], 30)
        self.assertEqual(data["remaining_visits"], 29)

    def test_id_is_string(self):
        sub = self.make_subscription()
        data = GymSubscriptionReadSerializer(sub).data

        self.assertIsInstance(data["id"], str)
        self.assertEqual(data["id"], str(sub.pk))

    def test_plan_is_nested_object_not_id(self):
        sub = self.make_subscription()
        data = GymSubscriptionReadSerializer(sub).data

        self.assertIsInstance(data["plan"], dict)
        self.assertIn("id", data["plan"])
        self.assertIn("name", data["plan"])
        self.assertIn("gym", data["plan"])

    def test_plan_id_matches_subscription_plan(self):
        sub = self.make_subscription()
        data = GymSubscriptionReadSerializer(sub).data

        self.assertEqual(data["plan"]["id"], self.plan.pk)
        self.assertEqual(data["plan"]["name"], "Monthly Plan")

    def test_plan_gym_is_nested(self):
        sub = self.make_subscription()
        data = GymSubscriptionReadSerializer(sub).data

        self.assertIsInstance(data["plan"]["gym"], dict)
        self.assertEqual(data["plan"]["gym"]["id"], str(self.gym.pk))
        self.assertEqual(data["plan"]["gym"]["name"], "Test Gym")

    def test_top_level_gym_is_nested_object(self):
        sub = self.make_subscription()
        data = GymSubscriptionReadSerializer(sub).data

        self.assertIn("gym", data)
        self.assertIsInstance(data["gym"], dict)
        self.assertEqual(data["gym"]["id"], str(self.gym.pk))
        self.assertEqual(data["gym"]["name"], "Test Gym")

    def test_top_level_gym_matches_plan_gym(self):
        sub = self.make_subscription()
        data = GymSubscriptionReadSerializer(sub).data

        self.assertEqual(data["gym"], data["plan"]["gym"])

    def test_plan_exposes_expected_fields(self):
        sub = self.make_subscription()
        data = GymSubscriptionReadSerializer(sub).data

        for key in (
            "id",
            "name",
            "gym",
            "description",
            "duration_months",
            "visit_limit",
            "is_active",
            "price",
        ):
            self.assertIn(key, data["plan"])

    def test_gym_exposes_expected_fields(self):
        sub = self.make_subscription()
        data = GymSubscriptionReadSerializer(sub).data

        for key in ("id", "name", "province", "city", "address", "is_active"):
            self.assertIn(key, data["gym"])

    def test_plan_gym_exposes_expected_fields(self):
        sub = self.make_subscription()
        data = GymSubscriptionReadSerializer(sub).data

        for key in ("id", "name", "province", "city", "address", "is_active"):
            self.assertIn(key, data["plan"]["gym"])


# ============================================================================
# Field values
# ============================================================================
class GymSubscriptionSerializerValuesTests(GymSubscriptionSerializerTestBase):
    def test_status_is_raw_enum_value(self):
        sub = self.make_subscription(status=GymSubscription.Status.ACTIVE)
        data = GymSubscriptionReadSerializer(sub).data

        self.assertEqual(data["status"], "ACTIVE")
        self.assertIsInstance(data["status"], str)

    def test_pending_status(self):
        sub = self.make_subscription(status=GymSubscription.Status.PENDING)
        data = GymSubscriptionReadSerializer(sub).data
        self.assertEqual(data["status"], "PENDING")

    def test_expired_status(self):
        sub = self.make_subscription(status=GymSubscription.Status.EXPIRED)
        data = GymSubscriptionReadSerializer(sub).data
        self.assertEqual(data["status"], "EXPIRED")

    def test_cancelled_status(self):
        sub = self.make_subscription(status=GymSubscription.Status.CANCELLED)
        data = GymSubscriptionReadSerializer(sub).data
        self.assertEqual(data["status"], "CANCELLED")

    def test_end_reason_null_when_not_set(self):
        sub = self.make_subscription(status=GymSubscription.Status.PENDING)
        data = GymSubscriptionReadSerializer(sub).data
        self.assertIsNone(data["end_reason"])

    def test_end_reason_time(self):
        sub = self.make_subscription(
            status=GymSubscription.Status.EXPIRED,
            end_reason=GymSubscription.EndReason.TIME,
        )
        data = GymSubscriptionReadSerializer(sub).data
        self.assertEqual(data["end_reason"], "TIME")

    def test_end_reason_visits(self):
        sub = self.make_subscription(
            status=GymSubscription.Status.EXPIRED,
            end_reason=GymSubscription.EndReason.VISITS,
        )
        data = GymSubscriptionReadSerializer(sub).data
        self.assertEqual(data["end_reason"], "VISITS")

    def test_end_reason_cancelled(self):
        sub = self.make_subscription(
            status=GymSubscription.Status.CANCELLED,
            end_reason=GymSubscription.EndReason.CANCELLED,
        )
        data = GymSubscriptionReadSerializer(sub).data
        self.assertEqual(data["end_reason"], "CANCELLED")

    def test_remaining_visits_is_integer(self):
        sub = self.make_subscription(remaining_visits=42)
        data = GymSubscriptionReadSerializer(sub).data

        self.assertEqual(data["remaining_visits"], 42)
        self.assertIsInstance(data["remaining_visits"], int)

    def test_remaining_visits_zero(self):
        sub = self.make_subscription(remaining_visits=0)
        data = GymSubscriptionReadSerializer(sub).data
        self.assertEqual(data["remaining_visits"], 0)

    def test_started_at_null_for_pending(self):
        sub = self.make_subscription(status=GymSubscription.Status.PENDING)
        data = GymSubscriptionReadSerializer(sub).data
        self.assertIsNone(data["started_at"])

    def test_started_at_serialized_when_set(self):
        started = timezone.now()
        sub = self.make_subscription(
            status=GymSubscription.Status.ACTIVE,
            started_at=started,
        )
        data = GymSubscriptionReadSerializer(sub).data
        self.assertIsNotNone(data["started_at"])

    def test_expires_at_null_for_pending(self):
        sub = self.make_subscription(status=GymSubscription.Status.PENDING)
        data = GymSubscriptionReadSerializer(sub).data
        self.assertIsNone(data["expires_at"])

    def test_expires_at_serialized_when_set(self):
        expires = timezone.now() + timedelta(days=30)
        sub = self.make_subscription(
            status=GymSubscription.Status.ACTIVE,
            expires_at=expires,
        )
        data = GymSubscriptionReadSerializer(sub).data
        self.assertIsNotNone(data["expires_at"])

    def test_cancelled_at_null_when_not_cancelled(self):
        sub = self.make_subscription(status=GymSubscription.Status.ACTIVE)
        data = GymSubscriptionReadSerializer(sub).data
        self.assertIsNone(data["cancelled_at"])

    def test_cancelled_at_set_when_cancelled(self):
        cancelled = timezone.now()
        sub = self.make_subscription(
            status=GymSubscription.Status.CANCELLED,
            end_reason=GymSubscription.EndReason.CANCELLED,
            cancelled_at=cancelled,
        )
        data = GymSubscriptionReadSerializer(sub).data
        self.assertIsNotNone(data["cancelled_at"])

    def test_created_at_and_updated_at_present(self):
        sub = self.make_subscription()
        data = GymSubscriptionReadSerializer(sub).data
        self.assertIsNotNone(data["created_at"])
        self.assertIsNotNone(data["updated_at"])

    def test_price_is_string_int(self):
        sub = self.make_subscription()
        data = GymSubscriptionReadSerializer(sub).data
        self.assertEqual(data["plan"]["price"], 10000)

    def test_plan_duration_month_and_visit_limit(self):
        sub = self.make_subscription()
        data = GymSubscriptionReadSerializer(sub).data
        self.assertEqual(data["plan"]["duration_months"], 1)
        self.assertEqual(data["plan"]["visit_limit"], 30)

    def test_plan_is_active_reflects_plan_state(self):
        sub = self.make_subscription()
        data = GymSubscriptionReadSerializer(sub).data
        self.assertTrue(data["plan"]["is_active"])

    def test_gym_fields_are_correct(self):
        sub = self.make_subscription()
        data = GymSubscriptionReadSerializer(sub).data
        gym = data["gym"]
        self.assertEqual(gym["province"], "Tehran")
        self.assertEqual(gym["city"], "Tehran")
        self.assertEqual(gym["address"], "Test Address")

    def test_top_level_gym_fields_are_correct(self):
        sub = self.make_subscription()
        data = GymSubscriptionReadSerializer(sub).data
        gym = data["gym"]
        self.assertEqual(gym["id"], str(self.gym.pk))
        self.assertEqual(gym["name"], "Test Gym")
        self.assertEqual(gym["province"], "Tehran")
        self.assertEqual(gym["city"], "Tehran")
        self.assertEqual(gym["address"], "Test Address")


# ============================================================================
# Read-only enforcement
# ============================================================================
class GymSubscriptionSerializerReadOnlyTests(GymSubscriptionSerializerTestBase):
    def test_all_fields_are_read_only(self):
        serializer = GymSubscriptionReadSerializer()
        for field_name, field in serializer.fields.items():
            self.assertTrue(
                field.read_only,
                f"Field {field_name!r} is not read-only",
            )

    def test_serializer_ignores_input_on_all_fields(self):
        sub = self.make_subscription(
            status=GymSubscription.Status.ACTIVE,
            remaining_visits=10,
        )
        serializer = GymSubscriptionReadSerializer(
            sub,
            data={
                "status": "CANCELLED",
                "remaining_visits": 999,
            },
        )
        self.assertTrue(serializer.is_valid())
        self.assertEqual(serializer.data["status"], "ACTIVE")
        self.assertEqual(serializer.data["remaining_visits"], 10)


# ============================================================================
# Many=True (list serialization)
# ============================================================================
class GymSubscriptionSerializerManyTests(GymSubscriptionSerializerTestBase):
    def test_serializes_queryset(self):
        self.make_subscription(status=GymSubscription.Status.PENDING)

        order_2 = Order.objects.create(
            seller=User.objects.get_or_create(phone_number="09999999999")[0],
            buyer=self.user,
            status=Order.Status.SUCCEEDED,
            subtotal_amount=100000,
            discount_amount=0,
            tax_amount=0,
            succeeded_at=timezone.now(),
            commerce_product=self.plan.id,
            product_snapshot={},
        )
        GymSubscription.objects.create(
            subscriber=self.user,
            plan=self.plan,
            order=order_2,
            initial_visits=self.plan.visit_limit,
            remaining_visits=self.plan.visit_limit,
            duration_months=self.plan.duration_months,
            status=GymSubscription.Status.CANCELLED,
            end_reason=GymSubscription.EndReason.CANCELLED,
            cancelled_at=timezone.now(),
        )

        qs = GymSubscription.objects.filter(subscriber=self.user)
        data = GymSubscriptionReadSerializer(qs, many=True).data

        self.assertEqual(len(data), 2)
        for item in data:
            self.assertIn("gym", item)
            self.assertIn("plan", item)
            self.assertIn("gym", item["plan"])

    def test_serializes_empty_queryset(self):
        qs = GymSubscription.objects.filter(
            subscriber=self.user,
            status=GymSubscription.Status.ACTIVE,
        )
        data = GymSubscriptionReadSerializer(qs, many=True).data
        self.assertEqual(data, [])


# ============================================================================
# Query count / N+1 — the serializer itself, without a view
# ============================================================================
class GymSubscriptionSerializerQueryCountTests(GymSubscriptionSerializerTestBase):
    def test_serializer_does_not_fetch_per_row_when_prefetched(self):
        orders = []
        for _ in range(5):
            order = Order.objects.create(
                seller=User.objects.get_or_create(phone_number="09999999999")[0],
                buyer=self.user,
                status=Order.Status.SUCCEEDED,
                subtotal_amount=100000,
                discount_amount=0,
                tax_amount=0,
                succeeded_at=timezone.now(),
                commerce_product=self.plan.id,
                product_snapshot={},
            )
            orders.append(order)
        for oi in orders:
            GymSubscription.objects.create(
                subscriber=self.user,
                plan=self.plan,
                order=oi,
                initial_visits=self.plan.visit_limit,
                remaining_visits=0,
                duration_months=self.plan.duration_months,
                status=GymSubscription.Status.EXPIRED,
            )

        qs = GymSubscription.objects.select_related("plan", "plan__gym")

        with self.assertNumQueries(1):
            list(GymSubscriptionReadSerializer(qs, many=True).data)

    def test_serializer_fires_extra_queries_without_prefetch(self):
        orders = []
        for _ in range(3):
            order = Order.objects.create(
                seller=User.objects.get_or_create(phone_number="09999999999")[0],
                buyer=self.user,
                status=Order.Status.SUCCEEDED,
                subtotal_amount=100000,
                discount_amount=0,
                tax_amount=0,
                succeeded_at=timezone.now(),
                commerce_product=self.plan.id,
                product_snapshot={},
            )
            orders.append(order)
        for oi in orders:
            GymSubscription.objects.create(
                subscriber=self.user,
                plan=self.plan,
                order=oi,
                initial_visits=self.plan.visit_limit,
                remaining_visits=0,
                duration_months=self.plan.duration_months,
                status=GymSubscription.Status.EXPIRED,
            )

        qs = GymSubscription.objects.all()

        # 1 fetch + 3 plan + 3 gym = 7 with no prefetch.
        with self.assertNumQueries(7):
            list(GymSubscriptionReadSerializer(qs, many=True).data)
