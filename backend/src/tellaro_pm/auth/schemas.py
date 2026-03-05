"""Pydantic schemas for authentication endpoints."""

from typing import Literal

from pydantic import BaseModel, EmailStr, Field


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1)


class OAuthCallbackRequest(BaseModel):
    code: str = Field(min_length=1)
    state: str = Field(min_length=1)
    provider: Literal["github", "oidc"]


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class AuthDiscoveryRequest(BaseModel):
    email: EmailStr


class AuthDiscoveryResponse(BaseModel):
    provider: Literal["local", "github", "oidc"]
    redirect_url: str | None = None


class AuthDomainCreate(BaseModel):
    domain: str = Field(min_length=1, pattern=r"^[a-zA-Z0-9]([a-zA-Z0-9\-]*[a-zA-Z0-9])?(\.[a-zA-Z]{2,})+$")
    provider: Literal["local", "github", "oidc"]
    provider_config: dict[str, object] = Field(default_factory=dict)


class AuthDomainUpdate(BaseModel):
    provider: Literal["local", "github", "oidc"] | None = None
    provider_config: dict[str, object] | None = None
    is_active: bool | None = None


class AuthDomainResponse(BaseModel):
    id: str
    domain: str
    provider: Literal["local", "github", "oidc"]
    provider_config: dict[str, object]
    is_active: bool
    created_at: str
    updated_at: str
