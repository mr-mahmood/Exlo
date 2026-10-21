# gym_devices/tests/test_models.py

import time
import uuid

from core.hashing import hash_secret, verify_secret
from django.conf import settings
from django.db.models import ProtectedError
from django.test import TestCase

from core.errors import APIError, GymDeviceError
from gym.models import Gym
from gym_devices.models import GymDevice, GymDeviceManager


class GymDeviceManagerGetDeviceTests(TestCase):

    def setUp(self):
        settings.DEBUG = True
        self.gym = Gym.objects.create(name="Gym A")
        self.other_gym = Gym.objects.create(name="Gym B")

    def test_get_device_returns_active_device(self):
        device = GymDevice.objects.create(
            gym=self.gym,
            device_type=GymDevice.GymDeviceType.ENTRANCE,
            token_hash="hash",
            token_prefix="abcdefghijkl",
        )

        result = GymDevice.objects.get_device(
            device.id,
            self.gym,
        )

        self.assertEqual(result, device)

    def test_get_device_raises_when_not_found(self):
        with self.assertRaises(APIError) as ctx:
            GymDevice.objects.get_device(
                uuid.uuid7(),
                self.gym,
            )

        self.assertEqual(
            ctx.exception.error_code,
            GymDeviceError.DEVICE_NOT_FOUND[0],
        )

    def test_get_device_raises_when_device_belongs_to_other_gym(self):
        device = GymDevice.objects.create(
            gym=self.other_gym,
            device_type=GymDevice.GymDeviceType.ENTRANCE,
            token_hash="hash",
            token_prefix="abcdefghijkl",
        )

        with self.assertRaises(APIError):
            GymDevice.objects.get_device(
                device.id,
                self.gym,
            )

    def test_get_device_returns_inactive_device(self):
        device = GymDevice.objects.create(
            gym=self.gym,
            device_type=GymDevice.GymDeviceType.ENTRANCE,
            token_hash="hash",
            token_prefix="abcdefghijkl",
            is_active=False,
        )

        result = GymDevice.objects.get_device(
            device.id,
            self.gym,
        )

        self.assertEqual(result, device)
        self.assertFalse(result.is_active)


class GymDeviceManagerFindDeviceTests(TestCase):

    def setUp(self):
        settings.DEBUG = True
        self.gym = Gym.objects.create(name="Gym A")
        self.other_gym = Gym.objects.create(name="Gym B")

    def _create_device(
        self,
        gym,
        raw_token=None,
        device_type=GymDevice.GymDeviceType.ENTRANCE,
    ):
        raw_token = raw_token or "a" * 64

        return (
            GymDevice.objects.create(
                gym=gym,
                device_type=device_type,
                token_hash=hash_secret(raw_token),
                token_prefix=raw_token[:12],
            ),
            raw_token,
        )

    def test_find_device_returns_device_on_valid_token(self):
        device, raw = self._create_device(self.gym)

        found = GymDevice.objects.find_device(
            self.gym,
            raw,
        )

        self.assertEqual(found, device)

    def test_find_device_works_for_locker_device(self):
        device, raw = self._create_device(
            self.gym,
            device_type=GymDevice.GymDeviceType.LOCKER,
        )

        found = GymDevice.objects.find_device(
            self.gym,
            raw,
        )

        self.assertEqual(found, device)
        self.assertEqual(
            found.device_type,
            GymDevice.GymDeviceType.LOCKER,
        )

    def test_find_device_short_token_raises(self):
        with self.assertRaises(APIError) as ctx:
            GymDevice.objects.find_device(
                self.gym,
                "short",
            )

        self.assertEqual(
            ctx.exception.error_code,
            GymDeviceError.DEVICE_NOT_FOUND[0],
        )

    def test_find_device_empty_token_raises(self):
        with self.assertRaises(APIError):
            GymDevice.objects.find_device(
                self.gym,
                "",
            )

    def test_find_device_token_exactly_11_chars_raises(self):
        with self.assertRaises(APIError):
            GymDevice.objects.find_device(
                self.gym,
                "a" * 11,
            )

    def test_find_device_token_12_chars_looks_up_prefix(self):
        with self.assertRaises(APIError):
            GymDevice.objects.find_device(
                self.gym,
                "a" * 12,
            )

    def test_find_device_wrong_prefix_raises(self):
        self._create_device(
            self.gym,
            raw_token="a" * 64,
        )

        with self.assertRaises(APIError):
            GymDevice.objects.find_device(
                self.gym,
                "b" * 64,
            )

    def test_find_device_correct_prefix_wrong_hash_raises(self):
        device, raw = self._create_device(
            self.gym,
            raw_token="a" * 64,
        )

        tampered = "a" * 12 + "b" * 52

        self.assertEqual(
            tampered[:12],
            raw[:12],
        )

        with self.assertRaises(APIError):
            GymDevice.objects.find_device(
                self.gym,
                tampered,
            )

    def test_find_device_wrong_gym_raises(self):
        _, raw = self._create_device(
            self.gym,
            raw_token="a" * 64,
        )

        with self.assertRaises(APIError):
            GymDevice.objects.find_device(
                self.other_gym,
                raw,
            )

    def test_find_device_inactive_device_raises(self):
        device, raw = self._create_device(self.gym)

        device.is_active = False
        device.save(update_fields=["is_active"])

        with self.assertRaises(APIError):
            GymDevice.objects.find_device(
                self.gym,
                raw,
            )


