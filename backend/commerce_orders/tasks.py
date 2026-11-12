# commerce_orders/tasks.py


from celery import shared_task
from django.db import transaction
from commerce_orders.models import Order
from commerce_payments.models import Payment
from commerce_refunds.models import Refund
from commerce_wallet.models import Wallet
from commerce_wallet_ledger.models import WalletLedger


@shared_task
def process_seller_settlements():

    # Get unsettled successful orders without locking.
    order_ids = list(
        Order.objects.filter(
            status=Order.Status.SUCCEEDED,
            settlement_status=Order.SettlementStatus.HELD,
        ).values_list("id", flat=True)
    )

    for order_id in order_ids:
        try:
            with transaction.atomic():

                # 1. Lock order.
                order: Order = Order.objects.select_for_update().get(pk=order_id)
                seller_revenue = order.subtotal_amount - order.discount_amount

                # 2. Check order and settlement status.
                if order.status != Order.Status.SUCCEEDED or order.settlement_status != Order.SettlementStatus.HELD:
                    continue

                # 3. Get the confirmed paid payment.
                try:
                    payment: Payment = Payment.objects.get(
                        order=order,
                        purpose=Payment.Purpose.ORDER_PAYMENT,
                        status=Payment.Status.PAID,
                        amount=order.total_amount,
                    )
                except Payment.DoesNotExist:
                    continue
                except Payment.MultipleObjectsReturned:
                    continue

                # 4. Check product refundability.
                if order.is_refundable:
                    continue

                # 5. Check refunds.
                has_refund = Refund.objects.filter(payment__order=order).exists()
                if has_refund:
                    continue

                # 6. Check previous seller revenue.
                if WalletLedger.objects.filter(
                    payment__order_id=order.id,
                    reason=WalletLedger.Reason.SALE_REVENUE,
                ).exists():
                    continue

                # 7. Lock seller wallet.
                wallet: Wallet = Wallet.objects.select_for_update().get(owner_id=order.seller_id)

                # 8. Credit seller wallet.
                balance_before = wallet.balance
                wallet.credit(seller_revenue)

                # 9. Create seller revenue ledger.
                WalletLedger.objects.create_seller_revenue_ledger(
                    wallet=wallet,
                    payment=payment,
                    amount=seller_revenue,
                    balance_before=balance_before,
                )

                # 10. Mark settlement released.
                order.mark_settlement_released()

        except Exception:
            continue
