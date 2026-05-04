from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import AppUser


async def sync_user_from_claims(session: AsyncSession, claims: dict) -> AppUser:
    sub = claims.get("sub")
    if not sub or not isinstance(sub, str):
        raise ValueError("missing sub")
    email = claims.get("email") if isinstance(claims.get("email"), str) else None
    result = await session.execute(select(AppUser).where(AppUser.stack_user_id == sub))
    row = result.scalar_one_or_none()
    if row is None:
        row = AppUser(stack_user_id=sub, email=email)
        session.add(row)
        await session.commit()
        await session.refresh(row)
    elif email and row.email != email:
        row.email = email
        await session.commit()
        await session.refresh(row)
    return row
