"""Single-owner compatibility for the local Breachwright workspace."""

from sqlalchemy import case, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import User, UserRole
from app.db.session import async_session


LOCAL_OWNER_EMAIL = "local@breachwright.invalid"
LOCAL_OWNER_NAME = "Local Owner"
LOCAL_PASSWORD_MARKER = "!local-workspace-no-password"


async def get_or_create_local_owner(db: AsyncSession) -> User:
    """Return the deterministic local owner used by every application request.

    Existing installations keep their earliest administrator so foreign-key
    ownership remains stable. If no administrator exists, the earliest user is
    promoted. Fresh installations receive one internal compatibility record.
    """
    owner = await db.scalar(
        select(User).order_by(
            case((User.role == UserRole.admin, 0), else_=1),
            User.created_at,
            User.id,
        )
    )
    if owner is None:
        owner = User(
            email=LOCAL_OWNER_EMAIL,
            password_hash=LOCAL_PASSWORD_MARKER,
            display_name=LOCAL_OWNER_NAME,
            role=UserRole.admin,
            is_active=True,
            token_version=0,
        )
        db.add(owner)
        await db.flush()
        return owner

    changed = False
    if owner.role != UserRole.admin:
        owner.role = UserRole.admin
        changed = True
    if not owner.is_active:
        owner.is_active = True
        changed = True
    if changed:
        await db.flush()
    return owner


async def ensure_local_owner() -> User:
    """Ensure the local owner exists after database migrations finish."""
    async with async_session() as db:
        owner = await get_or_create_local_owner(db)
        await db.commit()
        return owner
