import json as jsonlib
from unittest.mock import Mock, patch

from django.db import IntegrityError
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from commerce_payments.models import Payment, PaymentGateway
from commerce_wallet.models import Wallet
from commerce_wallet_ledger.models import WalletLedger
from users.models import User


class WalletTopUpTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(phone_number="09121234567")
        self.wallet = Wallet.objects.create(owner=self.user)
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    @patch("commerce_payments.services.requests.post")
    def test_initiation_sends_serializable_order_id_and_stores_gateway_track_id(self, post):
        def gateway_request(url, *, json, **kwargs):
            jsonlib.dumps(json)
            return Mock(json=lambda: {"result": 100, "trackId": 123456789})

        post.side_effect = gateway_request
        response = self.client.post(
            reverse("commerce_wallet:top-up"), {"amount": 1_000_000}, format="json"
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "success": True,
                "data": {"gateway_url": "https://gateway.zibal.ir/start/123456789"},
                "error_code": None,
            },
        )
        payment = Payment.objects.get(wallet=self.wallet)
        self.assertEqual(payment.status, Payment.Status.PENDING)
        self.assertEqual(payment.amount, 1_000_000)
        self.assertEqual(PaymentGateway.objects.get(payment=payment).track_id, 123456789)
        payload = post.call_args.kwargs["json"]
        self.assertEqual(payload["orderId"], str(payment.id))
        self.assertEqual(payload["amount"], 1_250_000)
        self.assertEqual(payload["callbackUrl"], "http://testserver/api/commerce/wallet/callback/")
        self.assertEqual(reverse("commerce_wallet:callback"), "/api/commerce/wallet/callback/")

    @patch("commerce_payments.services.requests.post")
    def test_gateway_rejection_marks_payment_failed(self, post):
        post.return_value.json.return_value = {"result": 104, "message": "invalid merchant"}

        response = self.client.post(
            reverse("commerce_wallet:top-up"), {"amount": 1_000_000}, format="json"
        )

        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.json()["error_code"], "PAY_001")
        self.assertEqual(Payment.objects.get(wallet=self.wallet).status, Payment.Status.FAILED)
        self.assertFalse(PaymentGateway.objects.exists())

    @patch("commerce_payments.services.requests.post")
    def test_unauthenticated_user_cannot_initiate_payment(self, post):
        self.client.force_authenticate(user=None)

        response = self.client.post(
            reverse("commerce_wallet:top-up"), {"amount": 1_000_000}, format="json"
        )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(Payment.objects.exists())
        post.assert_not_called()

    def test_cancelled_callback_marks_payment_failed(self):
        payment = Payment.objects.create_wallet_top_up(wallet=self.wallet, amount=1_000_000)
        PaymentGateway.objects.create(payment=payment, track_id=123456789)

        response = self.client.get(
            reverse("commerce_wallet:callback"),
            {"status": "3", "trackId": "123456789", "orderId": str(payment.pk)},
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], "/wallet/payment/result?status=cancelled")
        payment.refresh_from_db()
        self.assertEqual(payment.status, Payment.Status.FAILED)

    @patch("commerce_payments.services.requests.post")
    def test_verified_callback_credits_wallet_once(self, post):
        self.wallet.balance = 300
        self.wallet.save(update_fields=["balance"])
        payment = Payment.objects.create_wallet_top_up(wallet=self.wallet, amount=1_000_000)
        PaymentGateway.objects.create(payment=payment, track_id=123456789)
        post.return_value.json.return_value = {
            "result": 100,
            "amount": 1_250_000,
            "refNumber": "reference",
            "cardNumber": "1234",
        }
        params = {"status": "2", "trackId": "123456789", "orderId": str(payment.pk)}

        first = self.client.get(reverse("commerce_wallet:callback"), params)
        second = self.client.get(reverse("commerce_wallet:callback"), params)

        self.assertEqual(first.status_code, 302)
        self.assertEqual(first["Location"], "/wallet/payment/result?status=success")
        self.assertEqual(second.status_code, 302)
        self.wallet.refresh_from_db()
        payment.refresh_from_db()
        self.assertEqual(self.wallet.balance, 1_000_300)
        self.assertEqual(payment.status, Payment.Status.SUCCEEDED)
        entries = list(WalletLedger.objects.filter(payment=payment))
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].amount, 1_000_000)
        self.assertEqual(entries[0].balance_before, 300)
        self.assertEqual(entries[0].entry_type, WalletLedger.EntryType.CREDIT)
        self.assertEqual(entries[0].reason, WalletLedger.Reason.TOP_UP)
        post.assert_called_once()

    @patch("commerce_wallet.views.ZibalEBank.refund", return_value={"result": 100})
    @patch("commerce_wallet_ledger.models.WalletLedgerManager.create")
    @patch("commerce_wallet.views.ZibalIPG.verify_payment", return_value={"result": 100, "amount": 1_250_000})
    def test_failed_ledger_insert_rolls_back_credit_and_requests_refund(self, verify, create, refund):
        payment = Payment.objects.create_wallet_top_up(wallet=self.wallet, amount=1_000_000)
        PaymentGateway.objects.create(payment=payment, track_id=123456789)
        balance_at_insert = []

        def fail_insert(**kwargs):
            balance_at_insert.append(Wallet.objects.get(pk=self.wallet.pk).balance)
            raise IntegrityError("ledger insert failed")

        create.side_effect = fail_insert

        response = self.client.get(
            reverse("commerce_wallet:callback"),
            {"status": "2", "trackId": "123456789", "orderId": str(payment.pk)},
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], "/wallet/payment/result?status=refunded")
        self.wallet.refresh_from_db()
        payment.refresh_from_db()
        self.assertEqual(self.wallet.balance, 0)
        self.assertEqual(payment.status, Payment.Status.FAILED)
        self.assertFalse(WalletLedger.objects.exists())
        self.assertEqual(balance_at_insert, [1_000_000])
        verify.assert_called_once_with(track_id="123456789")
        create.assert_called_once()
        refund.assert_called_once()
