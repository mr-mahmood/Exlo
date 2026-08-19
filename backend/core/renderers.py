from rest_framework.renderers import JSONRenderer


class GlobalJSONRenderer(JSONRenderer):
    """
    Standardizes API response format across the application.

    Output format:
        Success: {"success": true, "data": {...}, "error": null}
        Error:   {"success": false, "data": null, "error": "ERROR_CODE"}
    """

    def render(self, data, accepted_media_type=None, renderer_context=None):
        response = renderer_context.get("response") if renderer_context else None

        # Skip non-DRF responses (file downloads, etc.)
        if response is None:
            return super().render(data, accepted_media_type, renderer_context)

        is_success = 200 <= response.status_code < 300
        response_data = data or {}

        # Extract error code if present
        error_code = response_data.get("error")

        # Build the standardized payload
        if is_success:
            payload = {
                "success": True,
                "data": response_data,
                "error": None,
            }
        else:
            payload = {
                "success": False,
                "data": None,
                "error": error_code,
            }

        return super().render(payload, accepted_media_type, renderer_context)
