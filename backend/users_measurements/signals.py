from django.db import transaction
from django.db.models.signals import post_delete
from django.dispatch import receiver

from .models import MeasurementPhotos


@receiver(post_delete, sender=MeasurementPhotos)
def delete_measurement_photo_file(sender, instance, using, **kwargs):
    if not instance.photo:
        return

    storage = instance.photo.storage
    name = instance.photo.name

    def delete_photo_file():
        storage.delete(name)

    transaction.on_commit(delete_photo_file, using=using, robust=True)
