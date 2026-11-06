import json as jsonlib
from unittest.mock import Mock, patch

from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from commerce_payments.models import Payment, PaymentGateway
from commerce_wallet.models import Wallet
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
