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
from commerce_payments.services import ZibalIPG, ZibalEBank
from core.errors import APIError, PaymentError, PaymentGatewayError


class WalletAPIView(APIView):
    serializer_class = WalletSerializer

    def get(self, request):
        wallet = Wallet.objects.get(owner=request.user)

        serializer = self.serializer_class(
            wallet,
            context={"request": request},
        )

        return Response({"plans": serializer.data}, status=status.HTTP_200_OK)


class WalletTopUpAPIView(APIView):

    def post(self, request):
        amount = parse_topup_amount(request.data.get("amount"))
        wallet = request.user.wallet

        # Step 1: Create Payment
        payment: Payment = Payment.objects.create_wallet_top_up(
            wallet=wallet,
            amount=amount,
        )

        # Build dynamic callback URL
        callback_url = request.build_absolute_uri("/api/commerce/wallet/callback/")

        zibal = ZibalIPG()
        total_amount = amount + zibal.fee
        response = zibal.request_payment(
            amount=total_amount,
            callback_url=callback_url,
            order_id=payment.id,
            mobile=request.user.phone_number,
            description="wallet top up",
        )

        if response and response["result"] == 100:
            PaymentGateway.objects.create(
                payment=payment,
                track_id=response["trackId"],
            )
            return Response(
                {"gateway_url": zibal.start_url(track_id=response["trackId"])},
                status=status.HTTP_200_OK,
            )
        else:
            payment.mark_failed()
            raise APIError(PaymentError.GATEWAY_ERROR)


@method_decorator(csrf_exempt, name="dispatch")
class WalletTopUpCallbackAPIView(APIView):
    authentication_classes = []
    permission_classes = []

    def get(self, request):
        gateway_status = str(request.GET.get("status"))
        track_id = str(request.GET.get("trackId"))
        order_id = str(request.GET.get("orderId"))

        payment_verified = False

        try:
            with transaction.atomic():
                # -------------------------------------------------
                # Lock everything belonging to this top-up.
                # -------------------------------------------------
                try:
                    gateway: PaymentGateway = (
                        PaymentGateway.objects.select_for_update(of=("self", "payment"))
                        .select_related("payment")
                        .get(track_id=track_id)
                    )
                except PaymentGateway.DoesNotExist:
                    raise APIError(PaymentGatewayError.GATEWAY_NOT_FOUND)

                payment: Payment = gateway.payment

                # -------------------------------------------------
                # Validate the callback against the locked payment.
                # -------------------------------------------------
                if (
                    str(payment.id) != str(order_id)
                    or payment.purpose != Payment.Purpose.WALLET_TOP_UP
                    or payment.wallet_id is None
                ):
                    raise APIError(PaymentError.PAYMENT_NOT_FOUND)

                wallet: Wallet = Wallet.objects.select_for_update().get(pk=payment.wallet_id)

                # -------------------------------------------------
                # Idempotency check.
                # Because payment is locked, another callback for
                # this payment cannot pass this point concurrently.
                # -------------------------------------------------
                if payment.status == Payment.Status.SUCCEEDED:
                    return redirect("/wallet/payment/result?status=success")
                if payment.status == Payment.Status.FAILED:
                    return redirect("/wallet/payment/result?status=failed")

                # -------------------------------------------------
                # Validate gateway callback status.
                # -------------------------------------------------
                if gateway_status not in ("1", "2"):
                    if gateway_status == "3":
                        payment.mark_failed()
                        return redirect("/wallet/payment/result?status=cancelled")
                    payment.mark_failed()
                    return redirect("/wallet/payment/result?status=failed")

                # -------------------------------------------------
                # Verify payment with Zibal.
                # -------------------------------------------------
                zibal = ZibalIPG()
                response = zibal.verify_payment(track_id=track_id)

                if not response:
                    payment.mark_failed()
                    return redirect("/wallet/payment/result?status=failed")

                if response.get("result") not in (100, 201):
                    payment.mark_failed()
                    return redirect("/wallet/payment/result?status=failed")

                if response.get("amount") != payment.amount + zibal.fee:
                    payment.mark_failed()
                    return redirect("/wallet/payment/result?status=failed")

                # ---------------------------------------------------------
                # At this point Zibal says the money was successfully paid
                # From here onward, we MUST either:
                #   1. successfully create the wallet top-up
                #   2. rollback everything and refund the payment
                # ---------------------------------------------------------
                payment_verified = True
                balance_before = wallet.balance
                wallet.credit(payment.amount)
                WalletLedger.objects.create_top_up_ledger(
                    wallet=wallet,
                    payment=payment,
                    amount=payment.amount,
                    balance_before=balance_before,
                )
                payment.mark_succeeded()
                gateway.mark_verified(
                    ref_num=response.get("refNumber"),
                    card_number=response.get("cardNumber"),
                )

                # TODO:
                # transaction.on_commit(
                #     lambda: send_success_sms.delay(payment.id)
                # )

            # If we reach here, the database transaction committed.
            return redirect("/wallet/payment/result?status=success")

        except Exception:
            # -----------------------------------------------------
            # IMPORTANT:
            #
            # We are OUTSIDE transaction.atomic() here.
            #
            # Therefore every database change inside the transaction
            # has already been rolled back.
            #
            # The wallet was NOT credited.
            # The ledger was NOT created.
            # Payment was NOT marked succeeded.
            # Gateway was NOT marked verified.
            #
            # But Zibal already received the money.
            # -----------------------------------------------------
            if not payment_verified:
                raise

            # TODO: handel the case that refund responce is not successfull
            refund_resp = ZibalEBank().refund(
                track_id=track_id,
                amount=payment.amount,
                description=(f"wallet topup refund for payment={payment.id}"),
            )
            if not refund_resp or refund_resp.get("result") != 100:
                raise APIError(PaymentError.GATEWAY_ERROR)

            payment.mark_failed()
            # TODO: queue refund SMS notification
            return redirect("/wallet/payment/result?status=refunded")
