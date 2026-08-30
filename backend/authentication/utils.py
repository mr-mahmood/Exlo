from rest_framework.response import Response
from django.conf import settings

AUTH_TRANSPORT_HEADER = "X-Auth-Transport"
AUTH_TRANSPORT_BEARER = "bearer"


def make_cookie(response: Response, cookies: dict) -> Response:
    for key, value in cookies.items():
        response.set_cookie(
            key=key,
            value=value,
            httponly=True,
            secure=settings.SESSION_COOKIE_SECURE,
            samesite=settings.SESSION_COOKIE_SAMESITE,
            path="/",
            domain=settings.SESSION_COOKIE_DOMAIN,
        )
    return response


def is_bearer_transport(request) -> bool:
    return (
        request.headers.get(AUTH_TRANSPORT_HEADER, "").lower() == AUTH_TRANSPORT_BEARER
    )


def attach_auth_tokens(
    response: Response,
    request,
    access_token: str,
    refresh_token: str,
) -> Response:

    if is_bearer_transport(request):
        # Merge the tokens into existing response data
        if isinstance(response.data, dict):
            response.data.update(
                {
                    "access": access_token,
                    "refresh": refresh_token,
                }
            )
        else:
            # If response.data is not a dict, create a new dict
            response.data = {
                "access": access_token,
                "refresh": refresh_token,
            }
    else:
        make_cookie(
            response,
            {
                "access_token": access_token,
                "refresh_token": refresh_token,
            },
        )

    return response
