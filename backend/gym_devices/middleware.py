# gym_devices/middleware.py

from channels.db import database_sync_to_async

from core.errors import APIError
from core.hashing import verify_secret
from gym.models import Gym
from gym_devices.models import GymDevice


class DeviceAuthMiddleware:

    def __init__(self, inner):
        self.inner = inner

    async def __call__(self, scope, receive, send):
        scope = dict(scope)

        if scope["type"] != "websocket":
            return await self.inner(scope, receive, send)

        gym_id = scope.get("url_route", {}).get("kwargs", {}).get("gym_id")
        token = get_websocket_device_token(scope)

        if gym_id is None or token is None:
            await self._reject(send)
            return

        device = await authenticate_websocket_device(
            gym_id=gym_id,
            raw_token=token,
        )

        if device is None:
            await self._reject(send)
            return

        scope["device"] = device
        await self.inner(scope, receive, send)

    @staticmethod
    async def _reject(send):
        await send(
            {
                "type": "websocket.close",
                "code": 4401,
            }
        )


def get_websocket_device_token(scope):
    headers = dict(scope.get("headers", []))
    authorization = headers.get(b"authorization")

    if authorization is None:
        return None

    parts = authorization.split()

    if len(parts) != 2 or parts[0].lower() != b"device":
        return None

    try:
        return parts[1].decode("ascii")
    except UnicodeDecodeError:
        return None


@database_sync_to_async
def authenticate_websocket_device(gym_id, raw_token):
    try:
        gym = Gym.objects.get_gym(gym_id=gym_id)

        if len(raw_token) < 12:
            return None

        device = GymDevice.objects.filter(
            gym=gym,
            token_prefix=raw_token[:12],
            is_active=True,
        ).first()

        if device is None:
            return None

        if not verify_secret(raw_token, device.token_hash):
            return None

        return device

    except APIError:
        return None
