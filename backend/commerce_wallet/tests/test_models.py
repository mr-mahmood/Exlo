from django.db import IntegrityError, transaction
from django.test import TestCase

from commerce_wallet.models import Wallet
from users.models import User


class WalletModelTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(phone_number="09120001002")

    def test_owner_has_one_wallet_and_zero_balance_is_valid(self):
        wallet = Wallet.objects.create(owner=self.owner)
        self.assertEqual(wallet.pk.version, 7)
        self.assertEqual(wallet.balance, 0)

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Wallet.objects.create(owner=self.owner)

    def test_database_rejects_negative_balance_on_insert_and_update(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Wallet.objects.create(owner=self.owner, balance=-1)

        wallet = Wallet.objects.create(owner=self.owner, balance=10)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Wallet.objects.filter(pk=wallet.pk).update(balance=-1)

        wallet.refresh_from_db()
        self.assertEqual(wallet.balance, 10)
