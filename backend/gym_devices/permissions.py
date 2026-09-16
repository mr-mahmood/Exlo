from rest_framework.permissions import BasePermission
from gym_devices.models import GymDevice
from core.errors import APIError, GymDeviceError


class IsGymDevice(BasePermission):
    def has_permission(self, request, view):
        if not isinstance(request.auth, GymDevice):
            raise APIError(GymDeviceError.DEVICE_NOT_FOUND)
        return True
