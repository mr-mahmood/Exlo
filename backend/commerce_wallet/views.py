# commerce_wallet/views.py

from django.db import transaction
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import status
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from django.shortcuts import redirect
from commerce_wallet.models import Wallet
from commerce_wallet_ledger.models import WalletLedger
from commerce_wallet.serializers import WalletSerializer
from commerce_wallet.validators import parse_topup_amount
from commerce_payments.models import Payment
from commerce_payments_gateway.models import PaymentGateway
from commerce_refunds.models import Refund
from commerce_payments.services import ZibalIPG, ZibalEBank
from core.errors import APIError, PaymentError, PaymentGatewayError


class WalletAPIView(APIView):
    serializer_class = WalletSerializer

    def get(self, request):
        wallet = Wallet.objects.get(owner=request.user)
        serializer = self.serializer_class(wallet, context={"request": request})
        return Response({"plans": serializer.data}, status=status.HTTP_200_OK)


class WalletTopUpAPIView(APIView):

    def post(self, request):
        amount = parse_topup_amount(request.data.get("amount"))

        payment: Payment = Payment.objects.create_wallet_top_up(
            wallet=request.user.wallet,
            amount=amount,
        )

        zibal = ZibalIPG()
        callback_url = request.build_absolute_uri("/api/commerce/wallet/callback/")

        # External API request
        try:
            response = zibal.request_payment(
                amount=payment.total_amount,
                callback_url=callback_url,
                order_id=str(payment.id),
                mobile=request.user.phone_number,
                description="Wallet top up",
            )
        except Exception:
            payment.mark_failed()
            raise APIError(PaymentError.GATEWAY_ERROR)

        if not response or response.get("result") != 100:
            payment.mark_failed()
            raise APIError(PaymentError.GATEWAY_ERROR)

        track_id = response.get("trackId")
        if not track_id:
            payment.mark_failed()
            raise APIError(PaymentError.GATEWAY_ERROR)

        try:
            PaymentGateway.objects.create(payment=payment, track_id=track_id)
        except Exception:
            payment.mark_failed()
            raise APIError(PaymentError.GATEWAY_ERROR)

        return Response({"gateway_url": zibal.start_url(track_id=track_id)}, status=status.HTTP_200_OK)


@method_decorator(csrf_exempt, name="dispatch")
class WalletTopUpCallbackAPIView(APIView):
    authentication_classes = []
    permission_classes = []

    def get(self, request):
        track_id = str(request.GET.get("trackId"))
        order_id = str(request.GET.get("orderId"))

        with transaction.atomic():

            # 1. Lock gateway and payment
            try:
                gateway: PaymentGateway = PaymentGateway.objects.select_for_update().get(track_id=track_id)
            except PaymentGateway.DoesNotExist:
                raise APIError(PaymentGatewayError.GATEWAY_NOT_FOUND)

            payment: Payment = Payment.objects.select_for_update().get(pk=gateway.payment_id)

            # 2. Validate payment
            if (
                str(payment.id) != str(order_id)
                or payment.purpose != Payment.Purpose.WALLET_TOP_UP
                or payment.payment_method != Payment.Method.ONLINE_GATEWAY
                or payment.wallet_id is None
            ):
                raise APIError(PaymentError.PAYMENT_NOT_FOUND)

            # 3. Lock wallet
            wallet: Wallet = Wallet.objects.select_for_update().get(pk=payment.wallet_id)

            # 4. Check idempotency
            if payment.status == Payment.Status.PAID:
                return redirect("/wallet/payment/result?status=paid")
            if payment.status == Payment.Status.FAILED:
                return redirect("/wallet/payment/result?status=failed")

            # 5. Verify with Zibal
            zibal = ZibalIPG()
            response = zibal.verify_payment(track_id=track_id)

            if not response:
                payment.mark_failed()
                return redirect("/wallet/payment/result?status=failed")

            if response.get("result") not in (100, 201):
                payment.mark_failed()
                return redirect("/wallet/payment/result?status=failed")

            expected_amount = payment.amount + payment.gateway_fee_amount
            if response.get("amount") != expected_amount:
                payment.mark_failed()
                return redirect("/wallet/payment/result?status=failed")

            # Zibal confirmed payment.
            payment.mark_paid()
            gateway.mark_verified(
                ref_num=response.get("refNumber"),
                card_number=response.get("cardNumber"),
            )

            # From here onward, we MUST either:
            #   1. successfully create the wallet top-up
            #   2. rollback everything and refund the payment
            try:
                # Inner transaction (savepoint)
                with transaction.atomic():
                    balance_before = wallet.balance

                    wallet.credit(payment.amount)
                    WalletLedger.objects.create_top_up_ledger(
                        wallet=wallet,
                        payment=payment,
                        amount=payment.amount,
                        balance_before=balance_before,
                    )

                    # TODO:
                    # transaction.on_commit(
                    #     lambda: send_success_sms.delay(payment.id)
                    # )

                    # Wallet credit succeeded.
                    return redirect("/wallet/payment/result?status=success")

            except Exception:
                # Inner transaction was rolled back.
                # No wallet credit or ledger is committed.

                Refund.objects.create_wallet_top_up_refund(payment=payment)

                # TODO:
                # transaction.on_commit(
                #     lambda: send_success_sms.delay(payment.id)
                # )

                return redirect("/wallet/payment/result?status=refund_approved")