class GymDeviceManagerRegisterDeviceTests(TestCase):

    def setUp(self):
        settings.DEBUG = True
        self.gym = Gym.objects.create(name="Gym A")

    def test_register_entrance_device(self):
        device, raw = GymDevice.objects.register_device(
            gym=self.gym,
            device_type=GymDevice.GymDeviceType.ENTRANCE,
        )

        self.assertIsInstance(device, GymDevice)
        self.assertIsInstance(raw, str)
        self.assertEqual(len(raw), 64)
        self.assertEqual(device.gym, self.gym)
        self.assertEqual(
            device.device_type,
            GymDevice.GymDeviceType.ENTRANCE,
        )
        self.assertTrue(device.is_active)
        self.assertEqual(device.token_prefix, raw[:12])

    def test_register_locker_device(self):
        device, raw = GymDevice.objects.register_device(
            gym=self.gym,
            device_type=GymDevice.GymDeviceType.LOCKER,
        )

        self.assertEqual(
            device.device_type,
            GymDevice.GymDeviceType.LOCKER,
        )
        self.assertTrue(verify_secret(raw, device.token_hash))

    def test_register_device_hash_matches_raw_token(self):
        device, raw = GymDevice.objects.register_device(
            gym=self.gym,
            device_type=GymDevice.GymDeviceType.ENTRANCE,
        )

        self.assertTrue(verify_secret(raw, device.token_hash))
        self.assertFalse(verify_secret("wrong", device.token_hash))

    def test_register_device_generates_unique_tokens(self):
        _, raw1 = GymDevice.objects.register_device(
            gym=self.gym,
            device_type=GymDevice.GymDeviceType.ENTRANCE,
        )
        _, raw2 = GymDevice.objects.register_device(
            gym=self.gym,
            device_type=GymDevice.GymDeviceType.LOCKER,
        )

        self.assertNotEqual(raw1, raw2)

    def test_register_device_persists_to_db(self):
        device, _ = GymDevice.objects.register_device(
            gym=self.gym,
            device_type=GymDevice.GymDeviceType.ENTRANCE,
        )

        self.assertTrue(GymDevice.objects.filter(id=device.id).exists())


class GymDeviceManagerGenerateTokenTests(TestCase):

    def test_generate_token_is_64_hex_chars(self):
        token = GymDeviceManager._generate_token()

        self.assertEqual(len(token), 64)
        int(token, 16)

    def test_generate_token_unique(self):
        tokens = {GymDeviceManager._generate_token() for _ in range(100)}

        self.assertEqual(len(tokens), 100)


