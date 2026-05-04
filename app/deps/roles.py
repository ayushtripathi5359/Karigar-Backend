from enum import Enum
from typing import Annotated

from fastapi import Depends, HTTPException, status

from app.deps.auth import current_user
from app.models.user import AppUser


class UserRole(str, Enum):
    user = "user"
    admin = "admin"
    vendor = "vendor"


def require_role(*allowed: UserRole):
    allowed_values = {r.value for r in allowed}

    async def dependency(user: Annotated[AppUser, Depends(current_user)]) -> AppUser:
        if user.role not in allowed_values:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "insufficient role")
        return user

    return dependency
