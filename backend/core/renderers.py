from rest_framework.renderers import JSONRenderer
from django.conf import settings


class GlobalJSONRenderer(JSONRenderer):
    def render(self, data, accepted_media_type=None, renderer_context=None):
        response = renderer_context.get("response") if renderer_context else None

        # Skip non-DRF responses (file downloads, etc.)
        if response is None:
            return super().render(data, accepted_media_type, renderer_context)

        # Determine if response is successful
        is_success = 200 <= response.status_code < 300

        # Build the standardized payload
        if is_success:
            payload = {
                "success": True,
                "data": data if data is not None else None,
                "error_code": None,
            }
        else:
            # Extract error information
            error_code = data.get("error_code", "ERROR")
            error_message = data.get("error_message") if settings.DEBUG else None

            payload = {
                "success": False,
                "data": None,
                "error_code": error_code,
            }

            # Only include error_message in development
            if settings.DEBUG and error_message:
                payload["error_message"] = error_message

        return super().render(payload, accepted_media_type, renderer_context)
