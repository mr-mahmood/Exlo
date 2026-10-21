# gym_auth/tests/test_serializers.py
# type: ignore

from django.test import TestCase
from gym.models import Gym
from users.models import User
from gym_auth.models import UserGymRole
from gym_auth.serializers import UserGymRoleSerializer


class UserGymRoleSerializerTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            phone_number="09129876543",
            first_name="Test",
            last_name="User",
        )

        self.gym = Gym.objects.create(
            name="Test Gym",
            province="Test Province",
            city="Test City",
            address="123 Test St",
            is_active=True,
        )

        self.role = UserGymRole.objects.create(
            user=self.user,
            gym=self.gym,
            role=UserGymRole.Role.COACH,
        )

    def test_serialize_role_fields(self):
        serializer = UserGymRoleSerializer(instance=self.role)

        self.assertEqual(
            set(serializer.data.keys()),
            {"id", "user", "gym", "role", "created_at"},
        )

        self.assertEqual(serializer.data["id"], str(self.role.id))
        self.assertEqual(serializer.data["gym"], self.gym.id)
        self.assertEqual(serializer.data["role"], UserGymRole.Role.COACH)
        self.assertIsNotNone(serializer.data["created_at"])

    def test_serialize_nested_user(self):
        serializer = UserGymRoleSerializer(instance=self.role)

        self.assertEqual(
            serializer.data["user"],
            {
                "phone_number": self.user.phone_number,
                "first_name": self.user.first_name,
                "last_name": self.user.last_name,
            },
        )

    def test_all_fields_are_read_only(self):
        serializer = UserGymRoleSerializer()

        self.assertEqual(
            set(serializer.fields.keys()),
            {"id", "user", "gym", "role", "created_at"},
        )

        for field in serializer.fields.values():
            self.assertTrue(field.read_only)

    def test_serialize_multiple_roles(self):
        second_user = User.objects.create_user(
            phone_number="09121112222",
            first_name="Second",
            last_name="User",
        )

        second_role = UserGymRole.objects.create(
            user=second_user,
            gym=self.gym,
            role=UserGymRole.Role.STAFF,
        )

        serializer = UserGymRoleSerializer(
            instance=[self.role, second_role],
            many=True,
        )

        self.assertEqual(len(serializer.data), 2)
        self.assertEqual(
            serializer.data[0]["user"]["phone_number"],
            self.user.phone_number,
        )
        self.assertEqual(
            serializer.data[1]["user"]["phone_number"],
            second_user.phone_number,
        )
