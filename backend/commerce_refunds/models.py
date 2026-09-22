# commerce_refunds/models.py

import uuid
from django.db import models


class RefundManager(models.Manager):
    pass


class Refund(models.Model):

    # Custom manager
    objects: RefundManager = RefundManager()
