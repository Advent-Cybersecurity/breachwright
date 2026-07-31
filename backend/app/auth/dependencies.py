from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.auth.service import decode_token, get_user_by_id
from app.auth.models import User, UserRole

security = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> User:
    payload = decode_token(credentials.credentials)
    if not payload or payload.get("type") != "access":
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    user = await get_user_by_id(db, payload["sub"])
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found or inactive")
    if payload.get("ver", 0) != user.token_version:
        raise HTTPException(status_code=401, detail="Session has been revoked")

    return user


async def require_admin(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role != UserRole.admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    return current_user


async def require_editor(current_user: User = Depends(get_current_user)) -> User:
    """Allow users who may change engagement data.

    Viewers are intentionally read-only across the application. Administrators
    and analysts retain the same editing capabilities.
    """
    if current_user.role == UserRole.viewer:
        raise HTTPException(status_code=403, detail="Read-only account")
    return current_user
