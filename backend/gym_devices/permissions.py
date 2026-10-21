# gym_devices/permissions.py

from rest_framework.permissions import BasePermission
from core.errors import APIError, GymDeviceError
from gym_devices.models import GymDevice


class IsGymGate(BasePermission):
    def has_permission(self, request, view):
        device = request.auth

        if not isinstance(device, GymDevice):
            raise APIError(GymDeviceError.DEVICE_NOT_FOUND)

        return device.device_type == GymDevice.GymDeviceType.ENTRANCE


class IsGymLocker(BasePermission):
    def has_permission(self, request, view):
        device = request.auth

        if not isinstance(device, GymDevice):
            raise APIError(GymDeviceError.DEVICE_NOT_FOUND)

        return device.device_type == GymDevice.GymDeviceType.LOCKER
