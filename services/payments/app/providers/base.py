from dataclasses import dataclass
from decimal import Decimal
from typing import Literal, Protocol


@dataclass
class IntentResult:
    provider_payment_id: str


@dataclass
class ConfirmResult:
    status: Literal["succeeded", "failed"]
    error_code: str | None = None
    error_message: str | None = None


class PaymentProvider(Protocol):
    name: str

    async def create_intent(
        self, *, order_id: str, amount_inr: Decimal, idempotency_key: str
    ) -> IntentResult: ...

    async def confirm(
        self, *, provider_payment_id: str, requested_outcome: str
    ) -> ConfirmResult: ...
