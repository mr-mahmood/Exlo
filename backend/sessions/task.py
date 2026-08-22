from celery import shared_task
from django.utils import timezone
from datetime import timedelta
from .models import UserSession


@shared_task
def cleanup_expired_sessions():
    """Run daily to clean up old sessions"""

    expiry_date = timezone.now() - timedelta(days=30)
    UserSession.objects.filter(last_activity_at__lt=expiry_date).delete()

    return f"Clean up old sessions completed"
