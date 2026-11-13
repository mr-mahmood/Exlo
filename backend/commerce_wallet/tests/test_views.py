from unittest.mock import patch

from requests.exceptions import Timeout
from django.test import TestCase
from rest_framework.test import APIClient

from commerce_payments.models import Payment
from commerce_payments_gateway.models import PaymentGateway
from commerce_refunds.models import Refund
from commerce_wallet.models import Wallet
from commerce_wallet_ledger.models import WalletLedger
from users.models import User


class WalletTopUpCallbackTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(phone_number="09121111111")
        self.wallet = Wallet.objects.create(owner=self.user, balance=100)
        self.payment = Payment.objects.create_wallet_top_up(wallet=self.wallet, amount=1_000_000)
        self.gateway = PaymentGateway.objects.create(payment=self.payment, track_id=123456)
        self.params = {"trackId": "123456", "orderId": str(self.payment.pk)}
        self.url = "/api/commerce/wallet/callback/"

    def assert_no_credit(self):
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance, 100)
        self.assertFalse(WalletLedger.objects.exists())
        self.assertFalse(Refund.objects.exists())

    def test_timeout_stays_pending_and_retry_credits_exactly_once(self):
        with patch("commerce_payments.services.requests.post", side_effect=Timeout()):
            response = self.client.get(self.url, self.params)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/wallet/payment/result?status=pending")
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, "PENDING")
        self.assertIsNone(self.payment.paid_at)
        self.assert_no_credit()

        with patch("commerce_wallet.views.ZibalIPG.verify_payment", return_value={
            "result": 100, "amount": self.payment.total_amount,
            "refNumber": "receipt", "cardNumber": "603799******1234",
        }) as verify:
            self.assertEqual(self.client.get(self.url, self.params).status_code, 302)
            self.assertEqual(self.client.get(self.url, self.params).status_code, 302)
            verify.assert_called_once()
        self.wallet.refresh_from_db()
        self.payment.refresh_from_db()
        self.gateway.refresh_from_db()
        self.assertEqual(self.wallet.balance, 1_000_100)
        self.assertEqual(self.payment.status, "PAID")
        self.assertIsNotNone(self.payment.paid_at)
        self.assertEqual(self.gateway.ref_num, "receipt")
        entry = WalletLedger.objects.get()
        self.assertEqual((entry.wallet_id, entry.payment_id, entry.amount, entry.balance_before),
                         (self.wallet.pk, self.payment.pk, 1_000_000, 100))
        self.assertEqual(entry.reason, "TOP_UP")

    def test_invalid_identifiers_return_not_found_without_verification(self):
        cases = ({}, {"trackId": "123456"}, {"orderId": str(self.payment.pk)})
        cases += tuple({**self.params, "trackId": value} for value in ("", "abc", "1.5", "-1", "9" * 100))
        cases += tuple({**self.params, "orderId": value} for value in ("", "bad-uuid"))
        with patch("commerce_wallet.views.ZibalIPG.verify_payment") as verify:
            for params in cases:
                with self.subTest(params=params):
                    response = self.client.get(self.url, params)
                    self.assertEqual(response.status_code, 404)
                    self.assertFalse(response.json()["success"])
            verify.assert_not_called()
        self.assert_no_credit()

    def test_unknown_gateway_and_wrong_payment_are_not_found(self):
        for params in ({**self.params, "trackId": "654321"},
                       {**self.params, "orderId": "00000000-0000-0000-0000-000000000000"}):
            with self.subTest(params=params), patch("commerce_wallet.views.ZibalIPG.verify_payment") as verify:
                self.assertEqual(self.client.get(self.url, params).status_code, 404)
                verify.assert_not_called()
        self.assert_no_credit()

    def test_definitive_rejection_and_wrong_amount_still_fail(self):
        for payload in ({"result": -1}, {"result": 100, "amount": 1}):
            Payment.objects.filter(pk=self.payment.pk).update(status="PENDING")
            with self.subTest(payload=payload), patch("commerce_wallet.views.ZibalIPG.verify_payment", return_value=payload):
                self.assertEqual(self.client.get(self.url, self.params).status_code, 302)
                self.payment.refresh_from_db()
                self.assertEqual(self.payment.status, "FAILED")
                self.assert_no_credit()
