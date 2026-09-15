# gym_devices/tasks.py

from celery import shared_task
from gym_devices.models import GymDevice


@shared_task
def delete_stale_gym_devices():

    stale = GymDevice.objects.filter(is_active=False)
    stale.delete()

    return "Delete deactive devices"
