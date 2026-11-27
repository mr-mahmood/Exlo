from unittest.mock import patch
from uuid import uuid4

from django.core.cache import cache
from django.test import SimpleTestCase, runner


class RedisIsolationTests(SimpleTestCase):
    def test_clear_preserves_another_workers_cache_and_raw_keys(self):
        key = f"isolation-{uuid4().hex}"
        raw_key = cache.make_key(key + "-raw")
        current = cache.client.get_client(write=True)
        self.assertGreaterEqual(current.connection_pool.connection_kwargs["db"], 4)
        # Only clear our own worker. The peer may be running another test.
        peer_id = 0 if runner._worker_id else 1
        with patch.object(runner, "_worker_id", peer_id):
            peer = cache.client.get_client(write=True)
            cache.set(key, "peer", timeout=60)
            peer.set(raw_key, b"peer", ex=60)
            self.addCleanup(peer.delete, cache.make_key(key), raw_key)

        cache.set(key, "local", timeout=60)
        current.set(raw_key, b"local", ex=60)
        cache.clear()
        self.assertIsNone(cache.get(key))
        self.assertIsNone(current.get(raw_key))
        with patch.object(runner, "_worker_id", peer_id):
            self.assertEqual(cache.get(key), "peer")
            self.assertEqual(peer.get(raw_key), b"peer")
