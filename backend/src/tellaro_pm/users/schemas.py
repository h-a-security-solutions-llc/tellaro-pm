"""Pydantic schemas for user management endpoints."""

from typing import Literal

from pydantic import BaseModel, EmailStr, Field


class UserCreate(BaseModel):
    username: str = Field(min_length=2, max_length=64, pattern=r"^[a-zA-Z0-9_\-]+$")
    email: EmailStr
    display_name: str = Field(min_length=1, max_length=128)
    password: str | None = Field(default=None, min_length=8)
    avatar_url: str | None = None
    role: Literal["admin", "member"] = "member"
    auth_provider: Literal["local", "github", "oidc"] = "local"


class UserUpdate(BaseModel):
    username: str | None = Field(default=None, min_length=2, max_length=64, pattern=r"^[a-zA-Z0-9_\-]+$")
    email: EmailStr | None = None
    display_name: str | None = Field(default=None, min_length=1, max_length=128)
    password: str | None = Field(default=None, min_length=8)
    avatar_url: str | None = None
    role: Literal["admin", "member"] | None = None
    is_active: bool | None = None


class UserResponse(BaseModel):
    id: str
    username: str
    email: str
    display_name: str
    avatar_url: str | None = None
    role: Literal["admin", "member"]
    is_active: bool
    auth_provider: Literal["local", "github", "oidc"]
    created_at: str
    updated_at: str


class UserListResponse(BaseModel):
    users: list[UserResponse]
    total: int
