from celery import shared_task
from django.utils import timezone
from datetime import timedelta
from .models import Session


@shared_task
def cleanup_expired_sessions():
    """Delete sessions inactive for more than 30 days."""

    expiry_date = timezone.now() - timedelta(days=30)
    Session.objects.filter(last_activity_at__lt=expiry_date).delete()

    return "Clean up old Session completed"
