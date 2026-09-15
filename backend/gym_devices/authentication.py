# gym_devices/authentication.py

from rest_framework import authentication
from core.errors import APIError, GymDeviceError
from gym.models import Gym
from gym_devices.models import GymDevice


class DeviceTokenAuthentication(authentication.BaseAuthentication):
    keyword = "Bearer"

    def authenticate(self, request):

        header = authentication.get_authorization_header(request).split()
        if not header or header[0].lower() != self.keyword.lower().encode():
            return None

        if len(header) != 2:
            raise APIError(GymDeviceError.INVALID_DEVICE_CREDENTIAL)

        gym_id = self._extract_gym_id(request)
        if gym_id is None:
            raise APIError(GymDeviceError.INVALID_DEVICE_CREDENTIAL)

        gym = Gym.objects.get_gym(gym_id=gym_id, active_only=True)

        raw_token = header[1].decode()
        device = GymDevice.objects.find_device(gym, raw_token)

        return (None, device)

    @staticmethod
    def _extract_gym_id(request):
        resolver_match = getattr(request, "resolver_match", None)
        if resolver_match is None:
            return None
        return resolver_match.kwargs.get("gym_id")
