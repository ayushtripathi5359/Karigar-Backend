from __future__ import annotations

import logging
from decimal import Decimal
from uuid import uuid4

from app.providers.base import ConfirmResult, IntentResult, PaymentProvider

logger = logging.getLogger(__name__)


class StubPaymentProvider:
    name = "stub"

    async def create_intent(
        self, *, order_id: str, amount_inr: Decimal, idempotency_key: str
    ) -> IntentResult:
        provider_payment_id = f"stub_pay_{uuid4().hex[:16]}"
        bar = "=" * 52
        logger.info("[PAYMENT STUB] intent created order=%s amount=₹%s ref=%s",
                    order_id, amount_inr, provider_payment_id)
        print(
            f"\n{bar}\n  [PAYMENT STUB]  intent\n"
            f"  order_id    {order_id}\n"
            f"  amount_inr  ₹{amount_inr}\n"
            f"  provider_id {provider_payment_id}\n{bar}\n",
            flush=True,
        )
        return IntentResult(provider_payment_id=provider_payment_id)

    async def confirm(
        self, *, provider_payment_id: str, requested_outcome: str
    ) -> ConfirmResult:
        bar = "=" * 52
        if requested_outcome == "success":
            print(f"\n{bar}\n  [PAYMENT STUB]  confirm SUCCESS  ref={provider_payment_id}\n{bar}\n", flush=True)
            return ConfirmResult(status="succeeded")
        print(f"\n{bar}\n  [PAYMENT STUB]  confirm FAILURE  ref={provider_payment_id}\n{bar}\n", flush=True)
        return ConfirmResult(status="failed", error_code="STUB_DECLINED",
                             error_message="Payment declined by stub provider (QA failure path)")


default_provider: PaymentProvider = StubPaymentProvider()
