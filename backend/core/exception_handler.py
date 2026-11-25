from rest_framework.views import exception_handler
from rest_framework import status
from django.conf import settings
from core.errors import APIError


def custom_exception_handler(exc, context):
    if isinstance(exc, APIError):
        from rest_framework.response import Response

        response_data = {
            "error_code": exc.error_code,
        }

        # Only include message in debug mode
        if settings.DEBUG:
            response_data["error_message"] = exc.message

        return Response(
            data=response_data,
            status=getattr(exc, "status_code", status.HTTP_400_BAD_REQUEST),
            headers={"Retry-After": str(exc.retry_after)} if exc.retry_after else None,
        )

    # Call DRF's default exception handler
    response = exception_handler(exc, context)

    if response is not None:
        # Map status codes to error codes
        error_code_map = {
            status.HTTP_400_BAD_REQUEST: "VALIDATION_ERROR",
            status.HTTP_401_UNAUTHORIZED: "UNAUTHORIZED",
            status.HTTP_403_FORBIDDEN: "NOT_FOUND",  # Convert 403 to 404 for security
            status.HTTP_404_NOT_FOUND: "NOT_FOUND",
            status.HTTP_405_METHOD_NOT_ALLOWED: "METHOD_NOT_ALLOWED",
            status.HTTP_429_TOO_MANY_REQUESTS: "RATE_LIMIT_EXCEEDED",
        }

        # Prepare data for renderer
        response_data = {
            "error_code": error_code_map.get(response.status_code, "ERROR"),
        }

        # Add detail in debug mode
        if settings.DEBUG and response.status_code != status.HTTP_403_FORBIDDEN:
            if hasattr(exc, "detail"):
                response_data["error_message"] = str(exc.detail)

        response.data = response_data

        # Convert 403 to 404
        if response.status_code == status.HTTP_403_FORBIDDEN:
            response.status_code = status.HTTP_404_NOT_FOUND

    return response