class GymDeviceModelTests(TestCase):

    def setUp(self):
        self.gym = Gym.objects.create(name="Gym A")

    def _create_device(self, **kwargs) -> GymDevice:
        defaults = {
            "gym": self.gym,
            "device_type": GymDevice.GymDeviceType.ENTRANCE,
            "token_hash": "hash",
            "token_prefix": "abcdefghijkl",
        }

        defaults.update(kwargs)

        return GymDevice.objects.create(**defaults)

    def test_default_id_is_uuid(self):
        device = self._create_device()

        self.assertIsInstance(device.id, uuid.UUID)

    def test_default_is_active_true(self):
        device = self._create_device()

        self.assertTrue(device.is_active)

    def test_device_type_is_stored(self):
        device = self._create_device(
            device_type=GymDevice.GymDeviceType.LOCKER,
        )

        self.assertEqual(
            device.device_type,
            GymDevice.GymDeviceType.LOCKER,
        )

    def test_device_type_choices(self):
        self.assertEqual(
            GymDevice.GymDeviceType.ENTRANCE,
            "entrance",
        )
        self.assertEqual(
            GymDevice.GymDeviceType.LOCKER,
            "locker",
        )

    def test_str_ordering_newest_first(self):
        d1 = self._create_device(
            token_hash="h1",
            token_prefix="p1" * 6,
        )
        d2 = self._create_device(
            token_hash="h2",
            token_prefix="p2" * 6,
        )

        devices = list(GymDevice.objects.all())

        self.assertEqual(devices[0], d2)
        self.assertEqual(devices[1], d1)

    def test_db_table_name(self):
        self.assertEqual(
            GymDevice._meta.db_table,
            "gym_device",
        )

    def test_deactivate_device_sets_inactive(self):
        device = self._create_device()

        device.deactivate_device()
        device.refresh_from_db()

        self.assertFalse(device.is_active)

    def test_deactivate_device_preserves_other_fields(self):
        device = self._create_device()
        original_hash = device.token_hash
        original_type = device.device_type

        device.deactivate_device()
        device.refresh_from_db()

        self.assertFalse(device.is_active)
        self.assertEqual(device.token_hash, original_hash)
        self.assertEqual(device.device_type, original_type)

    def test_deactivate_device_is_idempotent(self):
        device = self._create_device()

        device.deactivate_device()
        device.deactivate_device()
        device.refresh_from_db()

        self.assertFalse(device.is_active)

    def test_activate_device_sets_active(self):
        device = self._create_device(is_active=False)

        device.activate_device()
        device.refresh_from_db()

        self.assertTrue(device.is_active)

    def test_activate_device_preserves_other_fields(self):
        device = self._create_device(is_active=False)
        original_hash = device.token_hash
        original_type = device.device_type

        device.activate_device()
        device.refresh_from_db()

        self.assertTrue(device.is_active)
        self.assertEqual(device.token_hash, original_hash)
        self.assertEqual(device.device_type, original_type)

    def test_activate_device_is_idempotent(self):
        device = self._create_device(is_active=False)

        device.activate_device()
        device.activate_device()
        device.refresh_from_db()

        self.assertTrue(device.is_active)

    def test_deactivate_then_activate_device(self):
        device = self._create_device()

        device.deactivate_device()
        device.refresh_from_db()
        self.assertFalse(device.is_active)

        device.activate_device()
        device.refresh_from_db()
        self.assertTrue(device.is_active)

    def test_gym_protected_on_delete(self):
        self._create_device()

        with self.assertRaises(ProtectedError):
            self.gym.delete()

    def test_related_name_devices(self):
        self._create_device()

        self.assertEqual(
            self.gym.devices.count(),
            1,
        )

    def test_created_at_auto_set(self):
        device = self._create_device()

        self.assertIsNotNone(device.created_at)

    def test_updated_at_changes_on_save(self):
        device = self._create_device()

        time.sleep(1)

        original = device.updated_at
        device.token_hash = "newhash"
        device.save()

        device.refresh_from_db()

        self.assertGreater(
            device.updated_at,
            original,
        )
