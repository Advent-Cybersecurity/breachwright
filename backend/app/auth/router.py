from fastapi import APIRouter, Depends, HTTPException, Response, Cookie
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from app.db.session import get_db
from app.auth.schemas import LoginRequest, TokenResponse, UserCreate, UserResponse
from app.auth.service import (
    authenticate_user, create_access_token, create_refresh_token,
    decode_token, create_user, get_user_by_id, get_active_user_count,
)
from app.auth.dependencies import get_current_user, require_admin
from app.auth.models import User

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
    user = await create_user(
        db,
        email=request.email,
        password=request.password,
        display_name=request.display_name or request.email.split("@")[0],
        role=UserRole.admin,
    )
    return {"message": f"Admin account created: {user.email}", "email": user.email}


@router.post("/login", response_model=TokenResponse)
async def login(request: LoginRequest, response: Response, db: AsyncSession = Depends(get_db)):
    user = await authenticate_user(db, request.email, request.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid email or password")

    access_token = create_access_token(user.id, user.role.value)
    refresh_token = create_refresh_token(user.id)

    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        samesite="lax",
        max_age=7 * 24 * 60 * 60,
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

    access_token = create_access_token(user.id, user.role.value)
    new_refresh = create_refresh_token(user.id)

    response.set_cookie(
        key="refresh_token",
        value=new_refresh,
        httponly=True,
        samesite="lax",
        max_age=7 * 24 * 60 * 60,
    )

    return TokenResponse(access_token=access_token)


@router.post("/logout")
async def logout(response: Response):
    response.delete_cookie("refresh_token")
    return {"message": "Logged out"}


@router.get("/me", response_model=UserResponse)
async def me(current_user: User = Depends(get_current_user)):
    return current_user


@router.post("/users", response_model=UserResponse)
async def create_new_user(
    request: UserCreate,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    user = await create_user(db, request.email, request.password, request.display_name, request.role)
    return user
