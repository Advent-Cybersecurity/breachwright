from pydantic import BaseModel, EmailStr
from typing import Optional
from app.auth.models import UserRole


class LoginRequest(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserCreate(BaseModel):
    email: str
    password: str
    display_name: Optional[str] = None
    role: UserRole = UserRole.analyst


class UserResponse(BaseModel):
    id: str
    email: str
    display_name: Optional[str] = None
    role: UserRole
    is_active: bool

    model_config = {"from_attributes": True}


class UserUpdate(BaseModel):
    display_name: Optional[str] = None
    role: Optional[UserRole] = None
    is_active: Optional[bool] = None
