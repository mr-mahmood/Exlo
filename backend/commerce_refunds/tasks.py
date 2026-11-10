# commerce_refunds/tasks.py


from celery import shared_task
from django.db import transaction
from commerce_payments.models import Payment
from commerce_refunds.models import Refund
from commerce_wallet.models import Wallet
from commerce_wallet_ledger.models import WalletLedger


@shared_task
def process_approved_refunds():

    # 1. Get all approved refund IDs without locking.
    refund_ids = list(Refund.objects.filter(status=Refund.Status.APPROVED).values_list("id", flat=True))

    # 2. Process refunds individually.
    for refund_id in refund_ids:
        try:
            with transaction.atomic():

                # Lock only this refund.
                refund: Refund = Refund.objects.select_for_update().get(pk=refund_id)

                # Another worker may have completed it.
                if refund.status != Refund.Status.APPROVED:
                    continue

                payment: Payment = refund.payment

                # 3. Find and lock destination wallet.
                if payment.purpose == Payment.Purpose.WALLET_TOP_UP:
                    wallet: Wallet = Wallet.objects.select_for_update().get(pk=payment.wallet_id)
                elif payment.purpose == Payment.Purpose.ORDER_PAYMENT:
                    wallet: Wallet = Wallet.objects.select_for_update().get(owner_id=payment.order.buyer_id)

                # 4. Credit wallet.
                balance_before = wallet.balance
                wallet.credit(refund.amount)

                # 5. Create refund ledger.
                WalletLedger.objects.create_refund_ledger(
                    wallet=wallet,
                    refund=refund,
                    amount=refund.amount,
                    balance_before=balance_before,
                )

                # 6. Mark refund completed.
                refund.mark_completed()

        except Exception:
            continue
