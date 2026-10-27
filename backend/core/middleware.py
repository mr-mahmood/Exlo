# core/middleware.py

import time
import logging

logger = logging.getLogger("request_timing")


class RequestTimingMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        start = time.perf_counter()

        response = self.get_response(request)

        duration_ms = (time.perf_counter() - start) * 1000

        response["Server-Timing"] = f"django;dur={duration_ms:.2f}"

        return response
