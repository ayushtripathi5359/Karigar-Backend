from typing import Annotated

from fastapi import APIRouter, Depends, Request

from app.modules.auth.deps import CurrentUser, current_user
from app.modules.payments.providers.stub import default_provider
from app.modules.payments.schemas import (
    PaymentConfirmBody,
    PaymentConfirmResponse,
    PaymentIntentBody,
    PaymentIntentResponse,
)
from app.modules.payments.services import confirmation as confirm_svc
from app.modules.payments.services import intent as intent_svc
from app.shared.rate_limit import limiter

router = APIRouter(prefix="/v1/payments", tags=["payments"])


@router.post(
    "/intent",
    response_model=PaymentIntentResponse,
    status_code=201,
    summary="Open a payment intent for an order (idempotent on idempotency_key)",
)
@limiter.limit("30/minute")
async def open_intent(
    request: Request,
    body: PaymentIntentBody,
    me: Annotated[CurrentUser, Depends(current_user)],
) -> PaymentIntentResponse:
    row = await intent_svc.create_intent(
        me.session,
        user_id=me.user_id,
        order_id=body.order_id,
        idempotency_key=body.idempotency_key,
        provider=default_provider,
    )
    return PaymentIntentResponse(**row)


@router.post(
    "/confirm",
    response_model=PaymentConfirmResponse,
    summary="Confirm payment — flips order to 'confirmed' (success) or 'cancelled' (failure)",
)
@limiter.limit("30/minute")
async def confirm_payment(
    request: Request,
    body: PaymentConfirmBody,
    me: Annotated[CurrentUser, Depends(current_user)],
) -> PaymentConfirmResponse:
    row = await confirm_svc.confirm(
        me.session,
        user_id=me.user_id,
        payment_id=body.payment_id,
        idempotency_key=body.idempotency_key,
        requested_outcome=body.outcome,
        provider=default_provider,
    )
    return PaymentConfirmResponse(**row)
