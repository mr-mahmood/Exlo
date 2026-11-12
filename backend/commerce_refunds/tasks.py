# commerce_refunds/tasks.py


from celery import shared_task
from django.db import transaction
from commerce_orders.models import Order
from commerce_payments.models import Payment
from commerce_refunds.models import Refund
from commerce_wallet.models import Wallet
from commerce_wallet_ledger.models import WalletLedger


@shared_task
def process_pending_refunds():

    # Get pending refund IDs without locking.
    refund_ids = list(Refund.objects.filter(status=Refund.Status.PENDING).values_list("id", flat=True))

    for refund_id in refund_ids:
        try:
            with transaction.atomic():

                # Lock the refund.
                refund: Refund = Refund.objects.select_for_update().get(pk=refund_id)

                # Prevent duplicate processing.
                if refund.status != Refund.Status.PENDING:
                    continue

                payment: Payment = refund.payment

                # Financial checks.
                if payment.status != Payment.Status.PAID:
                    continue

                if refund.amount != payment.amount:
                    continue

                # Determine the destination wallet.
                if payment.purpose == Payment.Purpose.WALLET_TOP_UP:
                    wallet: Wallet = Wallet.objects.select_for_update().get(pk=payment.wallet_id)

                elif payment.purpose == Payment.Purpose.ORDER_PAYMENT:
                    # Lock the order
                    order: Order = Order.objects.select_for_update().get(pk=payment.order_id)

                    wallet: Wallet = Wallet.objects.select_for_update().get(owner_id=order.buyer_id)

                    # Seller revenue must not be released.
                    if order.status != Order.Status.SUCCEEDED or order.settlement_status != Order.SettlementStatus.HELD:
                        continue

                    # Void seller settlement for order refunds.
                    order.mark_settlement_voided()

                else:
                    # must add new payment purpose as system get bigger
                    continue

                # Credit wallet.
                balance_before = wallet.balance
                wallet.credit(refund.amount)

                # Create refund ledger.
                WalletLedger.objects.create_refund_ledger(
                    wallet=wallet,
                    payment=payment,
                    amount=refund.amount,
                    balance_before=balance_before,
                )

                # Complete refund.
                refund.mark_completed()

        except Exception:
            continue
