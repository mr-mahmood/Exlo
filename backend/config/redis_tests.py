from contextlib import ExitStack

from django.conf import settings
from django.core.management.base import CommandError
from django.db import connection
from django.test import runner
from django_redis.cache import RedisCache
from redis import Redis


def worker_url(base_url, worker_id):
    server, database = base_url.rsplit("/", 1)
    if database != "4" or worker_id < 0:
        raise ValueError("Test Redis must use DB 4 or a dedicated worker DB above it.")
    return f"{server}/{4 + worker_id}"


class WorkerRedisCache(RedisCache):
    _worker_id = None

    @property
    def client(self):
        # A fork can inherit a backend already initialized by the parent.
        worker_id = runner._worker_id
        if self._worker_id != worker_id:
            server = worker_url(self._server, worker_id)
            self._client = self._client_cls(server, self._params, self)
            self._worker_id = worker_id
        return self._client


class RedisTestRunner(runner.DiscoverRunner):
    def run_tests(self, test_labels, **kwargs):
        # A session lock also releases if the runner exits unexpectedly.
        with connection._nodb_cursor() as cursor, ExitStack() as resources:
            cursor.execute("SELECT pg_try_advisory_lock(hashtext('exlo.redis-tests'))")
            if not cursor.fetchone()[0]:
                raise CommandError("Another Exlo test run owns the test Redis databases.")

            base_url = settings.CACHES["default"]["LOCATION"]
            clients = []
            for worker_id in range(max(1, self.parallel) + 1):
                client = resources.enter_context(Redis.from_url(worker_url(base_url, worker_id)))
                if client.dbsize():
                    raise CommandError(f"Test Redis DB {4 + worker_id} already contains data.")
                clients.append(client)

            try:
                return super().run_tests(test_labels, **kwargs)
            finally:
                for client in clients:
                    client.flushdb()
