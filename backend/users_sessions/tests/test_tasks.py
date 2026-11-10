import subprocess
import sys
from datetime import datetime, timedelta
from unittest.mock import patch
from zoneinfo import ZoneInfo

from django.conf import settings
from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from authentication.token_services import create_tokens_for_user
from config.celery import app
from core.errors import SessionError
from users.models import User
from users_sessions.models import Session

CLEANUP_TASK_NAME = "users_sessions.tasks.cleanup_expired_sessions"


class SessionCleanupConfigurationTest(SimpleTestCase):
    def test_worker_discovers_cleanup_task_in_fresh_process(self):
        # Importing a task in this test process must not hide broken discovery.
        script = f"""
from celery.app.utils import find_app
app = find_app("config")
app.loader.import_default_modules()
assert {CLEANUP_TASK_NAME!r} in app.tasks, "Session cleanup task is not registered"
"""
        result = subprocess.run(
            [sys.executable, "-c", script],
            cwd=settings.BASE_DIR,
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_beat_schedules_cleanup_daily(self):
        entries = [entry for entry in app.conf.beat_schedule.values() if entry["task"] == CLEANUP_TASK_NAME]
        self.assertEqual(len(entries), 1, "Session cleanup needs one Beat schedule")
        schedule = entries[0]["schedule"]
        run_at = datetime(2026, 11, 6, 3, 10, tzinfo=ZoneInfo(settings.CELERY_TIMEZONE))
        previous_run = run_at - timedelta(days=1)

        for now, last_run, expected_due, next_run in (
            (run_at - timedelta(minutes=1), previous_run, False, 60),
            (run_at, previous_run, True, 86400),
            (run_at + timedelta(minutes=1), run_at, False, 86340),
        ):
            with self.subTest(now=now):
                with patch.object(schedule, "now", return_value=now):
                    due = schedule.is_due(last_run)
                self.assertEqual(due.is_due, expected_due)
                self.assertEqual(due.next, next_run)


class SessionCleanupTaskTest(TestCase):
    def setUp(self):
        app.loader.import_default_modules()
        self.cleanup_task = app.tasks[CLEANUP_TASK_NAME]
        self.now = datetime(2026, 11, 6, 12, tzinfo=ZoneInfo("UTC"))
        self.user = User.objects.create_user(
            phone_number="09123456789",
            first_name="John",
            last_name="Doe",
            gender=User.Gender.MALE,
        )
        self.other_user = User.objects.create_user(
            phone_number="09123456788",
            first_name="Jane",
            last_name="Doe",
            gender=User.Gender.FEMALE,
        )

    def _create_session(self, last_activity_at, user=None):
        return Session.objects.create(
            user=user or self.user,
            ip_address="127.0.0.1",
            user_agent="Session cleanup test",
            last_activity_at=last_activity_at,
        )

    def _run_cleanup(self):
        with patch("users_sessions.tasks.timezone.now", return_value=self.now):
            self.cleanup_task()

    def test_cleanup_removes_only_sessions_inactive_for_more_than_30_days(self):
        self._create_session(self.now - timedelta(days=31))
        self._create_session(self.now - timedelta(days=30, microseconds=1), user=self.other_user)
        boundary_session = self._create_session(self.now - timedelta(days=30))
        recent_session = self._create_session(
            self.now - timedelta(days=30) + timedelta(microseconds=1),
            user=self.other_user,
        )
        active_session = self._create_session(self.now)
        Session.objects.filter(pk=active_session.pk).update(created_at=self.now - timedelta(days=60))

        self._run_cleanup()

        self.assertSetEqual(
            set(Session.objects.values_list("pk", flat=True)),
            {boundary_session.pk, recent_session.pk, active_session.pk},
        )
        self.assertEqual(User.objects.count(), 2)

    def test_cleanup_is_safe_to_repeat_or_run_without_sessions(self):
        self._run_cleanup()
        self.assertEqual(Session.objects.count(), 0)
        self._create_session(self.now - timedelta(days=31))
        recent_session = self._create_session(self.now)

        for attempt in range(2):
            with self.subTest(attempt=attempt):
                self._run_cleanup()
                self.assertEqual(
                    list(Session.objects.values_list("pk", flat=True)),
                    [recent_session.pk],
                )

    def test_cleanup_revokes_deleted_session_tokens_and_preserves_active_session(self):
        expired_session = self._create_session(self.now - timedelta(days=31))
        active_session = self._create_session(self.now)
        expired_client = APIClient()
        active_client = APIClient()
        for client, session in (
            (expired_client, expired_session),
            (active_client, active_session),
        ):
            access, refresh = create_tokens_for_user(self.user, session)
            client.cookies["access_token"] = access
            client.cookies["refresh_token"] = refresh

        self._run_cleanup()

        response = expired_client.get(reverse("user_sessions:user-sessions"))
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["error_code"], SessionError.SESSION_EXPIRE[0])
        response = expired_client.post(reverse("authentication:refresh"))
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["error_code"], SessionError.SESSION_EXPIRE[0])
        self.assertFalse(Session.objects.filter(pk=expired_session.pk).exists())

        response = active_client.get(reverse("user_sessions:user-sessions"))
        self.assertEqual(response.status_code, 200)
        response = active_client.post(reverse("authentication:refresh"))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(Session.objects.filter(pk=active_session.pk).exists())
