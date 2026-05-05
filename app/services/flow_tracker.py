import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.flow import UserFlowEvent

logger = logging.getLogger(__name__)


async def logtrack(
    session: AsyncSession,
    *,
    event: str,
    phone: str | None = None,
    request_id: str | None = None,
) -> None:
    record = UserFlowEvent(phone=phone, event=event, request_id=request_id)
    session.add(record)
    await session.commit()
    logger.info("[logtrack] event=%s phone=%s rid=%s", event, phone, request_id)
