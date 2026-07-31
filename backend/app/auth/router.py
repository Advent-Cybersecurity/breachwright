from fastapi import APIRouter, Depends, HTTPException, Response, Cookie
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from app.db.session import get_db
from app.auth.schemas import (
    LoginRequest,
    ChangePasswordRequest,
    TokenResponse,
    UserCreate,
    UserResponse,
    UserUpdate,
)
from app.auth.service import (
    authenticate_user, create_access_token, create_refresh_token,
    decode_token, create_user, get_user_by_id, get_active_user_count,
    hash_password, verify_password, DuplicateEmailError,
)
from app.auth.dependencies import get_current_user, require_admin
from app.auth.models import User, UserRole
from app.config import settings

router = APIRouter(prefix="/api/auth", tags=["auth"])




@router.get("/needs-setup")
async def needs_setup(db: AsyncSession = Depends(get_db)):
    """Check if the app needs first-run setup (no users exist)."""
    count = await get_active_user_count(db)
    return {"needs_setup": count == 0}


@router.post("/setup")
async def first_run_setup(request: UserCreate, db: AsyncSession = Depends(get_db)):
    """Create the first admin user. Only works when no users exist."""
    count = await get_active_user_count(db)
    if count > 0:
        raise HTTPException(status_code=403, detail="Setup already completed. Use the app to manage users.")

    from app.auth.models import UserRole
    try:
        user = await create_user(
            db,
            email=request.email,
            password=request.password,
            display_name=request.display_name or str(request.email).split("@")[0],
            role=UserRole.admin,
        )
    except DuplicateEmailError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"message": f"Admin account created: {user.email}", "email": user.email}


@router.post("/login", response_model=TokenResponse)
async def login(request: LoginRequest, response: Response, db: AsyncSession = Depends(get_db)):
    user = await authenticate_user(db, request.email, request.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid email or password")

    access_token = create_access_token(user.id, user.role.value, user.token_version)
    refresh_token = create_refresh_token(user.id, user.token_version)

    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        samesite="lax",
        max_age=settings.refresh_token_expire_days * 24 * 60 * 60,
        path="/",
    )

    return TokenResponse(access_token=access_token)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    response: Response,
    refresh_token: Optional[str] = Cookie(None),
    db: AsyncSession = Depends(get_db),
):
    if not refresh_token:
        raise HTTPException(status_code=401, detail="No refresh token")

    payload = decode_token(refresh_token)
    if not payload or payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    user = await get_user_by_id(db, payload["sub"])
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found or inactive")
    if payload.get("ver", 0) != user.token_version:
        raise HTTPException(status_code=401, detail="Session has been revoked")

    access_token = create_access_token(user.id, user.role.value, user.token_version)
    new_refresh = create_refresh_token(user.id, user.token_version)

    response.set_cookie(
        key="refresh_token",
        value=new_refresh,
        httponly=True,
        samesite="lax",
        max_age=settings.refresh_token_expire_days * 24 * 60 * 60,
        path="/",
    )

    return TokenResponse(access_token=access_token)


@router.post("/logout")
async def logout(response: Response):
    # Remove both the current cookie and the narrower path used by v2.0.
    response.delete_cookie("refresh_token", path="/")
    response.delete_cookie("refresh_token", path="/api/auth")
    return {"message": "Logged out"}


@router.get("/me", response_model=UserResponse)
async def me(current_user: User = Depends(get_current_user)):
    return current_user


@router.post("/change-password")
async def change_password(
    request: ChangePasswordRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not verify_password(request.current_password, current_user.password_hash):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    if verify_password(request.new_password, current_user.password_hash):
        raise HTTPException(
            status_code=400,
            detail="New password must be different from the current password",
        )

    current_user.password_hash = hash_password(request.new_password)
    current_user.token_version += 1
    await db.flush()
    response.delete_cookie("refresh_token", path="/")
    response.delete_cookie("refresh_token", path="/api/auth")
    return {"message": "Password changed. Sign in again with your new password."}


@router.post("/users", response_model=UserResponse)
async def create_new_user(
    request: UserCreate,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    try:
        user = await create_user(
            db,
            request.email,
            request.password,
            request.display_name,
            request.role,
        )
    except DuplicateEmailError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return user


@router.get("/users", response_model=list[UserResponse])
async def list_users(
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    result = await db.execute(select(User).order_by(User.email))
    return list(result.scalars().all())


@router.patch("/users/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: str,
    request: UserUpdate,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    if not request.model_fields_set:
        raise HTTPException(status_code=400, detail="No user changes were provided")

    result = await db.execute(select(User).where(User.id == user_id))
    target = result.scalar_one_or_none()
    if target is None:
        raise HTTPException(status_code=404, detail="User not found")

    changes_own_access = target.id == admin.id and (
        request.is_active is False
        or (request.role is not None and request.role != target.role)
    )
    if changes_own_access:
        raise HTTPException(
            status_code=400,
            detail="You cannot deactivate or change the role of your own account",
        )

    removes_active_admin = (
        target.is_active
        and target.role == UserRole.admin
        and (
            request.is_active is False
            or (request.role is not None and request.role != UserRole.admin)
        )
    )
    if removes_active_admin:
        active_admins = await db.scalar(
            select(func.count(User.id)).where(
                User.role == UserRole.admin,
                User.is_active == True,
            )
        )
        if active_admins <= 1:
            raise HTTPException(
                status_code=400,
                detail="At least one active administrator is required",
            )

    if request.display_name is not None:
        target.display_name = request.display_name
    if request.role is not None:
        target.role = request.role
    if request.is_active is not None:
        if request.is_active != target.is_active:
            target.token_version += 1
        target.is_active = request.is_active
    await db.flush()
    return target
