# commerce_commissions/models.py

import uuid
from django.db import models


class ReferralCommissionManager(models.Manager):
    pass


class ReferralCommission(models.Model):

    # Custom manager
    objects: ReferralCommissionManager = ReferralCommissionManager()
