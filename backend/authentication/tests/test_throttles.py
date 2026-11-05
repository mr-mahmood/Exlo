from types import SimpleNamespace

from django.test import SimpleTestCase

from authentication.throttles import OTPPhoneThrottle


class OTPPhoneKeyTests(SimpleTestCase):
    def test_phone_key_normalizes_surrounding_spaces(self):
        throttle = OTPPhoneThrottle()
        canonical = throttle.get_cache_key(
            SimpleNamespace(data={"phone_number": "09123456789"}), None
        )
        padded = throttle.get_cache_key(
            SimpleNamespace(data={"phone_number": " 09123456789 "}), None
        )
        self.assertIsNotNone(canonical)
        self.assertEqual(padded, canonical)

    def test_missing_empty_and_non_string_phones_have_no_phone_key(self):
        throttle = OTPPhoneThrottle()
        for phone in (
            None,
            "",
            " \t ",
            9123456789,
            0,
            True,
            False,
            [],
            ["09123456789"],
            {},
            {"phone": "09123456789"},
        ):
            with self.subTest(phone=phone):
                self.assertIsNone(
                    throttle.get_cache_key(
                        SimpleNamespace(data={"phone_number": phone}), None
                    )
                )
        self.assertIsNone(throttle.get_cache_key(SimpleNamespace(data={}), None))
