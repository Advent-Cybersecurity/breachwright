from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt
from passlib.context import CryptContext
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import User, UserRole
from app.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

ALGORITHM = "HS256"


class DuplicateEmailError(ValueError):
    """Raised when a user account already exists for an email address."""


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def create_access_token(user_id: str, role: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_expire_minutes)
    payload = {
        "sub": user_id,
        "role": role,
        "exp": expire,
        "type": "access",
    }
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)


def create_refresh_token(user_id: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(days=settings.refresh_token_expire_days)
    payload = {
        "sub": user_id,
        "exp": expire,
        "type": "refresh",
    }
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)


def decode_token(token: str) -> Optional[dict]:
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
        return payload
    except jwt.PyJWTError:
        return None


async def authenticate_user(db: AsyncSession, email: str, password: str) -> Optional[User]:
    normalized_email = email.strip().lower()
    result = await db.execute(
        select(User).where(
            User.email == normalized_email,
            User.is_active == True,
        )
    )
    user = result.scalar_one_or_none()
    if user and verify_password(password, user.password_hash):
        user.last_login = datetime.now(timezone.utc)
        return user
    return None


async def get_user_by_id(db: AsyncSession, user_id: str) -> Optional[User]:
    result = await db.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()


async def get_active_user_count(db: AsyncSession) -> int:
    result = await db.execute(select(func.count(User.id)).where(User.is_active == True))
    return result.scalar_one()


async def create_user(
    db: AsyncSession,
    email: str,
    password: str,
    display_name: Optional[str],
    role: UserRole = UserRole.analyst,
) -> User:
    normalized_email = str(email).strip().lower()
    existing = await db.execute(select(User.id).where(User.email == normalized_email))
    if existing.scalar_one_or_none():
        raise DuplicateEmailError("A user with this email already exists")
    normalized_name = (display_name or normalized_email.split("@")[0]).strip()
    user = User(
        email=normalized_email,
        password_hash=hash_password(password),
        display_name=normalized_name,
        role=role,
    )
    db.add(user)
    await db.flush()
    return user
