from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.auth.local_owner import get_or_create_local_owner
from app.auth.models import User


async def get_current_user(
    db: AsyncSession = Depends(get_db),
) -> User:
    """Resolve every request to the single owner of this local workspace."""
    return await get_or_create_local_owner(db)


async def require_admin(current_user: User = Depends(get_current_user)) -> User:
    return current_user


async def require_editor(current_user: User = Depends(get_current_user)) -> User:
    return current_user
