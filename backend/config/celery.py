# config/celery.py
import os
from celery import Celery

# ============================================
# CELERY INITIALIZATION
# ============================================
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
app = Celery("fitness")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()


# ============================================
# DEBUG TASK
# ============================================
@app.task(bind=True)
def debug_task(self):
    """Debug task to verify Celery is working"""
    print(f"Request: {self.request!r}")
