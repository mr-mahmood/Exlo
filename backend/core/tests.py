from datetime import datetime, timezone
from unittest.mock import patch

from django.test import SimpleTestCase
from django.utils.dateparse import parse_datetime
from rest_framework import serializers
from rest_framework.request import Request
from rest_framework.test import APIRequestFactory

from core.cache import cache_key


class APIDateTimeFormatTests(SimpleTestCase):
    def test_datetime_represents_the_correct_instant(self):
        class TimestampSerializer(serializers.Serializer):
            created_at = serializers.DateTimeField()

        instant = datetime(2026, 1, 1, 12, 0, 0, 123456, tzinfo=timezone.utc)

        value = TimestampSerializer({"created_at": instant}).data["created_at"]

        self.assertEqual(value, "2026-01-01T15:30:00.123456+03:30")
        self.assertEqual(parse_datetime(value), instant)


class CacheKeyQueryParameterTests(SimpleTestCase):
    def test_repeated_scalar_value_order_produces_distinct_keys(self):
        factory = APIRequestFactory()
        first = Request(factory.get("/api/subscriptions/?status=ACTIVE&status=CANCELLED"))
        second = Request(factory.get("/api/subscriptions/?status=CANCELLED&status=ACTIVE"))

        self.assertEqual(first.query_params.get("status"), "CANCELLED")
        self.assertEqual(second.query_params.get("status"), "ACTIVE")
        with patch("core.cache._get_version", return_value=1):
            self.assertNotEqual(
                cache_key("user:subscriptions", request=first),
                cache_key("user:subscriptions", request=second),
            )

    def test_distinct_parameter_order_remains_canonical(self):
        factory = APIRequestFactory()
        first = Request(factory.get("/api/gyms/?page=2&page_size=20"))
        second = Request(factory.get("/api/gyms/?page_size=20&page=2"))

        with patch("core.cache._get_version", return_value=1):
            self.assertEqual(
                cache_key("gym:list", request=first),
                cache_key("gym:list", request=second),
            )
