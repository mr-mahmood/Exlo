from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import TokenError
from core.errors import APIError, AuthenticationError, UserAccountError
from users.models import User


def create_tokens_for_user(user, session):
    """
    Create access and refresh tokens with session_id claim.
    """
    refresh = RefreshToken.for_user(user)
    refresh["key_2"] = str(session.session_id)

    return {
        "access": str(refresh.access_token),
        "refresh": str(refresh),
    }


def refresh_tokens(refresh_token_str, request):
    """
    Rotate refresh token and generate new access token.
    """
    try:
        old_refresh = RefreshToken(refresh_token_str)
    except TokenError:
        raise APIError(AuthenticationError.INVALID_REFRESH_TOKEN)

    # Get user
    user: User = User.objects.get(id=old_refresh["key_1"])
    user.validate_account_status()

    # Blacklist old refresh token
    old_refresh.blacklist()

    # Create new tokens
    new_refresh = RefreshToken.for_user(user)

    # Preserve session_id if exists
    session_id = old_refresh.get("key_2")
    if session_id:
        new_refresh["key_2"] = session_id

    return str(new_refresh.access_token), str(new_refresh)
